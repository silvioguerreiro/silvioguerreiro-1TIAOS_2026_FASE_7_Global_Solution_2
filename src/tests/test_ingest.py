"""
Testes do módulo de ingestão de dados reais (data/ingest.py).
Todos OFFLINE: validam parsing/normalização/tiling sem tocar a rede.
O último teste é de INTEGRAÇÃO: imagem real -> cells -> detectar_cena.
"""
import numpy as np
import pandas as pd

from config import SCENE_GRID, IMG_SIZE, AOI
from data import ingest


# CSV de exemplo no formato da Area API do FIRMS (VIIRS: confiança l/n/h)
FIRMS_VIIRS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-7.5,-63.2,330.1,0.4,0.36,2026-06-01,1715,N,VIIRS,h,2.0NRT,295.0,12.5,D\n"
    "-8.1,-61.7,310.0,0.4,0.36,2026-06-01,1716,N,VIIRS,n,2.0NRT,290.0,5.1,D\n"
    "-6.9,-64.0,300.0,0.4,0.36,2026-06-02,1700,N,VIIRS,l,2.0NRT,288.0,1.0,D\n"
)

# CSV no formato MODIS (confiança 0-100)
FIRMS_MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
    "confidence,version,bright_t31,frp,daynight\n"
    "-7.0,-62.0,320.0,1.0,1.0,2026-06-01,1730,Terra,82,6.1NRT,300.0,20.0,D\n"
)


def test_aoi_to_bbox_ordem_WSEN():
    w, s, e, n = ingest.aoi_to_bbox()
    assert (w, s, e, n) == (AOI["lon_min"], AOI["lat_min"],
                            AOI["lon_max"], AOI["lat_max"])
    assert w < e and s < n


def test_firms_url_formato():
    url = ingest._firms_url((-65, -10, -60, -5), days=3,
                            source="VIIRS_SNPP_NRT", map_key="ABC123")
    assert url.endswith("/VIIRS_SNPP_NRT/-65,-10,-60,-5/3")
    assert "ABC123" in url


def test_firms_url_clamp_dias():
    # Area API aceita 1..5; valores fora da faixa são ajustados
    assert ingest._firms_url((0, 0, 1, 1), 99, "S", "K").endswith("/5")
    assert ingest._firms_url((0, 0, 1, 1), 0, "S", "K").endswith("/1")


def test_parse_firms_viirs_confianca_categorica():
    df = ingest._parse_firms_csv(FIRMS_VIIRS_CSV)
    assert len(df) == 3
    # h/n/l -> 0.90/0.60/0.25
    assert df["confidence"].tolist() == [0.90, 0.60, 0.25]
    assert {"latitude", "longitude", "acq_date", "frp"} <= set(df.columns)


def test_parse_firms_modis_confianca_numerica():
    df = ingest._parse_firms_csv(FIRMS_MODIS_CSV)
    assert len(df) == 1
    assert abs(df["confidence"].iloc[0] - 0.82) < 1e-9


def test_parse_firms_vazio():
    df = ingest._parse_firms_csv("latitude,longitude,acq_date\n")
    assert df.empty


def test_fire_foci_to_timeseries_agrega_por_dia():
    df = ingest._parse_firms_csv(FIRMS_VIIRS_CSV)
    serie = ingest.fire_foci_to_timeseries(df)
    # 2 focos em 2026-06-01, 1 em 2026-06-02 -> [2, 1]
    assert serie.tolist() == [2.0, 1.0]


def test_fire_foci_to_timeseries_fill_days():
    df = ingest._parse_firms_csv(FIRMS_VIIRS_CSV)
    serie = ingest.fire_foci_to_timeseries(df, fill_days=5)
    assert len(serie) == 5
    assert serie[:3].tolist() == [0.0, 0.0, 0.0]


def test_fire_foci_to_grid_dentro_da_aoi():
    df = ingest._parse_firms_csv(FIRMS_VIIRS_CSV)
    g = ingest.fire_foci_to_grid(df, grid=SCENE_GRID)
    assert g.shape == (SCENE_GRID, SCENE_GRID)
    # todos os 3 focos estão dentro da AOI -> soma == 3
    assert int(g.sum()) == 3


def test_fire_foci_to_grid_fora_da_aoi_ignorado():
    df = pd.DataFrame({"latitude": [0.0], "longitude": [0.0],  # fora da Amazônia
                       "acq_date": ["2026-06-01"], "confidence": [0.9],
                       "frp": [1.0], "satellite": ["x"]})
    g = ingest.fire_foci_to_grid(df, grid=SCENE_GRID)
    assert int(g.sum()) == 0


def test_tile_image_to_cells_shape_e_intervalo():
    rng = np.random.default_rng(0)
    img = (rng.random((200, 240, 3)) * 255).astype(np.uint8)  # não-quadrada
    scene, cells = ingest.tile_image_to_cells(img, grid=SCENE_GRID,
                                              img_size=IMG_SIZE)
    assert cells.shape == (SCENE_GRID, SCENE_GRID, IMG_SIZE, IMG_SIZE, 3)
    assert scene.shape == (SCENE_GRID * IMG_SIZE, SCENE_GRID * IMG_SIZE, 3)
    assert cells.dtype == np.float32
    assert 0.0 <= cells.min() and cells.max() <= 1.0


def test_tile_image_grayscale_para_rgb():
    img = np.full((100, 100), 0.5, dtype=np.float32)  # 1 canal
    _, cells = ingest.tile_image_to_cells(img)
    assert cells.shape[-1] == 3


def test_integracao_imagem_real_para_detector(tmp_path):
    """Imagem salva em disco -> load_scene_from_image -> detectar_cena roda."""
    from core.vision import VisionModel, detectar_cena
    from data.synthetic import generate_landuse_dataset
    import cv2

    # cria uma "imagem de satélite" e grava como PNG real
    rng = np.random.default_rng(1)
    img = (rng.random((256, 256, 3)) * 255).astype(np.uint8)
    p = tmp_path / "cena_sat.png"
    cv2.imwrite(str(p), img)

    scene, cells = ingest.load_scene_from_image(str(p))
    assert cells.shape == (SCENE_GRID, SCENE_GRID, IMG_SIZE, IMG_SIZE, 3)

    # detector treinado no fallback leve roda sobre os pixels reais
    X, y = generate_landuse_dataset(n_per_class=12, seed=3)
    vm = VisionModel(force_light=True)
    vm.train(X, y)
    dets = detectar_cena(vm, cells)
    assert len(dets) == SCENE_GRID * SCENE_GRID
    assert {"row", "col", "classe", "confianca"} <= set(dets[0].keys())
