#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# publicar.sh resolve sozinho conflito em docs/ (gerado); qualquer outro
# conflito aborta o rebase, deixando o checkout limpo e a falha no journal.
scripts/publicar.sh --sincronizar || exit 1
.venv/bin/python3 scripts/varredura.py
# Raia de leitura: texto integral (HTML, PDF, OCR) de tudo que ainda nao tem.
# Falha aqui nao segura a publicacao da varredura: o que nao foi lido fica
# como `falhou` em dados/leituras.json e e' tentado de novo no proximo ciclo.
.venv/bin/python3 scripts/ler_textos.py || echo "AVISO: ler_textos.py falhou (ver acima)" >&2
.venv/bin/python3 scripts/gerar_painel.py
scripts/publicar.sh "varredura $(date +%Y-%m-%d) ${TURNO:-}" dados docs
