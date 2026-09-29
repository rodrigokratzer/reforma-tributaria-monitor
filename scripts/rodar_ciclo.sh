#!/usr/bin/env bash
# Um ciclo completo: DOU -> 12 portais -> analise -> alerta. Roda as 05:00
# (matinal) e as 17:00 (noturna) pelo reforma-ciclo.timer.
#
# As raias continuam scripts separados (cada uma faz o proprio pull/commit/
# push), e a falha de uma nao impede as seguintes: DOU fora do ar nao pode
# segurar a varredura dos portais, nem a analise do que chegou. No fim o
# alerta sai sempre - com o resultado, ou com o que falhou.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python3
TURNO="${TURNO:-$($PY -c 'import sys; sys.path.insert(0,"scripts"); import lacuna_analise as l; print(l.turno_atual())')}"
export TURNO
echo "=== ciclo $TURNO $(date '+%Y-%m-%d %H:%M') ==="

falhas=()
scripts/rodar_dou.sh       || falhas+=("coleta do DOU")
scripts/rodar_varredura.sh || falhas+=("varredura dos portais")
scripts/rodar_analise.sh "$TURNO" || falhas+=("analise $TURNO")

if [ ${#falhas[@]} -eq 0 ]; then
  $PY scripts/notificar.py
  echo "=== ciclo $TURNO ok ==="
  exit 0
fi

lista=$(printf '%s, ' "${falhas[@]}"); lista=${lista%, }
echo "=== ciclo $TURNO com falha: $lista ===" >&2
# A analise pode ter saido mesmo com uma coleta falhando: nesse caso o alerta
# normal tambem vai, para quem le nao perder o conteudo por causa do aviso.
if [[ "$lista" != *analise* ]]; then
  $PY scripts/notificar.py
fi
$PY scripts/notificar.py --falha "Ciclo $TURNO de $(date +%d/%m) com falha em: $lista. Ver journalctl -u reforma-ciclo.service no lenovo-claude."
exit 1
