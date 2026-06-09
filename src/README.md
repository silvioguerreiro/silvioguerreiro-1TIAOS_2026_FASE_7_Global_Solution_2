# src — Código-fonte

Aplicação SENTINELA (Python).

```
src/
├── config.py        # parâmetros globais (classes, AOI, severidade, paths)
├── conftest.py      # ajuste de path para os testes
├── run_demo.py      # pipeline ponta a ponta (entrada principal)
├── make_figures.py  # gera as figuras de resultado em ../assets/figuras
├── core/            # módulos de IA e serviços
│   ├── vision.py        # CNN (Keras) + fallback numpy; detecção na cena
│   ├── forecast.py      # RNN/LSTM (Keras) + fallback AR; previsão de focos
│   ├── genetic.py       # algoritmo genético: rota de patrulha
│   ├── recommender.py   # priorização de alertas
│   ├── geo.py           # georreferenciamento (pixel->lat/lon, Haversine)
│   ├── storage.py       # SQLite (detecções) + MongoDB/mongomock (telemetria)
│   ├── cognitive_mock.py# serviço cognitivo simulado (estilo Rekognition)
│   ├── serverless_mock.py# orquestração simulada (Lambda/SQS/SNS/CloudWatch)
│   ├── voice.py         # alerta por voz (TTS) com fallback texto
│   └── api.py           # API REST (FastAPI)
├── data/            # geração/ingestão/persistência de dados
│   ├── synthetic.py     # dados sintéticos (proxy de Sentinel-2/NASA FIRMS)
│   ├── ingest.py        # ingestão de dados PÚBLICOS REAIS (FIRMS + Sentinel-2)
│   ├── repository.py    # repositório local (data lake) — acumula dados reais
│   └── lake/            # dados reais baixados (parquet/json, versionável)
├── dashboard/       # painel de comando
│   └── app.py           # Streamlit
├── esp32/           # firmware do sensor de campo (simulado no Wokwi)
│   └── sensor_solo.ino
└── tests/           # bateria de testes (pytest)
```

## Executar (a partir desta pasta `src/`)
```bash
python run_demo.py             # pipeline completo (relatório no console)
python -m pytest               # 29 testes
python -m data.repository      # sincroniza o data lake (baixa + agrega)
streamlit run dashboard/app.py # dashboard
uvicorn core.api:app --reload  # API REST (docs em /docs)
```
Sem TensorFlow instalado, os módulos de visão e previsão usam automaticamente
os fallbacks em numpy — o sistema roda em qualquer máquina.

## Dados públicos reais (`data/ingest.py`)

Por padrão o demo roda com dados sintéticos (offline, determinístico). Para
alimentar a POC com **dados abertos reais**, sem trocar o pipeline:

```bash
python -m data.ingest                       # mostra AOI, busca cenas Sentinel-2
python -m data.ingest --image cena.png      # tila uma imagem real p/ a CNN
```

**1) Focos de calor — NASA FIRMS** (queimadas). Gere uma chave gratuita em
https://firms.modaps.eosdis.nasa.gov/api/map_key/ e exporte:
```bash
export FIRMS_MAP_KEY=<sua_chave>
```
`fetch_fire_foci_firms()` baixa os focos reais (VIIRS 375 m) dentro da AOI e
`fire_foci_to_timeseries()` os agrega para a previsão (LSTM/AR).

**2) Imagem orbital — Sentinel-2** (uso do solo). No
[Copernicus Browser](https://browser.dataspace.copernicus.eu/) navegue até a
Amazônia, selecione *True Color*, e baixe a imagem (`.png`/`.tif`). Depois:
```python
from data.ingest import load_scene_from_image
from core.vision import VisionModel, detectar_cena
scene, cells = load_scene_from_image("cena.png")   # imagem real -> grade
dets = detectar_cena(VisionModel(force_light=True), cells)
```
`search_sentinel2_scenes()` também lista cenas reais via STAC pública (sem login).

**Plugar no `run_demo.py`** (substitui os geradores sintéticos pelos reais):
```python
# antes:  scene, cells, truth = generate_scene(...)
from data.ingest import load_scene_from_image, fetch_fire_foci_firms, fire_foci_to_timeseries
scene, cells = load_scene_from_image("assets/cena_amazonia.png")
serie = fire_foci_to_timeseries(fetch_fire_foci_firms(days=5), fill_days=180)
```

Dependências: apenas stdlib (`urllib`) + `numpy/pandas/opencv` já listados — sem
novos pacotes. [FORA DO MATERIAL: NASA FIRMS e Copernicus são fontes externas.]

## Repositório local / data lake (`data/repository.py`)

Para rodar **offline-first** e ficar mais rico a cada execução, os dados reais
baixados são acumulados (com deduplicação) em `data/lake/`:

```
data/lake/firms_foci.parquet  # focos de calor acumulados (NASA FIRMS)
data/lake/s2_scenes.json      # catálogo de cenas Sentinel-2 (dedup por id)
data/lake/manifest.json       # contagens, período coberto, última sync
```

```bash
export FIRMS_MAP_KEY=<sua_chave>
python -m data.repository        # baixa em tempo real e AGREGA ao lake
```
```python
from data import repository as repo
repo.sync_fire_foci(days=5)      # tempo real -> agrega (retorna novos, total)
repo.sync_scenes(limit=10)       # idem para Sentinel-2
df    = repo.load_fire_foci()    # offline: tudo que já foi acumulado
serie = repo.fire_foci_timeseries(fill_days=180)   # alimenta o forecast
```

No **dashboard**, a seção *Repositório local* mostra as contagens e oferece
**🔄 Sincronizar (baixar + agregar)** e **📂 Usar repositório (offline)**; ao
abrir, as abas já carregam o que estiver no lake (sem rede). O `data/lake/` é
versionável e acompanha a entrega — apague-o para começar do zero.
