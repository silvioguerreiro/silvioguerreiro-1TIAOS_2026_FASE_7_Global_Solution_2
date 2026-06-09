"""
SENTINELA - Configurações globais do projeto.
Define classes de uso do solo, área de interesse (AOI) na Amazônia,
pesos de severidade e caminhos. Tudo centralizado para facilitar ajuste.
"""
import os
from pathlib import Path

# Raiz do projeto (este arquivo está na raiz)
ROOT = Path(__file__).resolve().parent
# Diretório de dados/artefatos: por padrão dentro do projeto, mas pode ser
# redirecionado via env SENTINELA_HOME (útil p/ discos sincronizados/CI).
DATA_HOME = Path(os.environ.get("SENTINELA_HOME", ROOT))
DATA_DIR = DATA_HOME / ".sentinela_data"
DB_PATH = DATA_DIR / "sentinela.db"
MODEL_DIR = DATA_DIR / "models"
for _d in (DATA_DIR, MODEL_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Repositório local de DADOS REAIS (data lake incremental, versionável):
# acumula os dados públicos baixados (NASA FIRMS + Sentinel-2) para rodar
# offline-first e enriquecer a cada sincronização. Vive junto do código (não
# em .sentinela_data) para poder acompanhar a entrega. Ver data/repository.py.
LAKE_DIR = ROOT / "data" / "lake"

# Classes de uso do solo detectadas pela visão computacional
CLASSES = ["floresta", "agua", "mineracao", "queimada", "urbano"]

# Severidade (0-1) de cada classe para priorização de alertas.
# 'floresta' e 'agua' são baseline (sem ameaça); mineração/queimada são críticas.
CLASS_SEVERITY = {
    "floresta": 0.05,
    "agua": 0.05,
    "urbano": 0.20,
    "queimada": 0.90,
    "mineracao": 0.95,
}

# Classes que disparam alerta de fiscalização
CLASSES_ALERTA = {"mineracao", "queimada"}

# Área de Interesse (AOI): recorte da Amazônia Ocidental (aprox. Rondônia/Amazonas)
AOI = {"lat_min": -10.0, "lat_max": -5.0, "lon_min": -65.0, "lon_max": -60.0}

# Polígono "área protegida" (ex.: terra indígena/UC) para elevar prioridade
AREA_PROTEGIDA = {"lat_min": -8.5, "lat_max": -6.5, "lon_min": -64.0, "lon_max": -62.0}

IMG_SIZE = 32          # tamanho do patch (px) para a CNN
SCENE_GRID = 8         # cena = grade SCENE_GRID x SCENE_GRID de patches
PIXEL_AREA_HA = 50.0   # ha representados por cada célula detectada (escala didática)
