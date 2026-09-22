#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
git pull --rebase --autostash -q

PROMPT="Leia scripts/analise_brief.md e siga as instrucoes dele por completo, para a data de hoje ($(date +%Y-%m-%d)). Rode scripts/lacuna_analise.py para obter a lacuna de cobertura, aplique o criterio do brief aos itens novos, e produza a saida exatamente como o brief especifica: analises/AAAA-MM-DD.md quando houver novidade relevante, ou so dados/analise_status.json quando nao houver. Ao final, se analises/ ou dados/analise_status.json mudaram, faca 'git add', commit com mensagem no formato 'analise AAAA-MM-DD: <resumo curto>' e 'git push'. Nao pergunte nada - decida e execute sozinho."

claude -p "$PROMPT" --permission-mode bypassPermissions --output-format json \
  > /tmp/reforma-analise-ultima-saida.json
codigo=$?

if [ $codigo -ne 0 ]; then
  echo "claude -p saiu com codigo $codigo - analise diaria NAO concluida. Ver /tmp/reforma-analise-ultima-saida.json" >&2
  exit $codigo
fi

echo "Analise diaria concluida (codigo 0)."
