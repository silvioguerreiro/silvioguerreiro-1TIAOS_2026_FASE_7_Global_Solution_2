# config

Configurações do projeto.

- As **dependências** estão em `requirements.txt` (raiz do repositório).
- Parâmetros da solução (classes de uso do solo, área de interesse na Amazônia,
  pesos de severidade, tamanho de imagem) ficam em `src/config.py`.
- Variável de ambiente opcional **`SENTINELA_HOME`**: redireciona o diretório de
  dados/artefatos de runtime (banco SQLite, modelos, alertas). Útil em CI ou em
  discos sincronizados. Por padrão, usa `src/.sentinela_data/`.
