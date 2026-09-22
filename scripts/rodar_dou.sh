#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --rebase --autostash -q
.venv/bin/python3 scripts/dou_diario.py
.venv/bin/python3 scripts/gerar_painel.py
git add dados docs
if git diff --staged --quiet; then
  echo "Nada mudou hoje (DOU)."
else
  git commit -m "dou $(date +%Y-%m-%d)"
  git push
fi
