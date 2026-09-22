#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Um conflito de rebase aqui deixaria o checkout parado no meio do rebase,
# quebrando todas as noites seguintes ate alguem intervir na mao. Abortar
# devolve o checkout a um estado limpo e falha visivel no journal.
if ! git pull --rebase --autostash -q; then
  echo "git pull --rebase falhou - abortando rebase para deixar o checkout limpo" >&2
  git rebase --abort 2>/dev/null || true
  exit 1
fi
.venv/bin/python3 scripts/varredura.py
.venv/bin/python3 scripts/gerar_painel.py
git add dados docs
if git diff --staged --quiet; then
  echo "Nada mudou hoje (varredura)."
else
  git commit -m "varredura $(date +%Y-%m-%d)"
  git push
fi
