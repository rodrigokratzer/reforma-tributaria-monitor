#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
# Mesmo tratamento das outras duas raias (M3). Aqui importa ainda mais: este
# script nao usa 'set -e', entao sem esta guarda um rebase conflitado seguiria
# adiante e o claude acabaria commitando/empurrando em cima de um checkout
# parado no meio do rebase.
if ! git pull --rebase --autostash -q; then
  echo "git pull --rebase falhou - abortando rebase para deixar o checkout limpo" >&2
  git rebase --abort 2>/dev/null || true
  exit 1
fi

PROMPT="Leia scripts/analise_brief.md e siga as instrucoes dele por completo, para a data de hoje ($(date +%Y-%m-%d)). Rode scripts/lacuna_analise.py para obter a lacuna de cobertura, aplique o criterio do brief aos itens novos, e produza a saida exatamente como o brief especifica: analises/AAAA-MM-DD.md quando houver novidade relevante, ou so dados/analise_status.json quando nao houver. Ao final, se analises/ ou dados/analise_status.json mudaram, faca 'git add', commit com mensagem no formato 'analise AAAA-MM-DD: <resumo curto>' e 'git push'. Nao pergunte nada - decida e execute sozinho."

# Fora de /tmp: /tmp e apagado no reboot, e era justamente ali que ficava a
# unica copia da saida do claude. Em ~/.local/state a saida sobrevive.
SAIDA="$HOME/.local/state/reforma/analise-ultima-saida.json"
mkdir -p "$(dirname "$SAIDA")"

# 'tee' em vez de redirecionamento simples: alem de gravar em $SAIDA, o JSON
# cru vai para stdout, que o systemd captura no journal. Sem isso, o
# 'journalctl -u reforma-analise.service' fica vazio, ao contrario das outras
# duas raias, que imprimem progresso em stderr naturalmente.
# Com 'set -o pipefail' (linha 2), $? depois do pipe reflete a falha do
# 'claude', nao a do 'tee'.
claude -p "$PROMPT" --permission-mode bypassPermissions --output-format json \
  | tee "$SAIDA"
codigo=$?

if [ $codigo -ne 0 ]; then
  echo "claude -p saiu com codigo $codigo - analise diaria NAO concluida. Ver $SAIDA" >&2
  exit $codigo
fi

# Codigo 0 nao prova que a analise saiu: o claude pode encerrar limpo tendo
# batido num limite de uso, recusado a tarefa, ou simplesmente nao gravado
# nada. O contrato do brief e que toda execucao boa atualize
# dados/analise_status.json com a data de hoje - se isso nao aconteceu, a
# raia falhou, e o systemd precisa enxergar isso.
hoje=$(date +%Y-%m-%d)
if ! .venv/bin/python3 -c "
import json, sys
d = json.load(open('dados/analise_status.json'))
sys.exit(0 if d.get('data') == '$hoje' else 1)
"; then
  echo "claude -p saiu com codigo 0 mas dados/analise_status.json nao reflete a data de hoje ($hoje) - a analise pode nao ter sido produzida de verdade" >&2
  exit 1
fi

resumo=$(.venv/bin/python3 -c "import json; d=json.load(open('$SAIDA')); print(str(d.get('result',''))[:300])" 2>/dev/null || echo "(nao foi possivel extrair resumo)")
echo "Resultado: $resumo"

echo "Analise diaria concluida (codigo 0)."
