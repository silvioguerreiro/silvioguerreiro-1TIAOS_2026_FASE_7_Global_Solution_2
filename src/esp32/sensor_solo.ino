/*
 * SENTINELA - Sensor de validação em solo (ESP32) [SIMULADO no Wokwi]
 * Base: F6·C3 (ESP32/visão), F7·C8 (POO/ESP32), F5·C6-7 (conectividade sem fio).
 *
 * Lê temperatura/umidade/fumaça e envia JSON via Wi-Fi para a API SENTINELA
 * (endpoint /telemetria). Confirma em campo um alerta de queimada detectado
 * por satélite. Programação orientada a objetos (classe SensorCampo).
 *
 * Wokwi: https://wokwi.com  (ESP32 + sensor de gás MQ-2 + potenciômetro p/ temp.)
 *
 * IMPORTANTE: a telemetria (JSON) é SEMPRE impressa no Serial a cada ciclo,
 * independente do Wi-Fi/HTTP. O endpoint 10.0.0.10:8000 é inalcançável no
 * sandbox do Wokwi, então o POST usa timeout curto p/ não travar o loop.
 */
#include <WiFi.h>
#include <HTTPClient.h>

const char* SSID = "Wokwi-GUEST";
const char* PASS = "";
const char* API  = "http://10.0.0.10:8000/telemetria";   // ajuste p/ seu host

class SensorCampo {
  public:
    int pinoGas; int pinoDHT;
    SensorCampo(int g, int d) : pinoGas(g), pinoDHT(d) {}
    float lerFumaca()   { return analogRead(pinoGas) / 4095.0; }            // 0-1
    float lerTemp()     { return 20.0 + (analogRead(pinoDHT) / 4095.0) * 30.0; } // 20-50C, monotonico c/ o pot
};

SensorCampo sensor(34, 35);

void conectarWiFi() {
  Serial.print("Conectando ao Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(SSID, PASS);
  unsigned long inicio = millis();
  // Tentativa NÃO bloqueante: desiste após 10 s e segue gerando telemetria.
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < 10000) {
    delay(300);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\nWi-Fi conectado. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWi-Fi indisponivel (segue em modo offline; serial mostra telemetria).");
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== SENTINELA | Sensor de campo ESP32 ===");
  conectarWiFi();
}

void loop() {
  float fumaca = sensor.lerFumaca();
  float temp   = sensor.lerTemp();
  bool  fogo   = (fumaca > 0.6 && temp > 32.0);

  String json = "{\"sensor_id\":\"ESP32-AMZ-01\",\"lat\":-7.21,\"lon\":-63.05,";
  json += "\"temp\":" + String(temp, 1) + ",\"fumaca\":" + String(fumaca, 2);
  json += ",\"fogo_confirmado\":" + String(fogo ? "true" : "false") + "}";

  // 1) SEMPRE imprime a telemetria no Serial (é o que importa para a POC/print).
  Serial.printf("TELEMETRIA -> %s\n", json.c_str());

  // 2) Tenta enviar via HTTP (best-effort). Timeout curto evita travar o loop
  //    quando o endpoint não está acessível (caso típico no Wokwi).
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setConnectTimeout(2000);
    http.setTimeout(2000);
    if (http.begin(API)) {
      http.addHeader("Content-Type", "application/json");
      int code = http.POST(json);
      if (code > 0) Serial.printf("POST -> %d\n", code);
      else          Serial.printf("POST falhou (%d: %s) - host de exemplo offline\n",
                                  code, http.errorToString(code).c_str());
      http.end();
    }
  }

  delay(5000);
}
