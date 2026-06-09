"""
API REST (FastAPI) expõe detecções, alertas e previsão da plataforma.
Endpoints:
  GET  /health            -> status
  GET  /deteccoes         -> detecções geolocalizadas
  GET  /alertas           -> alertas priorizados
  GET  /previsao?dias=7   -> previsão de focos (RNN/LSTM ou fallback)
  POST /pipeline/run      -> executa o pipeline ponta a ponta uma vez
"""
from fastapi import FastAPI
from core import storage
from data.synthetic import generate_fire_timeseries
from core.forecast import ForecastModel

app = FastAPI(title="SENTINELA API", version="1.0")


@app.on_event("startup")
def _startup():
    storage.init_db()


@app.get("/health")
def health():
    return {"status": "ok", "nosql": storage.backend_nosql()}


@app.get("/deteccoes")
def deteccoes():
    return storage.listar_deteccoes()


@app.get("/alertas")
def alertas():
    return storage.listar_alertas()


@app.get("/previsao")
def previsao(dias: int = 7):
    serie = generate_fire_timeseries()
    fm = ForecastModel(force_light=True)  # leve para resposta rápida da API
    fm.fit(serie)
    fc = fm.forecast(serie, horizon=dias)
    return {"backend": fm.backend, "horizonte": dias,
            "previsao": [round(float(x), 1) for x in fc]}


@app.post("/pipeline/run")
def pipeline_run():
    from run_demo import executar_pipeline
    return executar_pipeline(treinar_keras=False)
