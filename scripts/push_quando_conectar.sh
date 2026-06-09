#!/usr/bin/env bash
# push_quando_conectar.sh
# Monitora a conexao com o GitHub e faz o push automaticamente quando voltar.
# Uso:  bash scripts/push_quando_conectar.sh [branch]   (default: branch atual)

set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR" || { echo "Nao foi possivel acessar o repo"; exit 1; }

BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"
INTERVALO=15          # segundos entre tentativas
TIMEOUT_TESTE=10      # timeout de cada teste de conexao

echo "Repo......: $REPO_DIR"
echo "Branch....: $BRANCH"
echo "Verificando conexao com o GitHub a cada ${INTERVALO}s (Ctrl+C para parar)..."
echo

testar_conexao() {
  # Sucesso so se o handshake TLS completar e o GitHub responder de fato.
  git ls-remote --exit-code origin HEAD >/dev/null 2>&1
}

tentativa=0
while true; do
  tentativa=$((tentativa + 1))
  printf "[%s] tentativa %d... " "$(date '+%H:%M:%S')" "$tentativa"

  if testar_conexao; then
    echo "CONECTADO ✓"
    echo
    echo ">>> Fazendo git push origin $BRANCH"
    if git push origin "$BRANCH"; then
      echo
      echo "✅ Push concluido com sucesso."
      exit 0
    else
      echo
      echo "⚠️  Conexao OK mas o push falhou (ver mensagem acima)."
      echo "    Pode ser necessario 'git pull --rebase' ou autenticacao. Saindo."
      exit 2
    fi
  else
    echo "sem conexao (timeout/reset). Nova tentativa em ${INTERVALO}s."
    sleep "$INTERVALO"
  fi
done
