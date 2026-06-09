# esp32 — Sensor de validação em solo (Wokwi)

Firmware do sensor de campo que confirma, no solo, um alerta de queimada detectado
por satélite. Lê fumaça (sensor de gás) e temperatura (potenciômetro como proxy) e
envia JSON via Wi-Fi para a API SENTINELA (`POST /telemetria`).

```
sensor_solo.ino   # firmware (classe SensorCampo, POO)
diagram.json      # circuito Wokwi: ESP32 + sensor de gás (D34) + pot. (D35) + LED (D2)
wokwi.toml        # aponta para o firmware compilado em build/
```

## Rodar no Wokwi (extensão do VS Code)

Pré-requisito: extensão **Wokwi for VS Code** instalada (já presente neste
ambiente) e uma **licença gratuita** (uma vez): `F1` → **Wokwi: Request a License**.

1. **Compilar o firmware** (gera `build/sensor_solo.ino.bin` e `.elf`).
   O `arduino-cli` 1.x exige que o `.ino` esteja numa pasta com o mesmo nome,
   então copie o sketch para uma pasta temporária antes de compilar:
   ```bash
   # (uma vez) instalar o core ESP32:
   arduino-cli config add board_manager.additional_urls \
     https://espressif.github.io/arduino-esp32/package_esp32_index.json
   arduino-cli core update-index && arduino-cli core install esp32:esp32

   # compilar:
   mkdir -p /tmp/sensor_solo && cp sensor_solo.ino /tmp/sensor_solo/
   arduino-cli compile --fqbn esp32:esp32:esp32 \
     --output-dir build /tmp/sensor_solo
   ```
2. **Abrir** `diagram.json` no VS Code e rodar: `F1` → **Wokwi: Start Simulator**
   (ou clique no ▶️ do diagrama).
3. Abrir o **Serial Monitor** do Wokwi: ele mostra a conexão Wi-Fi e os envios
   `POST -> ... {"sensor_id":"ESP32-AMZ-01", ... "fogo_confirmado":true}`.
4. **Capturar o print** (para o PDF): `Cmd+Shift+4` (seleção) ou
   `Cmd+Shift+3` (tela cheia). Salve em `../../assets/figuras/print_esp32_wokwi.png`.

> Gire o potenciômetro e ajuste o sensor de gás no Wokwi para cruzar os limiares
> (`fumaca > 0.6` e `temp > 32`) e ver `fogo_confirmado: true` no serial.

## Alternativa sem instalar nada (web)
Abra https://wokwi.com/projects/new/esp32, cole `sensor_solo.ino` e `diagram.json`,
clique ▶️ e capture a tela. O Wokwi compila na nuvem (não precisa de toolchain).

## Observação sobre a rede
Em simulação, o ESP32 usa a rede `Wokwi-GUEST`. O endpoint `10.0.0.10:8000` é
ilustrativo: o que importa para a POC é o **serial mostrando o JSON de telemetria**
(a integração real chega via `POST /telemetria` quando apontado a um host acessível).
