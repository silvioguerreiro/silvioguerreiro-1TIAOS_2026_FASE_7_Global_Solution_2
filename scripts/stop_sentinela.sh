#!/usr/bin/env bash
# SENTINELA - encerra API (uvicorn) e Dashboard (streamlit) deste projeto.
set -uo pipefail
echo "==> Encerrando SENTINELA…"
pkill -f "uvicorn core.api:app" 2>/dev/null && echo "   API encerrada." || echo "   API não estava rodando."
pkill -f "streamlit run dashboard/app.py" 2>/dev/null && echo "   Dashboard encerrado." || echo "   Dashboard não estava rodando."
echo "==> Concluído."
