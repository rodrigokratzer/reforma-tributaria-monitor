#!/usr/bin/env bash
# Commit + push resiliente, usado pelas tres raias. Uso: publicar.sh "mensagem" caminho...
# Sem caminhos (publicar.sh --sincronizar): so' absorve o remoto e empurra
# commits locais pendentes - e' o passo inicial de cada raia.
#
# Por que existe: em 30/09/2026 o primeiro ciclo novo caiu inteiro porque o
# GitHub Actions tinha acabado de commitar um docs/index.html regenerado, e o
# rebase local conflitou nesse arquivo. docs/ e' 100% gerado a partir de
# dados/ + analises/, entao conflito ali nao e' conflito de verdade: basta
# regenerar o painel sobre o estado ja' rebaseado. Conflito em qualquer outro
# arquivo continua abortando (checkout limpo, falha visivel no journal).
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python3
msg="${1:?uso: publicar.sh mensagem caminho... | publicar.sh --sincronizar}"; shift

if [ "$msg" != "--sincronizar" ]; then
  git add "$@"
  # sem mudanca, nao commita - mas segue para o push: pode haver commit
  # local pendente (ex.: um merge feito antes) que precisa subir
  if git diff --staged --quiet; then
    echo "Nada mudou ($msg)."
  else
    git commit -q -m "$msg"
  fi
fi

for tentativa in 1 2 3 4 5; do
  git fetch -q
  absorveu=0
  if ! git merge-base --is-ancestor @{u} HEAD 2>/dev/null; then absorveu=1; fi
  if ! git pull --rebase --autostash -q; then
    # pode haver varios commits a reaplicar; cada parada resolve do mesmo jeito
    passos=0
    while [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; do
      passos=$((passos + 1))
      if [ $passos -gt 30 ]; then
        echo "rebase nao converge - abortando" >&2
        git rebase --abort 2>/dev/null || true
        exit 1
      fi
      conflitos=$(git diff --name-only --diff-filter=U)
      if [ -n "$conflitos" ]; then
        if echo "$conflitos" | grep -qv '^docs/'; then
          echo "conflito fora de docs/ ($conflitos) - abortando rebase" >&2
          git rebase --abort 2>/dev/null || true
          exit 1
        fi
        $PY scripts/gerar_painel.py >/dev/null && git add docs
      fi
      # commit que ficou vazio depois de resolvido (so' mexia no painel): pula
      GIT_EDITOR=true git rebase --continue >/dev/null 2>&1 \
        || GIT_EDITOR=true git rebase --skip >/dev/null 2>&1 || true
    done
  fi
  # Se o remoto trouxe commits, o painel local foi gerado sobre um estado
  # antigo: regenera sobre o estado final. Sem nada novo, nao regenera (o
  # carimbo de hora mudaria e geraria commit vazio de sentido).
  if [ "$absorveu" = 1 ]; then
    $PY scripts/gerar_painel.py >/dev/null && git add docs
    git diff --staged --quiet || git commit -q -m "painel $(date +%Y-%m-%d)"
  fi
  if [ -z "$(git log @{u}..HEAD --oneline 2>/dev/null)" ] || git push -q; then
    exit 0
  fi
  echo "push recusado (tentativa $tentativa) - absorvendo o remoto e repetindo" >&2
  sleep $((tentativa * 5))
done
echo "push falhou apos 5 tentativas" >&2
exit 1
