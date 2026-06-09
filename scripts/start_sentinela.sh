#!/usr/bin/env bash
# SENTINELA - inicializador único: sobe API + Dashboard e abre o navegador.
# Usado pelo app de Área de Trabalho (SENTINELA.app) e também executável direto.
set -euo pipefail

# Raiz do projeto (= diretório pai de scripts/)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/src"
VENV="$ROOT/.venv"
LOGDIR="$ROOT/.sentinela_logs"
mkdir -p "$LOGDIR"

API_PORT=8000
DASH_PORT=8501

echo "==> SENTINELA — iniciando (raiz: $ROOT)"

# 1) Garante o ambiente virtual e as dependências
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Criando ambiente virtual (.venv)…"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

if ! python -c "import fastapi, streamlit, uvicorn" >/dev/null 2>&1; then
  echo "==> Instalando dependências (primeira execução)…"
  pip install --upgrade pip >/dev/null
  pip install -r "$ROOT/requirements.txt"
fi

# 2) Sobe um serviço só se a porta ainda não estiver atendendo
port_up() { curl -s -o /dev/null "http://127.0.0.1:$1" 2>/dev/null; }

cd "$SRC"

if port_up "$API_PORT"; then
  echo "==> API já está no ar em $API_PORT."
else
  echo "==> Subindo API (uvicorn) na porta $API_PORT…"
  nohup uvicorn core.api:app --host 127.0.0.1 --port "$API_PORT" \
    > "$LOGDIR/api.log" 2>&1 &
fi

if port_up "$DASH_PORT"; then
  echo "==> Dashboard já está no ar em $DASH_PORT."
else
  echo "==> Subindo Dashboard (streamlit) na porta $DASH_PORT…"
  nohup streamlit run dashboard/app.py \
    --server.headless true --server.port "$DASH_PORT" \
    > "$LOGDIR/dashboard.log" 2>&1 &
fi

# 3) Aguarda o dashboard responder e abre o navegador
echo "==> Aguardando o dashboard ficar pronto…"
for _ in $(seq 1 30); do
  if port_up "$DASH_PORT"; then break; fi
  sleep 1
done

open "http://127.0.0.1:$DASH_PORT"
echo ""
echo "==> Pronto!"
echo "    Dashboard : http://127.0.0.1:$DASH_PORT"
echo "    API /docs : http://127.0.0.1:$API_PORT/docs"
echo "    Logs      : $LOGDIR"
