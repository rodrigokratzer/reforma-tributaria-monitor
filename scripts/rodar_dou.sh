#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# publicar.sh resolve sozinho conflito em docs/ (gerado); qualquer outro
# conflito aborta o rebase, deixando o checkout limpo e a falha no journal.
scripts/publicar.sh --sincronizar || exit 1
.venv/bin/python3 scripts/dou_diario.py
.venv/bin/python3 scripts/gerar_painel.py
scripts/publicar.sh "dou $(date +%Y-%m-%d) ${TURNO:-}" dados docs
