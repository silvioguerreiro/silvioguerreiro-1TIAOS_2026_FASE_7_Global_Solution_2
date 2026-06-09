"""
SENTINELA - Repositório local de DADOS REAIS (data lake incremental).

Acumula em disco os dados públicos baixados (NASA FIRMS + Sentinel-2 STAC),
deduplicando, para que a solução rode OFFLINE-FIRST e fique mais rica a cada
sincronização — mantendo a opção de buscar em tempo real (data/ingest.py).

Fluxo:
  • sync_*()  -> baixa em TEMPO REAL via ingest e AGREGA ao repositório (dedup).
  • load_*()  -> lê o que já foi acumulado (sem rede); alimenta forecast/visão.
  • stats()   -> contagens, período coberto e última sincronização.

Layout (em src/data/lake/, versionável — viaja com a entrega):
  firms_foci.parquet  - focos de calor acumulados (dedup por posição/data/sat)
  s2_scenes.json      - metadados de cenas Sentinel-2 (dedup por id)
  manifest.json       - estatísticas e carimbo da última sincronização

[FORA DO MATERIAL: NASA FIRMS, Copernicus/Element84 são fontes externas.]
"""
import json
import datetime as dt

import pandas as pd

from config import LAKE_DIR
from data import ingest

FIRMS_STORE = LAKE_DIR / "firms_foci.parquet"
SCENES_STORE = LAKE_DIR / "s2_scenes.json"
MANIFEST = LAKE_DIR / "manifest.json"

# Chaves de deduplicação dos focos (duas linhas idênticas nelas = mesmo foco).
_FIRMS_DEDUP = ["latitude", "longitude", "acq_date", "satellite", "frp",
                "confidence"]
_FIRMS_COLS = ["latitude", "longitude", "acq_date", "confidence", "frp",
               "satellite"]


def _now_iso():
    return (dt.datetime.now(dt.timezone.utc)
            .replace(tzinfo=None).isoformat(timespec="seconds"))


def _ensure_dir():
    LAKE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# NASA FIRMS - focos de calor acumulados
# ---------------------------------------------------------------------------
def load_fire_foci():
    """DataFrame com todos os focos já acumulados (vazio se o lake não existe)."""
    if FIRMS_STORE.exists():
        return pd.read_parquet(FIRMS_STORE)
    return pd.DataFrame(columns=_FIRMS_COLS)


def append_fire_foci(df):
    """Funde novos focos ao repositório, deduplicando. Retorna nº de linhas novas."""
    if df is None or df.empty:
        return 0
    _ensure_dir()
    atual = load_fire_foci()
    antes = len(atual)
    combinado = pd.concat([atual, df], ignore_index=True)
    keys = [c for c in _FIRMS_DEDUP if c in combinado.columns]
    combinado = combinado.drop_duplicates(subset=keys).reset_index(drop=True)
    combinado.to_parquet(FIRMS_STORE, index=False)
    _touch_manifest()
    return len(combinado) - antes


def sync_fire_foci(map_key=None, days=5, source=ingest.FIRMS_SOURCE, bbox=None):
    """Baixa focos reais (tempo real) e os agrega ao repositório.
    Retorna (novos, total_acumulado). Propaga RuntimeError se faltar chave/rede."""
    df = ingest.fetch_fire_foci_firms(bbox=bbox, days=days, source=source,
                                      map_key=map_key)
    novos = append_fire_foci(df)
    return novos, len(load_fire_foci())


def fire_foci_timeseries(fill_days=None):
    """Série diária de focos acumulados, pronta p/ core.forecast.ForecastModel."""
    return ingest.fire_foci_to_timeseries(load_fire_foci(), fill_days=fill_days)


# ---------------------------------------------------------------------------
# Sentinel-2 - metadados de cenas acumulados
# ---------------------------------------------------------------------------
def load_scenes():
    """Lista de cenas Sentinel-2 já catalogadas (vazia se o lake não existe)."""
    if SCENES_STORE.exists():
        try:
            return json.loads(SCENES_STORE.read_text())
        except (ValueError, OSError):
            return []
    return []


def append_scenes(scenes):
    """Funde cenas ao catálogo, deduplicando por id. Retorna nº de cenas novas."""
    if not scenes:
        return 0
    _ensure_dir()
    catalogo = {s["id"]: s for s in load_scenes() if s.get("id")}
    antes = len(catalogo)
    for s in scenes:
        if s.get("id"):
            catalogo[s["id"]] = s          # atualiza/insere
    out = sorted(catalogo.values(),
                 key=lambda s: (s.get("datetime") or ""), reverse=True)
    SCENES_STORE.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    _touch_manifest()
    return len(catalogo) - antes


def sync_scenes(bbox=None, max_cloud=20, max_nodata=5, limit=10):
    """Consulta a STAC pública (tempo real) e agrega as cenas ao catálogo.
    Retorna (novas, total_catalogado)."""
    scenes = ingest.search_sentinel2_scenes(
        bbox=bbox, max_cloud=max_cloud, max_nodata=max_nodata, limit=limit)
    novas = append_scenes(scenes)
    return novas, len(load_scenes())


# ---------------------------------------------------------------------------
# Manifesto / estatísticas
# ---------------------------------------------------------------------------
def stats():
    """Resumo do repositório: contagens, período FIRMS e última sincronização."""
    base = {}
    if MANIFEST.exists():
        try:
            base = json.loads(MANIFEST.read_text())
        except (ValueError, OSError):
            base = {}
    df = load_fire_foci()
    out = {
        "firms_foci": int(len(df)),
        "s2_scenes": len(load_scenes()),
        "last_sync": base.get("last_sync"),
        "firms_periodo": None,
    }
    if not df.empty and "acq_date" in df.columns:
        datas = pd.to_datetime(df["acq_date"], errors="coerce").dropna()
        if len(datas):
            out["firms_periodo"] = [str(datas.min().date()),
                                    str(datas.max().date())]
    return out


def _touch_manifest():
    _ensure_dir()
    m = stats()
    m["last_sync"] = _now_iso()
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI: sincroniza (baixa + agrega) e imprime o estado do repositório
# ---------------------------------------------------------------------------
def _cli():
    print("=" * 60)
    print(" SENTINELA - REPOSITÓRIO LOCAL (data lake) - SINCRONIZAÇÃO")
    print("=" * 60)
    try:
        novos, total = sync_fire_foci(days=5)
        print(f" FIRMS: +{novos} focos novos -> {total} acumulados.")
    except RuntimeError as exc:
        print(f" FIRMS indisponível (sem chave/rede): {exc}")
    try:
        novas, total = sync_scenes(limit=10)
        print(f" Sentinel-2: +{novas} cenas novas -> {total} catalogadas.")
    except Exception as exc:  # offline
        print(f" Sentinel-2 STAC indisponível: {exc}")
    print("-" * 60)
    print(" Estado:", json.dumps(stats(), ensure_ascii=False))


if __name__ == "__main__":
    _cli()
