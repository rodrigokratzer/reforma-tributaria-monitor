#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# publicar.sh resolve sozinho conflito em docs/ (gerado); qualquer outro
# conflito aborta o rebase, deixando o checkout limpo e a falha no journal.
scripts/publicar.sh --sincronizar || exit 1
.venv/bin/python3 scripts/varredura.py
.venv/bin/python3 scripts/gerar_painel.py
# Publica a coleta ANTES de ler: a raia de leitura leva ate' 45 min (OCR) e,
# se o dados/<hoje>.json ainda nao estivesse no remoto, o fallback do GitHub
# Actions coletaria por cima e o push local abortaria em conflito fora de docs/.
scripts/publicar.sh "varredura $(date +%Y-%m-%d) ${TURNO:-}" dados docs
# Raia de leitura: texto integral (HTML, PDF, OCR) de tudo que ainda nao tem.
# Falha aqui nao segura a publicacao: o que nao foi lido fica como `falhou` em
# dados/leituras.json e e' tentado de novo no proximo ciclo. Mas nao pode ser
# silenciosa: o status vira o codigo de saida 3 no fim (rodar_ciclo.sh avisa).
rc_leitura=0
.venv/bin/python3 scripts/ler_textos.py || rc_leitura=$?
# Leis-base (normas/): baixa de novo se a compilacao tem >= 7 dias ou se o
# ciclo coletou lei complementar / emenda / "altera a LC 214". Nao fatal:
# as normas anteriores ficam e o erro vai para dados/normas_status.json.
.venv/bin/python3 scripts/baixar_normas.py --se-necessario \
  || echo "AVISO: baixar_normas.py falhou (normas anteriores mantidas)" >&2
.venv/bin/python3 scripts/gerar_painel.py
# publicar.sh ja' trata "nada mudou".
scripts/publicar.sh "leitura $(date +%Y-%m-%d) ${TURNO:-}" dados docs normas
if [ "$rc_leitura" -ne 0 ]; then
  echo "AVISO: ler_textos.py saiu com $rc_leitura (publicado mesmo assim)" >&2
  exit 3
fi
