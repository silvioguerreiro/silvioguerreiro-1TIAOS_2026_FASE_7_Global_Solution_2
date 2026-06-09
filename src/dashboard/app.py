"""
SENTINELA — Painel de Comando (Streamlit).

Dashboard inteligente que integra TODAS as disciplinas da GS 2026.1:
  • Visão computacional (CNN/fallback) ...... acurácia + detecções na cena
  • Redes neurais (RNN/LSTM/AR) ............. previsão de focos de calor
  • Pipeline de dados ....................... execução ponta a ponta
  • Cloud/AWS serverless (mock) ............. log Lambda/SNS/SQS/CloudWatch
  • Serviços cognitivos (mock Rekognition) .. rótulos por detecção
  • SQL (SQLite) + NoSQL (mongomock) ........ detecções e telemetria
  • IoT/ESP32 .............................. telemetria de sensor de campo
  • Algoritmo genético ...................... rota ótima de patrulha
  • Recomendação / análise preditiva ........ priorização de alertas
  • DADOS PÚBLICOS REAIS .................... cenas Sentinel-2 (STAC) e
                                              focos NASA FIRMS (data/ingest.py)

Rodar:  streamlit run dashboard/app.py
"""
import sys
import urllib.request
import urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import streamlit as st
import pydeck as pdk
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import (AOI, AREA_PROTEGIDA, CLASS_SEVERITY, CLASSES_ALERTA,
                    SCENE_GRID)
from core import storage
from core.forecast import ForecastModel, tendencia
from core.genetic import otimizar_rota, comprimento_rota
from core.geo import cell_to_latlon
from data.synthetic import generate_fire_timeseries
from data import ingest
from data import repository as repo
from run_demo import executar_pipeline

st.set_page_config(page_title="SENTINELA — Comando", layout="wide",
                   page_icon="🛰️")
storage.init_db()

# Cores por classe (RGB) para o mapa.
COR_CLASSE = {
    "queimada": [230, 74, 25],     # laranja-fogo
    "mineracao": [142, 36, 170],   # roxo
    "urbano": [120, 120, 120],
    "floresta": [27, 94, 32],
    "agua": [21, 101, 192],
}
CENTRO = {"lat": (AOI["lat_min"] + AOI["lat_max"]) / 2,
          "lon": (AOI["lon_min"] + AOI["lon_max"]) / 2}


def _poly(box):
    """dict bbox -> anel de polígono [[lon,lat],...] para PolygonLayer."""
    return [[box["lon_min"], box["lat_min"]], [box["lon_max"], box["lat_min"]],
            [box["lon_max"], box["lat_max"]], [box["lon_min"], box["lat_max"]],
            [box["lon_min"], box["lat_min"]]]


def _pontos_por_prioridade(dets, alertas):
    """(lat,lon) das detecções na ordem de prioridade (baseline ingênuo de
    patrulha = ir do foco mais urgente ao menos urgente)."""
    id2det = {d["id"]: d for d in dets}
    ordenadas = [id2det[a["deteccao_id"]] for a in alertas
                 if a.get("deteccao_id") in id2det]
    if not ordenadas:                       # sem alertas -> usa ordem do banco
        ordenadas = dets
    return [(d["lat"], d["lon"]) for d in ordenadas]


def _rota(pontos):
    """Otimiza a rota de patrulha (GA) e compara com a ordem ingênua recebida."""
    if len(pontos) < 2:
        return pontos, 0.0, 0.0
    rota, dist, _ = otimizar_rota(pontos, geracoes=120, pop=60, seed=42)
    naive = comprimento_rota(list(range(len(pontos))), pontos)
    return [pontos[i] for i in rota], dist, naive


@st.cache_data(ttl=900, show_spinner=False)
def _buscar_sentinel2(max_cloud, max_nodata, limit):
    return ingest.search_sentinel2_scenes(
        max_cloud=max_cloud, max_nodata=max_nodata, limit=limit)


@st.cache_data(ttl=900, show_spinner=False)
def _thumb_bytes(url):
    """Baixa a prévia no SERVIDOR e devolve os bytes — o Streamlit os serve pela
    própria mídia, evitando que o navegador busque no S3 (hotlink/CORS), o que
    causava imagens 'cortadas/ausentes'. Retorna None se falhar."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SENTINELA/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=ingest.SSL_CONTEXT) as r:
            return r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


# ---------------------------------------------------------------------------
# Leitura para decisão — interpreta os dados de cada aba e recomenda ações.
# Cada função devolve bullets em markdown; severidade indicada por emoji
# (🔴 crítico · 🟠 atenção · 🟢 ok · 🔵 info).
# ---------------------------------------------------------------------------
def _painel_decisao(bullets):
    """Renderiza o cartão 'Leitura para decisão' com a lista de achados."""
    with st.container(border=True):
        st.markdown("#### 💡 Leitura para decisão")
        st.markdown("\n".join(f"- {b}" for b in bullets))


def _decisao_mapa(dets, alertas, dist=0.0, naive=0.0, n_rota=0):
    if not dets:
        return ["🔵 Sem detecções persistidas — execute o **pipeline completo** "
                "para gerar o panorama operacional."]
    df = pd.DataFrame(dets)
    n_min = int((df["classe"] == "mineracao").sum())
    n_qmd = int((df["classe"] == "queimada").sum())
    prot = int(pd.to_numeric(df.get("em_area_protegida", 0)).sum())
    crit = [a for a in alertas if a["prioridade"] >= 0.5]
    b = [f"🗺️ **{len(dets)} anomalias** mapeadas: **{n_min}** de mineração e "
         f"**{n_qmd}** de queimada (área impactada ~**{df['area_ha'].sum():.0f} ha**)."]
    if crit:
        top = max(alertas, key=lambda a: a["prioridade"])
        b.append(f"🔴 **{len(crit)} alerta(s) crítico(s)** (prioridade ≥ 0,5). "
                 f"Maior prioridade **{top['prioridade']}** — {top['mensagem'][:64]}…")
    if prot:
        b.append(f"🟠 **{prot}** detecção(ões) dentro da **área protegida** "
                 "(terra indígena/UC): prioridade legal elevada — acionar "
                 "fiscalização imediata.")
    if n_rota >= 2 and naive:
        ganho = round(100 * (naive - dist) / naive, 1)
        b.append(f"🧬 Rota de patrulha otimizada economiza **{ganho}%** de "
                 f"deslocamento ({dist:.0f} vs {naive:.0f} km) — despachar a equipe "
                 "seguindo a sequência do traçado amarelo.")
    return b


def _decisao_s2(scenes):
    if not scenes:
        return []
    cob = lambda s: 100 - (s.get("nodata") or 0)
    melhor = min(scenes, key=lambda s: (s.get("cloud") or 100, -cob(s)))
    b = [f"🛰️ Melhor cena para análise: **{melhor['id']}** "
         f"({(melhor.get('datetime') or '')[:10]}) — nuvem **{melhor['cloud']}%**, "
         f"cobertura **{cob(melhor):.0f}%**. Baixe o true-color e rode "
         "`load_scene_from_image()` para alimentar a CNN com pixels reais."]
    datas = sorted((s["datetime"][:10] for s in scenes if s.get("datetime")))
    if len(datas) >= 2:
        b.append(f"📅 Tiles entre **{datas[0]}** e **{datas[-1]}** — para "
                 "**detecção de mudança**, compare a cena mais antiga com a mais "
                 "recente do mesmo tile MGRS.")
    nuvem_med = sum((s.get("cloud") or 0) for s in scenes) / len(scenes)
    if nuvem_med > 10:
        b.append(f"🟠 Nuvem média **{nuvem_med:.0f}%** nas cenas — reduza o limiar "
                 "para imagens mais limpas, se necessário.")
    return b


def _decisao_firms(df, serie):
    n = len(df)
    conf = df["confidence"].mean()
    frp = pd.to_numeric(df["frp"], errors="coerce").mean()
    alta = int((df["confidence"] >= 0.8).sum())
    b = [f"🔥 **{n} focos** reais na AOI — confiança média **{conf:.2f}** "
         f"(**{alta}** de alta confiança ≥0,8), FRP média **{frp:.1f} MW**."]
    s = np.asarray(serie, dtype=float)
    if len(s) >= 2 and (s[-1] or s[-2]):
        if s[-1] > s[-2]:
            b.append(f"📈 Focos **em alta** no último dia ({s[-2]:.0f}→{s[-1]:.0f}) — "
                     "risco crescente, antecipar mobilização.")
        elif s[-1] < s[-2]:
            b.append(f"📉 Focos **em queda** no último dia ({s[-2]:.0f}→{s[-1]:.0f}).")
    grid = ingest.fire_foci_to_grid(df)
    if grid.sum() > 0:
        r, c = (int(i) for i in np.unravel_index(int(np.argmax(grid)), grid.shape))
        lat, lon = cell_to_latlon(r, c, SCENE_GRID, SCENE_GRID)
        b.append(f"🎯 Maior concentração: **{int(grid[r, c])} focos** em "
                 f"(~{lat}, {lon}) — direcionar sobrevoo/patrulha a esse ponto.")
    if frp >= 20:
        b.append("🔴 FRP elevada — incêndios de alta intensidade; priorizar combate.")
    return b


def _decisao_ia(serie, fc, origem):
    s = np.asarray(serie, dtype=float)
    fc = np.asarray(fc, dtype=float)
    trend = tendencia(fc)
    base = s[-7:].mean() if len(s) >= 7 else s.mean()
    fut = fc.mean()
    var = (fut - base) / base * 100 if base else 0.0
    pico = int(np.argmax(fc)) + 1
    if trend > 0.01:
        b = [f"📈 Tendência de **alta** ({trend:+.3f}): previsão média 7d **{fut:.0f}** "
             f"focos/dia vs **{base:.0f}** recentes (**{var:+.0f}%**) — reforçar "
             "equipes preventivamente."]
    elif trend < -0.01:
        b = [f"📉 Tendência de **queda** ({trend:+.3f}) — pressão de fogo diminuindo; "
             "manter monitoramento de rotina."]
    else:
        b = [f"➡️ Tendência **estável** ({trend:+.3f}); previsão ~**{fut:.0f}** focos/dia."]
    b.append(f"🗓️ Pico previsto no **dia +{pico}** (~{fc[pico - 1]:.0f} focos) — "
             "concentrar recursos nessa janela.")
    b.append(f"📊 Série de origem: **{origem}**.")
    return b


def _decisao_cloud(resumo, tel):
    b = []
    if resumo:
        b.append(f"☁️ Última execução disparou **{resumo['sns_notificacoes']} "
                 f"notificações SNS** e **{resumo['lambda_invocacoes']} eventos "
                 "Lambda/CloudWatch** — fluxo serverless operante (escala sob demanda).")
    if tel:
        fogo = [t for t in tel if t.get("fogo_confirmado")]
        if fogo:
            t0 = fogo[0]
            b.append(f"🔴 **Confirmação multi-fonte**: sensor {t0.get('sensor_id')} "
                     f"reporta fumaça **{t0.get('fumaca')}** e fogo em "
                     f"(~{t0.get('lat')}, {t0.get('lon')}). Cruzado com a detecção "
                     "orbital → **alta confiança**, autorizar despacho.")
        else:
            b.append("🟢 Telemetria de campo sem confirmação de fogo no momento.")
    else:
        b.append("🔵 Sem telemetria — execute o pipeline para popular os sensores ESP32.")
    return b


# Feed real do sensor de campo (gerado por esp32/gerar_telemetria.py).
ESP32_JSONL = Path(__file__).resolve().parent.parent / "esp32" / "telemetria_simulada.jsonl"


def _fig_telemetria_esp32():
    """Gráfico da telemetria do ESP32 (temperatura x fumaça), reproduzindo o feed real
    do sensor de solo. Marca o instante de fogo_confirmado=true (envio do alerta)."""
    if not ESP32_JSONL.exists():
        return None
    regs = []
    for ln in ESP32_JSONL.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            regs.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    if not regs:
        return None
    t = [i * 5 for i in range(len(regs))]          # 5 s entre leituras (firmware)
    temp = [r.get("temp") for r in regs]
    fum = [r.get("fumaca") for r in regs]
    i_fogo = next((i for i, r in enumerate(regs) if r.get("fogo_confirmado")), None)

    fig, ax1 = plt.subplots(figsize=(9, 3.6))
    ax1.plot(t, temp, color="#e11d48", marker="o", ms=4, lw=2, label="Temperatura (°C)")
    ax1.set_xlabel("Tempo desde o início (s)")
    ax1.set_ylabel("Temperatura (°C)", color="#e11d48")
    ax1.tick_params(axis="y", labelcolor="#e11d48")
    ax1.grid(True, alpha=.25)
    ax2 = ax1.twinx()
    ax2.plot(t, fum, color="#2563eb", marker="s", ms=4, lw=2, label="Fumaça (índice 0–1)")
    ax2.set_ylabel("Fumaça (0–1)", color="#2563eb")
    ax2.tick_params(axis="y", labelcolor="#2563eb")
    if i_fogo is not None:
        x0 = t[i_fogo]
        ax1.axvline(x0, color="#475569", ls="--", lw=1.3)
        base = min((v for v in temp if v is not None), default=25)
        ax1.annotate("fogo_confirmado=true\n(envio do alerta)",
                     xy=(x0, temp[i_fogo]), xytext=(x0 + 10, base + 3),
                     fontsize=9, color="#334155",
                     arrowprops=dict(arrowstyle="->", color="#475569"))
    ax1.set_title("ESP32-AMZ-01 · Telemetria do sensor de solo (Wokwi) — validação de queimada",
                  fontsize=11, fontweight="bold")
    l1, lab1 = ax1.get_legend_handles_labels()
    l2, lab2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, lab1 + lab2, loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Estado de sessão
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("resumo", None)
ss.setdefault("firms_df", None)
ss.setdefault("firms_msg", None)
ss.setdefault("scenes", None)

# Boot OFFLINE-FIRST: na primeira carga da sessão, alimenta as abas com o que
# já está acumulado no repositório local (sem rede). Sync em tempo real continua
# disponível na barra lateral.
if "boot" not in ss:
    ss.boot = True
    _df = repo.load_fire_foci()
    if not _df.empty:
        ss.firms_df = _df
        ss.firms_msg = f"📂 {len(_df)} focos carregados do repositório local."
    _sc = repo.load_scenes()
    if _sc:
        ss.scenes = _sc

# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------
st.title("🛰️ SENTINELA — Vigilância Orbital Inteligente")
st.caption("Detecção de mineração ilegal e queimadas na Amazônia • "
           "POC FIAP Global Solution 2026.1 — integra visão computacional, "
           "redes neurais, cloud serverless, IoT/ESP32, SQL/NoSQL e dados "
           "públicos reais (Sentinel-2 + NASA FIRMS).")

# ---------------------------------------------------------------------------
# Barra lateral — BOTÕES DE FUNÇÃO
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Funções")

    st.subheader("🗄️ Repositório local (data lake)")
    _rs = repo.stats()
    rc = st.columns(2)
    rc[0].metric("Focos acumulados", _rs["firms_foci"])
    rc[1].metric("Cenas catalogadas", _rs["s2_scenes"])
    if _rs.get("firms_periodo"):
        st.caption(f"Período FIRMS: {_rs['firms_periodo'][0]} → "
                   f"{_rs['firms_periodo'][1]}")
    if _rs.get("last_sync"):
        st.caption(f"Última sync: {_rs['last_sync']} UTC")
    if st.button("🔄 Sincronizar (baixar + agregar)", width="stretch",
                 help="Baixa dados reais agora (FIRMS + Sentinel-2) e os ACUMULA "
                      "no repositório, deduplicando."):
        msgs = []
        with st.spinner("Sincronizando FIRMS + Sentinel-2..."):
            try:
                nf, tf = repo.sync_fire_foci(days=5)
                msgs.append(f"FIRMS +{nf} → {tf}")
            except RuntimeError:
                msgs.append("FIRMS sem chave/rede")
            try:
                nsc, tsc = repo.sync_scenes(max_cloud=30, max_nodata=5, limit=10)
                msgs.append(f"Sentinel-2 +{nsc} → {tsc}")
            except Exception:
                msgs.append("Sentinel-2 offline")
        _df = repo.load_fire_foci()
        if not _df.empty:
            ss.firms_df = _df
            ss.firms_msg = f"📂 {len(_df)} focos no repositório local."
        if repo.load_scenes():
            ss.scenes = repo.load_scenes()
        st.success(" • ".join(msgs))
    if st.button("📂 Usar repositório (offline)", width="stretch",
                 help="Alimenta as abas só com o que já foi acumulado (sem rede)."):
        _df = repo.load_fire_foci()
        ss.firms_df = _df if not _df.empty else None
        ss.firms_msg = (f"📂 {len(_df)} focos do repositório local."
                        if not _df.empty else "Repositório vazio — sincronize.")
        ss.scenes = repo.load_scenes() or None
        st.toast("Carregado do repositório local.")

    st.divider()
    st.subheader("Pipeline de IA")
    usar_keras = st.toggle("Usar CNN/LSTM Keras (se TensorFlow instalado)",
                           value=False,
                           help="Desligado = fallback numpy (roda em qualquer máquina).")
    if st.button("▶️ Executar pipeline completo", type="primary",
                 width="stretch"):
        with st.spinner("Visão → georref → cognitivo → SQL/NoSQL → previsão → "
                        "priorização → rota (GA) → serverless → voz..."):
            ss.resumo = executar_pipeline(treinar_keras=usar_keras)
        st.success(f"{ss.resumo['n_alertas']} alertas gerados.")

    st.divider()
    st.subheader("🛰️ Sentinel-2 (STAC público, sem login)")
    max_cloud = st.slider("Nuvem máx. (%)", 0, 100, 20, 5)
    max_nodata = st.slider("Nodata máx. (%)", 0, 100, 5, 5,
                           help="Baixo = só tiles cheios (evita fragmentos de "
                                "borda quase pretos).")
    n_cenas = st.slider("Nº de cenas", 1, 10, 5)
    if st.button("🔭 Buscar cenas reais", width="stretch"):
        with st.spinner("Consultando Earth-search (Element84/AWS)..."):
            try:
                ss.scenes = _buscar_sentinel2(max_cloud, max_nodata, n_cenas)
            except Exception as exc:  # offline / API fora
                ss.scenes = []
                st.error(f"STAC indisponível: {exc}")

    st.divider()
    st.subheader("🔥 NASA FIRMS (focos reais)")
    map_key = st.text_input("FIRMS_MAP_KEY", type="password",
                            help="Chave gratuita: firms.modaps.eosdis.nasa.gov/api/map_key/")
    dias = st.slider("Janela (dias)", 1, 5, 5)
    if st.button("🔥 Baixar focos de calor", width="stretch"):
        with st.spinner("Consultando NASA FIRMS..."):
            try:
                ss.firms_df = ingest.fetch_fire_foci_firms(
                    days=dias, map_key=(map_key or None))
                ss.firms_msg = f"{len(ss.firms_df)} focos reais na AOI."
            except RuntimeError as exc:
                ss.firms_df = None
                ss.firms_msg = f"FIRMS indisponível → use o demo sintético. {exc}"
    if st.button("🧪 Usar focos sintéticos (offline)", width="stretch"):
        serie = generate_fire_timeseries(days=30)
        ss.firms_df = "synthetic"
        ss.firms_msg = "Série sintética carregada (proxy FIRMS, offline)."

    st.divider()
    if st.button("🗑️ Limpar base SQL/NoSQL", width="stretch"):
        storage.limpar()
        ss.resumo = None
        st.toast("Base limpa.")

# ---------------------------------------------------------------------------
# Métricas-chave
# ---------------------------------------------------------------------------
dets = storage.listar_deteccoes()
alertas = storage.listar_alertas()
crit = sum(1 for a in alertas if a["prioridade"] >= 0.5)

m = st.columns(5)
m[0].metric("Detecções (SQL)", len(dets))
m[1].metric("Alertas", len(alertas))
m[2].metric("Críticos (≥0.5)", crit)
m[3].metric("NoSQL", storage.backend_nosql())
if ss.resumo:
    m[4].metric("Visão", f"acc {ss.resumo['vision_acc']}",
                ss.resumo["vision_backend"])
else:
    m[4].metric("Visão", "—", "rode o pipeline")

# ---------------------------------------------------------------------------
# Abas
# ---------------------------------------------------------------------------
tab_map, tab_s2, tab_firms, tab_ia, tab_cloud = st.tabs(
    ["🗺️ Mapa Operacional", "🛰️ Sentinel-2", "🔥 Focos FIRMS",
     "📈 IA & Previsão", "☁️ Cloud / Telemetria"])

# --- Mapa operacional (pydeck multi-camadas) -------------------------------
with tab_map:
    st.subheader("Mapa operacional — AOI, área protegida, detecções e rota de patrulha")
    layers = [
        pdk.Layer("PolygonLayer", data=[{"polygon": _poly(AOI)}],
                  get_polygon="polygon", stroked=True, filled=False,
                  get_line_color=[255, 255, 255], line_width_min_pixels=2),
        pdk.Layer("PolygonLayer", data=[{"polygon": _poly(AREA_PROTEGIDA)}],
                  get_polygon="polygon", stroked=True, filled=True,
                  get_fill_color=[33, 150, 243, 40],
                  get_line_color=[33, 150, 243], line_width_min_pixels=2),
    ]
    dist = naive = 0.0
    n_rota = 0
    if dets:
        dfd = pd.DataFrame(dets)
        dfd["cor"] = dfd["classe"].map(lambda c: COR_CLASSE.get(c, [200, 200, 0]))
        dfd["raio"] = (3000 + dfd["severidade"] * 9000).astype(float)
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=dfd,
            get_position="[lon, lat]", get_fill_color="cor",
            get_radius="raio", opacity=0.7, pickable=True,
            stroked=True, get_line_color=[0, 0, 0]))

        rota, dist, naive = _rota(_pontos_por_prioridade(dets, alertas))
        n_rota = len(rota)
        if len(rota) >= 2:
            path = [[lon, lat] for lat, lon in rota]
            layers.append(pdk.Layer(
                "PathLayer", data=[{"path": path}], get_path="path",
                get_color=[255, 235, 59], width_min_pixels=3))
            ganho = round(100 * (naive - dist) / naive, 1) if naive else 0.0
            st.info(f"🧬 Rota de patrulha (algoritmo genético): **{dist:.1f} km** "
                    f"vs. ingênua {naive:.1f} km — ganho **{ganho}%** "
                    f"sobre {len(rota)} focos prioritários.")

    # focos FIRMS reais sobrepostos (se baixados)
    if isinstance(ss.firms_df, pd.DataFrame) and not ss.firms_df.empty:
        layers.append(pdk.Layer(
            "HeatmapLayer", data=ss.firms_df,
            get_position="[longitude, latitude]", opacity=0.5,
            get_weight="confidence"))

    st.pydeck_chart(pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=CENTRO["lat"], longitude=CENTRO["lon"], zoom=6.2, pitch=0),
        layers=layers,
        tooltip={"text": "{classe}\nconf {confianca}\n{lat}, {lon}\n"
                         "área {area_ha} ha"}))

    cleg = st.columns(len(COR_CLASSE))
    for i, (cls, rgb) in enumerate(COR_CLASSE.items()):
        cleg[i].markdown(
            f"<span style='color:rgb({rgb[0]},{rgb[1]},{rgb[2]})'>●</span> {cls}",
            unsafe_allow_html=True)

    _painel_decisao(_decisao_mapa(dets, alertas, dist, naive, n_rota))

    if alertas:
        st.subheader("🚨 Alertas priorizados (recomendação preditiva)")
        dfa = pd.DataFrame(alertas)[["prioridade", "mensagem", "status", "ts"]]
        st.dataframe(dfa, width="stretch", hide_index=True)
    else:
        st.info("Sem detecções ainda — clique em **Executar pipeline completo**.")

# --- Sentinel-2 ------------------------------------------------------------
with tab_s2:
    st.subheader("Cenas Sentinel-2 L2A reais sobre a AOI (STAC Earth-search, sem login)")
    st.caption("Fonte pública anônima — COGs no bucket S3 aberto `sentinel-cogs` "
               "(Element84/AWS). Cada cartão é **um tile MGRS (~110 km)**, não a "
               "AOI inteira; o filtro de *nodata* descarta fragmentos de borda. "
               "[FORA DO MATERIAL: Copernicus/Element84.]")
    if ss.scenes is None:
        st.info("Use **🔭 Buscar cenas reais** na barra lateral.")
    elif not ss.scenes:
        st.warning("Nenhuma cena no filtro. Aumente *Nuvem máx.* ou *Nodata máx.*")
    else:
        _painel_decisao(_decisao_s2(ss.scenes))
        for s in ss.scenes:
            c1, c2 = st.columns([1, 3])
            with c1:
                img = _thumb_bytes(s.get("thumbnail"))
                if img:
                    st.image(img, width="stretch")
                else:
                    st.caption("🛰️ prévia indisponível — ver true-color ao lado")
            with c2:
                st.markdown(f"**{s['id']}**")
                nd = s.get("nodata")
                cob = f" • 🟩 cobertura **{100 - nd:.0f}%**" if nd is not None else ""
                st.write(f"📅 {s['datetime']}  •  ☁️ nuvem **{s['cloud']}%**{cob}")
                if s.get("visual"):
                    st.markdown(f"[true-color (COG GeoTIFF)]({s['visual']})")
            st.divider()
        st.caption("Dica: baixe um true-color do Copernicus Browser e use "
                   "`data.ingest.load_scene_from_image()` para rodar a CNN sobre "
                   "pixels reais.")

# --- FIRMS -----------------------------------------------------------------
with tab_firms:
    st.subheader("Focos de calor — NASA FIRMS (VIIRS 375 m)")
    if ss.firms_msg:
        (st.success if isinstance(ss.firms_df, pd.DataFrame) else st.warning)(ss.firms_msg)

    if isinstance(ss.firms_df, pd.DataFrame) and not ss.firms_df.empty:
        df = ss.firms_df
        c1, c2, c3 = st.columns(3)
        c1.metric("Focos na AOI", len(df))
        c2.metric("Confiança média", f"{df['confidence'].mean():.2f}")
        c3.metric("FRP média (MW)", f"{pd.to_numeric(df['frp'], errors='coerce').mean():.1f}")
        st.map(df.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
        st.dataframe(df, width="stretch", hide_index=True)

        serie = ingest.fire_foci_to_timeseries(df, fill_days=30)
        _painel_decisao(_decisao_firms(df, serie))
        st.subheader("📈 Série diária de focos (alimenta a previsão LSTM/AR)")
        st.bar_chart(pd.Series(serie, name="focos/dia"))
        grid = ingest.fire_foci_to_grid(df)
        st.subheader("🔢 Grade FIRMS × célula da cena (cruzamento multi-fonte)")
        st.dataframe(pd.DataFrame(grid), width="stretch")
    elif ss.firms_df == "synthetic":
        serie = generate_fire_timeseries(days=30)
        st.bar_chart(pd.Series(serie, name="focos/dia (sintético)"))
    else:
        st.info("Use **🔥 Baixar focos de calor** (com MAP_KEY) ou "
                "**🧪 Usar focos sintéticos** na barra lateral.")

# --- IA & Previsão ---------------------------------------------------------
with tab_ia:
    st.subheader("📈 Previsão de focos de calor — 7 dias")
    src = (ss.firms_df if isinstance(ss.firms_df, pd.DataFrame)
           and not ss.firms_df.empty else None)
    if src is not None:
        serie = ingest.fire_foci_to_timeseries(src, fill_days=60)
        origem = "NASA FIRMS (real)"
    else:
        serie = generate_fire_timeseries(days=180)
        origem = "sintético (offline)"
    serie = np.asarray(serie, dtype=float)
    if len(serie) >= 20:
        fm = ForecastModel(look_back=14, force_light=not usar_keras)
        fm.fit(serie, verbose=0)
        fc = fm.forecast(serie, horizon=7)
        hist = pd.concat([pd.Series(serie), pd.Series([None] * 7)],
                         ignore_index=True)
        prev = pd.Series([None] * len(serie) + list(fc))
        st.caption(f"Fonte da série: **{origem}** • backend **{fm.backend}** • "
                   f"tendência {tendencia(fc):+.3f}")
        st.line_chart(pd.DataFrame({"histórico": hist, "previsão (7d)": prev}))
        _painel_decisao(_decisao_ia(serie, fc, origem))
    else:
        st.warning("Série curta demais para prever (mín. 20 pontos).")

    if ss.resumo:
        st.subheader("🧠 Resumo do último pipeline")
        r = ss.resumo
        cc = st.columns(4)
        cc[0].metric("Visão (acc)", r["vision_acc"], r["vision_backend"])
        cc[1].metric("Detecções", r["n_deteccoes"])
        cc[2].metric("Rota GA", f"{r['rota_dist_km']} km", f"ganho {r['rota_ganho_pct']}%")
        cc[3].metric("Lambda / SNS", f"{r['lambda_invocacoes']} / {r['sns_notificacoes']}")
        if r["voz"]["path"]:
            st.audio(r["voz"]["path"])
            st.caption(f"🔊 Alerta por voz ({r['voz']['engine']}) para o foco de maior prioridade.")

# --- Cloud / Telemetria ----------------------------------------------------
with tab_cloud:
    st.subheader("☁️ Orquestração serverless (mock AWS Lambda/SNS/SQS/CloudWatch)")
    if ss.resumo:
        r = ss.resumo
        cc = st.columns(3)
        cc[0].metric("Invocações Lambda (CloudWatch)", r["lambda_invocacoes"])
        cc[1].metric("Notificações SNS", r["sns_notificacoes"])
        cc[2].metric("NoSQL backend", r["nosql"])
    else:
        st.info("Rode o pipeline para popular o log serverless.")

    tel = storage.listar_telemetria()
    _painel_decisao(_decisao_cloud(ss.resumo, tel))

    st.subheader("📈 Telemetria do sensor ESP32 — temperatura × fumaça")
    _figt = _fig_telemetria_esp32()
    if _figt is not None:
        st.pyplot(_figt, use_container_width=True)
        st.caption("Feed real do sensor de campo (esp32/telemetria_simulada.jsonl). "
                   "A linha tracejada marca **fogo_confirmado=true** → envio do alerta.")
    else:
        st.caption("Telemetria do ESP32 indisponível — rode `python esp32/gerar_telemetria.py`.")

    st.subheader("📡 Telemetria de campo — IoT/ESP32 (NoSQL)")
    st.dataframe(pd.DataFrame(tel) if tel
                 else pd.DataFrame([{"info": "sem leituras — rode o pipeline"}]),
                 width="stretch", hide_index=True)

    st.subheader("🗃️ Detecções persistidas (SQLite)")
    st.dataframe(pd.DataFrame(dets) if dets
                 else pd.DataFrame([{"info": "sem detecções"}]),
                 width="stretch", hide_index=True)
