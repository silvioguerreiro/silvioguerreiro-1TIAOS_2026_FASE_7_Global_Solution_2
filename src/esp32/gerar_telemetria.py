#!/usr/bin/env python3
"""
Gera telemetria do sensor de campo SENTINELA reproduzindo EXATAMENTE a logica do
firmware sensor_solo.ino (classe SensorCampo / loop), sem depender do simulador.

Util quando o serial do Wokwi headless nao esta disponivel: produz os mesmos
dados que o ESP32 imprimiria no Serial Monitor.

Formulas espelhadas do firmware:
    temp   = 25.0 + (adc_d35 % 15)         # 25.0 .. 39.0  (potenciometro)
    fumaca = adc_d34 / 4095.0              # 0.00 .. 1.00  (sensor de gas)
    fogo   = (fumaca > 0.6) and (temp > 32.0)
    linha  = TELEMETRIA -> {json}          # a cada 5 s (loop delay 5000)

Saidas:
    telemetria_simulada.log    -> formato identico ao Serial Monitor do Wokwi
    telemetria_simulada.jsonl  -> 1 objeto JSON por linha (ingestao/NoSQL)

Uso:
    python gerar_telemetria.py [--ciclos N] [--intervalo 5]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SENSOR_ID = "ESP32-AMZ-01"
LAT, LON = -7.21, -63.05
INICIO = datetime(2026, 6, 3, 9, 0, 0, tzinfo=timezone(timedelta(hours=-4)))  # Porto Velho/RO


def leitura(adc_d34: int, adc_d35: int) -> dict:
    """Reproduz SensorCampo.lerFumaca()/lerTemp() e a regra de fogo do loop()."""
    fumaca = round(adc_d34 / 4095.0, 2)
    temp = round(25.0 + (adc_d35 % 15), 1)
    fogo = (fumaca > 0.6) and (temp > 32.0)
    return {
        "sensor_id": SENSOR_ID,
        "lat": LAT,
        "lon": LON,
        "temp": temp,
        "fumaca": fumaca,
        "fogo_confirmado": fogo,
    }


def cenario_adc(n: int) -> list[tuple[int, int]]:
    """Perfil calmo -> queimada -> resfriamento (espelha scenario.test.yaml).

    Retorna pares (adc_d34_gas, adc_d35_pot) que cruzam os limiares de fogo no
    meio da janela e voltam ao normal no fim. ADC de 12 bits (0..4095).
    """
    pares: list[tuple[int, int]] = []
    for i in range(n):
        f = i / max(n - 1, 1)  # 0..1 ao longo do tempo
        if f < 0.35:           # calmo: gas baixo, temp amena
            gas = int(120 + 600 * f)          # ~0.03 .. ~0.09
            pot = int(300 + 400 * f)          # temp 25..27
        elif f < 0.75:         # queimada: gas e temp acima dos limiares
            gas = int(2900 + 900 * (f - 0.35))  # ~0.71 .. ~0.93
            pot = 4090                          # 4090 % 15 = 10 -> temp 35.0
        else:                  # resfriamento
            gas = int(2600 - 1800 * (f - 0.75))  # cai abaixo de 0.6
            pot = int(2000 - 1200 * (f - 0.75))  # temp volta a baixar
        pares.append((max(0, min(4095, gas)), max(0, min(4095, pot))))
    return pares


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera telemetria do sensor SENTINELA (espelha o firmware).")
    ap.add_argument("--ciclos", type=int, default=24, help="numero de leituras (default 24)")
    ap.add_argument("--intervalo", type=int, default=5, help="segundos entre leituras (firmware=5)")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    log_path = base / "telemetria_simulada.log"
    jsonl_path = base / "telemetria_simulada.jsonl"

    linhas_log: list[str] = [
        "=== SENTINELA | Sensor de campo ESP32 ===",
        "Conectando ao Wi-Fi....",
        "Wi-Fi conectado. IP: 10.0.0.123",
    ]
    registros: list[dict] = []
    n_fogo = 0

    for i, (gas, pot) in enumerate(cenario_adc(args.ciclos)):
        reg = leitura(gas, pot)
        ts = INICIO + timedelta(seconds=i * args.intervalo)
        # JSON na MESMA ordem/serializacao do firmware (temp 1 casa, fumaca 2 casas)
        json_fw = (
            '{"sensor_id":"%s","lat":%s,"lon":%s,"temp":%.1f,"fumaca":%.2f,"fogo_confirmado":%s}'
            % (reg["sensor_id"], reg["lat"], reg["lon"], reg["temp"], reg["fumaca"],
               "true" if reg["fogo_confirmado"] else "false")
        )
        linhas_log.append(f"TELEMETRIA -> {json_fw}")
        if reg["fogo_confirmado"]:
            linhas_log.append("POST -> 200")
            n_fogo += 1
        registros.append({"ts": ts.isoformat(), **reg})

    log_path.write_text("\n".join(linhas_log) + "\n", encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for r in registros:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"OK: {len(registros)} leituras geradas ({n_fogo} com fogo_confirmado=true)")
    print(f"  - serial : {log_path}")
    print(f"  - jsonl  : {jsonl_path}")


if __name__ == "__main__":
    main()
