"""
Gerador de dados sintéticos para demonstração offline.
Em produção, estes geradores são substituídos por dados públicos reais:
  - Patches de uso do solo: EuroSAT / Sentinel-2 / recortes da Amazônia (PRODES/DETER)
  - Série de focos de calor: NASA FIRMS (VIIRS/MODIS)
Os patches sintéticos têm assinaturas de cor/textura separáveis por classe,
o que permite que a CNN (ou o fallback) aprenda de fato. [FORA DO MATERIAL: fontes reais]
"""
import numpy as np
from config import CLASSES, IMG_SIZE, SCENE_GRID

# Assinatura RGB média (0-1) de cada classe
_PALETTE = {
    "floresta":  (0.10, 0.45, 0.12),
    "agua":      (0.07, 0.20, 0.55),
    "mineracao": (0.62, 0.50, 0.32),   # solo exposto / lama de garimpo
    "queimada":  (0.30, 0.10, 0.06),   # cicatriz de queima
    "urbano":    (0.55, 0.55, 0.58),   # cinza
}


def _make_patch(rng, classe, size):
    base = np.array(_PALETTE[classe], dtype=np.float32)
    img = np.ones((size, size, 3), dtype=np.float32) * base
    # textura específica por classe
    if classe == "floresta":
        img += rng.normal(0, 0.06, img.shape).astype(np.float32)  # canopy granular
    elif classe == "agua":
        img += rng.normal(0, 0.02, img.shape).astype(np.float32)  # liso
    elif classe == "mineracao":
        # manchas claras de solo exposto
        for _ in range(rng.integers(3, 7)):
            r, c = rng.integers(0, size, 2)
            img[max(0, r-3):r+3, max(0, c-3):c+3] = (0.80, 0.72, 0.55)
        img += rng.normal(0, 0.05, img.shape).astype(np.float32)
    elif classe == "queimada":
        # pontos pretos de char + fumaça acinzentada
        mask = rng.random((size, size)) < 0.15
        img[mask] = (0.05, 0.05, 0.05)
        img += rng.normal(0, 0.05, img.shape).astype(np.float32)
    elif classe == "urbano":
        # grade (ruas)
        img[::6, :] = (0.30, 0.30, 0.30)
        img[:, ::6] = (0.30, 0.30, 0.30)
        img += rng.normal(0, 0.04, img.shape).astype(np.float32)
    return np.clip(img, 0.0, 1.0)


def generate_landuse_dataset(n_per_class=80, img_size=IMG_SIZE, seed=42):
    """Retorna X (N,H,W,3) float32 [0,1] e y (N,) int. Classes balanceadas."""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for idx, classe in enumerate(CLASSES):
        for _ in range(n_per_class):
            X.append(_make_patch(rng, classe, img_size))
            y.append(idx)
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int64)
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


def generate_scene(grid=SCENE_GRID, img_size=IMG_SIZE, seed=7):
    """
    Monta uma 'cena' orbital como grade grid x grid de patches.
    Retorna: scene (H,W,3), cells (grid,grid,h,w,3), truth (grid,grid) int.
    Distribui floresta como base e insere focos de mineração/queimada.
    """
    rng = np.random.default_rng(seed)
    truth = np.zeros((grid, grid), dtype=np.int64)  # 0 = floresta
    fidx = {c: i for i, c in enumerate(CLASSES)}
    # rio horizontal
    river_row = rng.integers(1, grid - 1)
    truth[river_row, :] = fidx["agua"]
    # insere anomalias
    for _ in range(rng.integers(3, 6)):
        truth[rng.integers(0, grid), rng.integers(0, grid)] = fidx["mineracao"]
    for _ in range(rng.integers(2, 5)):
        truth[rng.integers(0, grid), rng.integers(0, grid)] = fidx["queimada"]
    truth[rng.integers(0, grid), rng.integers(0, grid)] = fidx["urbano"]

    cells = np.zeros((grid, grid, img_size, img_size, 3), dtype=np.float32)
    for r in range(grid):
        for c in range(grid):
            cells[r, c] = _make_patch(rng, CLASSES[truth[r, c]], img_size)
    linhas = [np.concatenate([cells[r, c] for c in range(grid)], axis=1)
              for r in range(grid)]
    scene = np.concatenate(linhas, axis=0)  # (grid*H, grid*W, 3)
    return scene, cells, truth


def generate_fire_timeseries(days=180, seed=123):
    """Série diária sintética de focos de calor (proxy NASA FIRMS)."""
    rng = np.random.default_rng(seed)
    t = np.arange(days)
    trend = 0.15 * t                                  # tendência de alta (estação seca)
    seasonal = 12 * np.sin(2 * np.pi * t / 30.0)      # ciclo ~mensal
    noise = rng.normal(0, 4, days)
    series = 20 + trend + seasonal + noise
    return np.clip(series, 0, None).round().astype(float)
