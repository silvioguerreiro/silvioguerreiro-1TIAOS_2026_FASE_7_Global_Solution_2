"""
SENTINELA - Ingestão de DADOS PÚBLICOS REAIS (contraparte do data/synthetic.py).

Este módulo conecta o MVP a fontes abertas e citáveis, alimentando os mesmos
componentes já existentes do pipeline:

  - Focos de calor (queimadas)  -> NASA FIRMS (VIIRS/MODIS) por bounding box
        alimenta core.forecast.ForecastModel (série temporal) e cruza com a cena.
  - Cena orbital (uso do solo)  -> Sentinel-2 (Copernicus / Earth-search STAC)
        a imagem real (true-color) vira o array `cells` consumido por
        core.vision.detectar_cena -> mesma CNN/fallback do projeto.

Eixos das disciplinas:
  * Engenharia de Dados (F7) ... ingestão por API, parsing, agregação.
  * Visão Computacional (F6) ... imagem real tile-ada para a CNN.
  * Cloud/AWS (F5) ............. Sentinel-2 é servido como COG em bucket S3
                                público (Earth-search/Element84), STAC API.

O QUE É FUNCIONAL (roda de verdade):
  - fetch_fire_foci_firms(): baixa CSV real da API FIRMS (precisa de MAP_KEY
    gratuito). Sem chave/rede -> erro claro e o demo cai no synthetic.
  - search_sentinel2_scenes(): consulta STAC pública (sem login) e retorna
    cenas reais sobre a AOI (id, data, nuvens, link da imagem true-color).
  - load_scene_from_image(): lê uma imagem real exportada do Copernicus Browser
    e a converte em `cells` -> detectar_cena roda sobre pixels reais.

O QUE É SIMULADO / PRÓXIMO PASSO:
  - Download automático dos pixels do COG por janela geográfica exige rasterio
    (GDAL). Mantemos o caminho leve (exportar a imagem pelo Browser) para a POC;
    o método para evoluir está documentado em scripts/README.md.

[FORA DO MATERIAL: NASA FIRMS, Copernicus/Element84 são fontes externas.]
Refs:
  FIRMS Area API .. https://firms.modaps.eosdis.nasa.gov/api/area/
  Earth-search ... https://earth-search.aws.element84.com/v1/
  Copernicus ..... https://dataspace.copernicus.eu/
"""
import io
import os
import ssl
import json
import urllib.request
import urllib.error

import numpy as np
import pandas as pd


def _make_ssl_context():
    """Contexto SSL com CA bundle do `certifi`, quando disponível.

    O Python.framework do macOS frequentemente não tem os certificados CA do
    sistema instalados, o que faz toda chamada HTTPS (STAC/COG) falhar com
    CERTIFICATE_VERIFY_FAILED — e, no dashboard, as miniaturas Sentinel-2
    simplesmente não aparecem. Usar o bundle do `certifi` (dependência já
    presente via requests) resolve de forma portável; sem ele, cai no contexto
    padrão do sistema.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# Reutilizado por todas as chamadas HTTPS deste módulo (e pelo dashboard).
SSL_CONTEXT = _make_ssl_context()

try:
    from config import AOI, IMG_SIZE, SCENE_GRID
except ModuleNotFoundError:  # permite rodar como script: python data/ingest.py
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import AOI, IMG_SIZE, SCENE_GRID

# ----------------------------------------------------------------------------
# Endpoints (constantes)
# ----------------------------------------------------------------------------
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
# Fonte padrão de focos: VIIRS S-NPP NRT (375 m). Alternativas:
#   VIIRS_NOAA20_NRT, VIIRS_NOAA21_NRT, MODIS_NRT, e variantes *_SP (arquivo).
FIRMS_SOURCE = "VIIRS_SNPP_NRT"
STAC_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
STAC_COLLECTION = "sentinel-2-l2a"

# Mapa confiança VIIRS (categórica) -> escala 0-1 usada no projeto.
_VIIRS_CONF = {"l": 0.25, "n": 0.60, "h": 0.90}


# ----------------------------------------------------------------------------
# Helpers geográficos
# ----------------------------------------------------------------------------
def aoi_to_bbox(aoi=AOI):
    """AOI (dict) -> bbox (lon_min, lat_min, lon_max, lat_max) = (W, S, E, N)."""
    return (aoi["lon_min"], aoi["lat_min"], aoi["lon_max"], aoi["lat_max"])


def _firms_url(bbox, days, source, map_key):
    """Monta a URL da Area API do FIRMS. AREA = 'W,S,E,N'."""
    w, s, e, n = bbox
    area = f"{w},{s},{e},{n}"
    days = max(1, min(int(days), 5))    # Area API aceita 1..5 dias (NRT)
    return f"{FIRMS_BASE}/{map_key}/{source}/{area}/{days}"


def _http_get(url, timeout=30):
    """GET simples via stdlib (sem dependências externas)."""
    req = urllib.request.Request(url, headers={"User-Agent": "SENTINELA/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _http_post_json(url, body, timeout=30):
    """POST JSON via stdlib; retorna dict."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "SENTINELA/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ----------------------------------------------------------------------------
# 1) NASA FIRMS - focos de calor (FUNCIONAL com MAP_KEY gratuito)
# ----------------------------------------------------------------------------
def _normalize_confidence(serie):
    """Confiança FIRMS -> float 0-1. VIIRS usa l/n/h; MODIS usa 0-100."""
    def conv(v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v in _VIIRS_CONF:
                return _VIIRS_CONF[v]
            try:
                return float(v) / 100.0
            except ValueError:
                return np.nan
        try:
            return float(v) / 100.0
        except (TypeError, ValueError):
            return np.nan
    return serie.map(conv)


def _parse_firms_csv(text):
    """
    CSV (string) da API FIRMS -> DataFrame normalizado.
    Colunas garantidas: latitude, longitude, acq_date, confidence(0-1), frp,
    satellite. Isolado da rede para ser testável.
    """
    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        return pd.DataFrame(
            columns=["latitude", "longitude", "acq_date", "confidence",
                     "frp", "satellite"])
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    if "confidence" in df.columns:
        df["confidence"] = _normalize_confidence(df["confidence"])
    else:
        df["confidence"] = np.nan
    if "frp" not in df.columns:
        df["frp"] = np.nan
    if "satellite" not in df.columns:
        df["satellite"] = FIRMS_SOURCE
    cols = ["latitude", "longitude", "acq_date", "confidence", "frp", "satellite"]
    return df[[c for c in cols if c in df.columns]].dropna(
        subset=["latitude", "longitude"]).reset_index(drop=True)


def fetch_fire_foci_firms(bbox=None, days=1, source=FIRMS_SOURCE,
                          map_key=None, timeout=30):
    """
    Baixa focos de calor reais da NASA FIRMS dentro do bounding box.

    map_key: chave gratuita (https://firms.modaps.eosdis.nasa.gov/api/map_key/).
             Se None, lê de os.environ['FIRMS_MAP_KEY'].
    Retorna DataFrame normalizado. Lança RuntimeError se faltar chave/rede,
    para o chamador decidir o fallback (synthetic) de forma explícita.
    """
    bbox = bbox or aoi_to_bbox()
    map_key = map_key or os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not map_key:
        raise RuntimeError(
            "FIRMS_MAP_KEY ausente. Gere uma chave gratuita em "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ e exporte "
            "FIRMS_MAP_KEY=<sua_chave>.")
    url = _firms_url(bbox, days, source, map_key)
    try:
        text = _http_get(url, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RuntimeError(f"Falha ao consultar FIRMS: {exc}") from exc
    if text.lstrip().lower().startswith(("invalid", "error")):
        raise RuntimeError(f"Resposta inválida do FIRMS: {text[:120]}")
    return _parse_firms_csv(text)


def fire_foci_to_timeseries(df, fill_days=None):
    """
    Agrega focos por dia -> np.array (proxy real para generate_fire_timeseries).
    Pronto para core.forecast.ForecastModel.fit().
    """
    if df is None or df.empty or "acq_date" not in df.columns:
        return np.zeros(0, dtype=float)
    counts = (df.assign(acq_date=pd.to_datetime(df["acq_date"], errors="coerce"))
                .dropna(subset=["acq_date"])
                .groupby(df["acq_date"].values).size())
    serie = counts.sort_index().to_numpy(dtype=float)
    if fill_days and len(serie) < fill_days:
        serie = np.concatenate([np.zeros(fill_days - len(serie)), serie])
    return serie


def fire_foci_to_grid(df, grid=SCENE_GRID, aoi=AOI):
    """
    Conta focos por célula da grade da cena (mesma AOI da visão computacional).
    Cruza FIRMS com as detecções da CNN -> confirmação multi-fonte de queimada.
    Retorna matriz (grid, grid) int.
    """
    g = np.zeros((grid, grid), dtype=int)
    if df is None or df.empty:
        return g
    dlat = aoi["lat_max"] - aoi["lat_min"]
    dlon = aoi["lon_max"] - aoi["lon_min"]
    for lat, lon in zip(df["latitude"], df["longitude"]):
        if not (aoi["lat_min"] <= lat <= aoi["lat_max"]
                and aoi["lon_min"] <= lon <= aoi["lon_max"]):
            continue
        row = int((aoi["lat_max"] - lat) / dlat * grid)
        col = int((lon - aoi["lon_min"]) / dlon * grid)
        row = min(max(row, 0), grid - 1)
        col = min(max(col, 0), grid - 1)
        g[row, col] += 1
    return g


# ----------------------------------------------------------------------------
# 2) Sentinel-2 - busca de cenas reais via STAC (FUNCIONAL, sem login)
# ----------------------------------------------------------------------------
def search_sentinel2_scenes(bbox=None, start=None, end=None,
                            max_cloud=20, max_nodata=5, limit=5, timeout=30):
    """
    Consulta a STAC pública Earth-search (Element84/AWS) por cenas Sentinel-2 L2A
    sobre a AOI, ordenadas pela menor cobertura de nuvens.

    IMPORTANTE: a Earth-search é ANÔNIMA (sem login) e indexa *tiles* MGRS
    individuais (~110 km). Tiles na borda da faixa orbital são preenchidos só
    parcialmente; ordenar apenas por nuvem traz "slivers" com ~98% de nodata
    (thumbnail quase todo preto). Por isso filtramos por nodata baixo
    (`max_nodata`) para retornar apenas tiles cheios e visualmente úteis.

    Retorna lista de dicts: {id, datetime, cloud, nodata, bbox, thumbnail,
    visual}, onde 'visual' é o COG true-color (RGB) pronto p/ inspeção/recorte.
    """
    bbox = list(bbox or aoi_to_bbox())
    query = {"eo:cloud_cover": {"lt": float(max_cloud)}}
    if max_nodata is not None:
        query["s2:nodata_pixel_percentage"] = {"lt": float(max_nodata)}
    body = {
        "collections": [STAC_COLLECTION],
        "bbox": bbox,
        "limit": int(limit),
        "query": query,
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    }
    if start and end:
        body["datetime"] = f"{start}/{end}"
    feats = _http_post_json(STAC_SEARCH_URL, body, timeout=timeout).get(
        "features", [])
    out = []
    for f in feats:
        props = f.get("properties", {})
        assets = f.get("assets", {})
        out.append({
            "id": f.get("id"),
            "datetime": props.get("datetime"),
            "cloud": props.get("eo:cloud_cover"),
            "nodata": props.get("s2:nodata_pixel_percentage"),
            "bbox": f.get("bbox"),
            "thumbnail": (assets.get("thumbnail") or {}).get("href"),
            "visual": (assets.get("visual") or {}).get("href"),
        })
    return out


# ----------------------------------------------------------------------------
# 3) Imagem real -> array `cells` para a CNN (FUNCIONAL)
# ----------------------------------------------------------------------------
def _read_rgb(path):
    """Lê imagem RGB float32 [0,1]. Usa OpenCV; cai para Pillow se faltar."""
    try:
        import cv2
        bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if bgr is None:
            raise IOError(f"Não foi possível ler a imagem: {path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    except ImportError:
        from PIL import Image
        rgb = np.array(Image.open(path).convert("RGB"))
    return rgb.astype(np.float32) / 255.0


def _resize(img, size):
    """Redimensiona (H,W,3) -> (size,size,3). OpenCV -> Pillow -> vizinho."""
    try:
        import cv2
        return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    except ImportError:
        pass
    try:
        from PIL import Image
        arr = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        im = Image.fromarray(arr).resize((size, size), Image.BILINEAR)
        return np.asarray(im, dtype=np.float32) / 255.0
    except ImportError:
        h, w = img.shape[:2]
        ri = (np.linspace(0, h - 1, size)).astype(int)
        ci = (np.linspace(0, w - 1, size)).astype(int)
        return img[np.ix_(ri, ci)]


def tile_image_to_cells(img_rgb, grid=SCENE_GRID, img_size=IMG_SIZE):
    """
    Converte uma imagem RGB real na grade que o detector consome.

    Passos: center-crop quadrado -> resize p/ (grid*img_size) -> fatiar em
    grid x grid patches de img_size. Retorna:
      scene (H,W,3), cells (grid,grid,img_size,img_size,3) float32 [0,1].
    """
    img = np.asarray(img_rgb, dtype=np.float32)
    if img.max() > 1.0:
        img = img / 255.0
    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    img = img[:, :, :3]
    h, w = img.shape[:2]
    side = min(h, w)
    top, left = (h - side) // 2, (w - side) // 2
    img = img[top:top + side, left:left + side]      # quadrado central
    full = grid * img_size
    scene = _resize(img, full)
    cells = np.zeros((grid, grid, img_size, img_size, 3), dtype=np.float32)
    for r in range(grid):
        for c in range(grid):
            cells[r, c] = scene[r * img_size:(r + 1) * img_size,
                                c * img_size:(c + 1) * img_size, :]
    return scene.astype(np.float32), cells


def load_scene_from_image(path, grid=SCENE_GRID, img_size=IMG_SIZE):
    """
    Lê uma imagem real (ex.: true-color Sentinel-2 exportada do Copernicus
    Browser, .png/.jpg/.tif) e devolve (scene, cells) prontos p/ detectar_cena.
    """
    rgb = _read_rgb(path)
    return tile_image_to_cells(rgb, grid=grid, img_size=img_size)


# ----------------------------------------------------------------------------
# Demo de linha de comando
# ----------------------------------------------------------------------------
def _demo(image_path=None):
    bbox = aoi_to_bbox()
    print("=" * 60)
    print(" SENTINELA - INGESTÃO DE DADOS PÚBLICOS REAIS")
    print("=" * 60)
    print(f" AOI bbox (W,S,E,N) : {bbox}")

    # --- FIRMS (focos) ---
    try:
        df = fetch_fire_foci_firms(bbox=bbox, days=2)
        print(f" FIRMS focos (2 dias): {len(df)} pontos reais")
        if not df.empty:
            print(df.head(3).to_string(index=False))
        serie = fire_foci_to_timeseries(df)
        print(f" Série diária (proxy forecast): {serie.tolist()}")
    except RuntimeError as exc:
        print(f" FIRMS indisponível -> fallback synthetic. Motivo: {exc}")

    # --- Sentinel-2 (busca STAC) ---
    try:
        cenas = search_sentinel2_scenes(bbox=bbox, max_cloud=20, limit=3)
        print(f"\n Sentinel-2 (STAC) cenas com menor nuvem:")
        for s in cenas:
            print(f"   {s['datetime']}  nuvem={s['cloud']}%  id={s['id']}")
            print(f"      true-color: {s['visual']}")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f" STAC indisponível (offline?). Motivo: {exc}")

    # --- Imagem real -> cells ---
    if image_path:
        scene, cells = load_scene_from_image(image_path)
        print(f"\n Imagem '{image_path}' -> cells {cells.shape} "
              f"(scene {scene.shape}). Pronto p/ detectar_cena().")


if __name__ == "__main__":
    import sys
    img = None
    if "--image" in sys.argv:
        img = sys.argv[sys.argv.index("--image") + 1]
    _demo(image_path=img)
