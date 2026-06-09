"""
SENTINELA - Pipeline ponta a ponta (demonstração).
Encadeia: visão computacional -> georreferenciamento -> serviço cognitivo ->
persistência SQL/NoSQL -> previsão (RNN/LSTM) -> priorização ->
algoritmo genético (rota) -> orquestração serverless -> alerta por voz.

Uso:
    python run_demo.py            # usa fallback leve (sem TensorFlow)
    python run_demo.py --keras    # usa CNN/LSTM Keras se TensorFlow instalado
"""
import sys
import numpy as np

from config import (CLASSES, CLASSES_ALERTA, CLASS_SEVERITY, PIXEL_AREA_HA,
                    SCENE_GRID)
from data.synthetic import (generate_landuse_dataset, generate_scene,
                            generate_fire_timeseries)
from core.vision import VisionModel, detectar_cena, avaliar
from core.geo import cell_to_latlon, em_area_protegida
from core import storage
from core.cognitive_mock import detect_labels
from core.forecast import ForecastModel, tendencia
from core.recommender import priorizar
from core.genetic import otimizar_rota, comprimento_rota
from core.serverless_mock import EventBus
from core.voice import falar_alerta


def executar_pipeline(treinar_keras=False, verbose=False):
    storage.init_db()
    storage.limpar()
    bus = EventBus()

    # 1) VISÃO COMPUTACIONAL: treina e avalia o classificador de uso do solo
    Xtr, ytr = generate_landuse_dataset(n_per_class=80, seed=42)
    Xte, yte = generate_landuse_dataset(n_per_class=20, seed=7)
    vm = VisionModel(force_light=not treinar_keras)
    vm.train(Xtr, ytr, verbose=0)
    acc = avaliar(vm, Xte, yte)
    bus.cw.log("Vision", f"backend={vm.backend} acc={acc:.3f}")

    # 2) DETECÇÃO na cena orbital (janela deslizante)
    scene, cells, truth = generate_scene(grid=SCENE_GRID, seed=7)
    dets_raw = detectar_cena(vm, cells)

    # 3) Georreferencia + serviço cognitivo + persiste apenas anomalias
    deteccoes = []
    for d in dets_raw:
        if d["classe"] not in CLASSES_ALERTA:
            continue
        lat, lon = cell_to_latlon(d["row"], d["col"], SCENE_GRID, SCENE_GRID)
        prot = em_area_protegida(lat, lon)
        labels = detect_labels(cells[d["row"], d["col"]], d["classe"])
        area = round(PIXEL_AREA_HA * (1 + 2 * d["confianca"]), 1)
        reg = {"classe": d["classe"], "confianca": d["confianca"],
               "lat": lat, "lon": lon, "area_ha": area,
               "severidade": CLASS_SEVERITY[d["classe"]],
               "em_area_protegida": prot, "cognitivo": labels["labels"]}
        rid = storage.inserir_deteccao(reg)
        reg["id"] = rid
        deteccoes.append(reg)
        bus.publish("nova_deteccao", reg)

    # 4) PREVISÃO de focos (série temporal) + tendência
    serie = generate_fire_timeseries(days=180)
    fm = ForecastModel(look_back=14, force_light=not treinar_keras)
    fm.fit(serie, verbose=0)
    fc = fm.forecast(serie, horizon=7)
    fator = tendencia(fc)
    bus.cw.log("Forecast", f"backend={fm.backend} tendencia={fator:.3f}")

    # 5) PRIORIZAÇÃO (recomendação) dos alertas
    priorizadas = priorizar(deteccoes, fator_tendencia=fator)

    # 6) Grava alertas e dispara notificações (SNS) p/ os mais críticos
    for d in priorizadas:
        msg = (f"{d['classe'].upper()} em ({d['lat']},{d['lon']}) "
               f"area~{d['area_ha']}ha prioridade={d['prioridade']}")
        storage.inserir_alerta(d["id"], d["prioridade"], msg)
        if d["prioridade"] >= 0.5:
            bus.notify("fiscalizacao", msg)
            bus.enqueue(d["id"])

    # 7) ALGORITMO GENÉTICO: rota ótima de patrulha pelos focos prioritários
    pontos = [(d["lat"], d["lon"]) for d in priorizadas]
    rota, dist, hist = otimizar_rota(pontos, geracoes=120, pop=60, seed=42)
    dist_naive = comprimento_rota(list(range(len(pontos))), pontos) if pontos else 0.0

    # 8) Telemetria de campo (ESP32 simulado -> NoSQL)
    storage.registrar_telemetria(
        {"sensor_id": "ESP32-AMZ-01", "lat": -7.21, "lon": -63.05,
         "temp": 34.2, "fumaca": 0.71, "fogo_confirmado": True})

    # 9) ALERTA POR VOZ para o foco de maior prioridade
    voz = {"engine": "n/a", "path": None}
    if priorizadas:
        top = priorizadas[0]
        texto = (f"Alerta SENTINELA. Detectado {top['classe']} com prioridade "
                 f"{top['prioridade']:.2f} na latitude {top['lat']}, longitude "
                 f"{top['lon']}. Acionar fiscalizacao.")
        voz = falar_alerta(texto, nome="alerta_top")

    resumo = {
        "vision_backend": vm.backend,
        "vision_acc": round(acc, 4),
        "forecast_backend": fm.backend,
        "tendencia": round(fator, 4),
        "previsao_7d": [round(float(x), 1) for x in fc],
        "n_deteccoes": len(deteccoes),
        "n_alertas": len(priorizadas),
        "top_alertas": [{"classe": d["classe"], "lat": d["lat"], "lon": d["lon"],
                         "prioridade": d["prioridade"]} for d in priorizadas[:3]],
        "rota_dist_km": dist,
        "rota_naive_km": round(dist_naive, 3),
        "rota_ganho_pct": (round(100 * (dist_naive - dist) / dist_naive, 1)
                           if dist_naive else 0.0),
        "lambda_invocacoes": len(bus.cw.eventos),
        "sns_notificacoes": len(bus.sns),
        "nosql": storage.backend_nosql(),
        "voz": voz,
    }
    if verbose:
        _print_relatorio(resumo)
    return resumo


def _print_relatorio(r):
    print("\n" + "=" * 60)
    print("        SENTINELA - RELATÓRIO DO PIPELINE")
    print("=" * 60)
    print(f" Visão computacional .... {r['vision_backend']}  acc={r['vision_acc']}")
    print(f" Detecções (anomalias) .. {r['n_deteccoes']}")
    print(f" Previsão focos (7d) .... {r['forecast_backend']}  tend={r['tendencia']}")
    print(f"   -> {r['previsao_7d']}")
    print(f" Alertas priorizados .... {r['n_alertas']}")
    for a in r["top_alertas"]:
        print(f"   [{a['prioridade']:.2f}] {a['classe']:9s} ({a['lat']},{a['lon']})")
    print(f" Rota patrulha (GA) ..... {r['rota_dist_km']} km "
          f"(ingênua {r['rota_naive_km']} km, ganho {r['rota_ganho_pct']}%)")
    print(f" Serverless (Lambda) .... {r['lambda_invocacoes']} invocações | "
          f"SNS {r['sns_notificacoes']}")
    print(f" NoSQL telemetria ....... {r['nosql']}")
    print(f" Alerta por voz ......... {r['voz']['engine']} -> {r['voz']['path']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    executar_pipeline(treinar_keras=("--keras" in sys.argv), verbose=True)
