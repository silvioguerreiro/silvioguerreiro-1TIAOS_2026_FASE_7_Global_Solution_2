 <a href="https://www.fiap.com.br/">
  <img width="2385" height="642" alt="logo-fiap" src="https://github.com/user-attachments/assets/62285a6c-34fe-4206-8a85-7ad584c6908b" border="0" width="40%" height="40%">
</a>

<br>

# SENTINELA — Sistema de Vigilância Orbital Inteligente para Defesa e Soberania

## Grupo 37

## 👨‍🎓 Integrantes
- [**Silvio Prestes Guerreiro Junior**](https://www.linkedin.com/in/silvio-guerreiro-junior/)
- **RM:** 567958

## 👩‍🏫 Professores
- **Tutor(a):** [Sabrina Otoni](https://www.linkedin.com/company/inova-fusca)
- **Coordenador(a):** [André Godoi Chiovato](https://www.linkedin.com/company/inova-fusca)

---

## 📜 Descrição

**SENTINELA** é uma Prova de Conceito (POC) da **Global Solution 2026.1 — A Nova
Economia Espacial**, do curso de Inteligência Artificial da FIAP (1TIAO, Fase 7).

A solução responde à pergunta norteadora *"como a Inteligência Artificial e as
tecnologias digitais podem transformar a nova economia espacial e gerar impacto
positivo na Terra?"* aplicando IA sobre **imagens de satélite e dados públicos**
para gerar **detecções geolocalizadas e alertas acionáveis**. O foco da POC é o
**monitoramento da Amazônia** — detecção de **mineração ilegal, queimadas e
desmatamento** — com arquitetura preparada para escalar a outras aplicações
estratégicas (combate ao tráfico, atualização cartográfica, navegabilidade de
rios, vigilância da ZEE/"Amazônia Azul" e controle de fronteiras), fortalecendo a
defesa do território e das Águas Jurisdicionais Brasileiras.

O projeto integra, de forma coerente, cerca de **11 disciplinas do curso**:

| Eixo / Disciplina | Onde entra |
|---|---|
| Visão Computacional (CNN/YOLO) | Detecção de anomalias na cena orbital |
| Redes Neurais Recorrentes (RNN/LSTM) | Previsão de focos de calor |
| Algoritmos Genéticos | Otimização da rota de patrulha |
| Ciência de Dados / Geolocalização | Pipeline e coordenadas das detecções |
| SQL & NoSQL | PostgreSQL (detecções) + MongoDB (telemetria) |
| Cloud / Serverless / Monitoramento | Orquestração por eventos (simulada) |
| Serviços Cognitivos & Voz (TTS/STT) | Rotulagem auxiliar e alerta falado |
| IoT / ESP32 | Sensor de validação em solo (simulado) |
| Dashboards | Painel de comando (Streamlit) |
| Cibersegurança & Direito Digital | Auditoria, integridade, LGPD e ética |

> **Funcional vs. simulado:** o núcleo de IA (visão, previsão, algoritmo genético,
> recomendação, geolocalização, API, dashboard, bancos e voz) é **real e testado**.
> Componentes que exigiriam conta AWS ou hardware (Lambda/SQS/SNS, serviço
> cognitivo e ESP32) são **simulados** com a mesma interface, acompanhados de
> plano de evolução para produção.

## 🎥 Demonstração em vídeo
Vídeo demonstrativo (até 5 min, YouTube — "Não listado"): https://youtu.be/RHZ77HH8EM8

## 📁 Estrutura de pastas

```
1TIAOS_2026_FASE_7_GS2/
├── assets/      # imagens, logo e figuras de resultado (+ figuras/)
├── config/      # configurações e variáveis de ambiente
├── document/    # PDF único de entrega (e versão .docx)
├── scripts/     # scripts auxiliares (run.sh)
├── src/         # código-fonte (core, data, dashboard, esp32, tests)
├── requirements.txt
└── README.md
```

## 🔧 Como executar o código

Pré-requisitos: Python 3.10+.

```bash
# 1) dependências
pip install -r requirements.txt

# 2) pipeline ponta a ponta (relatório no console)
cd src
python run_demo.py

# 3) testes (29 testes)
python -m pytest

# 4) dashboard de comando
streamlit run dashboard/app.py

# 5) API REST (documentação interativa em /docs)
uvicorn core.api:app --reload

# 6) (opcional) dados públicos reais: NASA FIRMS + Sentinel-2
export FIRMS_MAP_KEY=<chave_gratuita>   # firms.modaps.eosdis.nasa.gov/api/map_key/
python -m data.repository               # baixa e acumula no data lake local
```

> Sem TensorFlow instalado, a visão computacional e a previsão usam
> automaticamente fallbacks em numpy — o MVP roda em qualquer máquina. Para usar
> os modelos Keras (CNN/LSTM), instale `tensorflow-cpu` e rode
> `python run_demo.py --keras`.

## 🗃 Histórico de lançamentos
- **0.2.0** — Dados públicos REAIS (NASA FIRMS + Sentinel-2 via STAC), repositório
  local incremental (data lake) com sincronização e modo offline-first, dashboard
  com mapas e leitura para decisão por aba. 29 testes automatizados.
- **0.1.0** — POC inicial: detecção (CV), previsão (RNN/LSTM), algoritmo genético
  de rota, recomendação, API, dashboard, bancos SQL/NoSQL, voz e simulações de
  AWS/ESP32.

## 📋 Licença
<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p>Este projeto segue o modelo de licenciamento acadêmico FIAP — Attribution 4.0 International (CC BY 4.0).</p>
