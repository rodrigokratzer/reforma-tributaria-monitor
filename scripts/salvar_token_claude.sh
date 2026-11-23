#!/usr/bin/env bash
# Grava a chave de 1 ano do Claude (gerada por `claude setup-token`) para as
# rotinas do lenovo-claude, SEM mostrar a chave na tela nem em log.
#
#   1. claude setup-token            (autoriza no navegador e copia a chave)
#   2. scripts/salvar_token_claude.sh (cola a chave quando pedir; nada aparece)
#
# A chave fica em ~/.config/claude-token/token.env (só o rodrigo lê). As rotinas
# que usam o Claude a recebem pelo drop-in claude-token.conf do systemd
# (CLAUDE_CODE_OAUTH_TOKEN vale antes do login comum). A data de hoje vai para
# criado_em, que o aviso de vencimento (aviso_token_claude.py) lê.
set -euo pipefail
PASTA="$HOME/.config/claude-token"
ARQ="$PASTA/token.env"
export PATH="$HOME/.local/bin:$PATH"

printf 'Cole a chave do "claude setup-token" e tecle Enter DUAS vezes (ela não aparece): '
# A chave é longa e costuma vir quebrada em várias linhas quando copiada do
# terminal: junta todas as linhas coladas até um Enter vazio (antes, só a 1ª
# linha era lida e a chave chegava cortada; 23/11/2026).
token=""
while IFS= read -rs linha; do
  [ -z "${linha//[$'\t\r ']/}" ] && [ -n "$token" ] && break
  token+="$linha"
done
echo
token="${token//[$'\t\r\n ']/}"
echo "Recebi uma chave com ${#token} caracteres."
if [ -z "$token" ]; then
  echo "Nenhuma chave colada. Nada foi gravado." >&2
  exit 1
fi
case "$token" in
  sk-ant-*) ;;
  *) echo "Isso não parece a chave do setup-token (ela começa com sk-ant-). Nada foi gravado." >&2
     exit 1 ;;
esac

echo "Testando a chave com uma pergunta curta ao Claude..."
saida=$(env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN CLAUDE_CODE_OAUTH_TOKEN="$token" \
  timeout 120 claude -p "responda só OK" --output-format json 2>&1) || true
if ! printf '%s' "$saida" | python3 -c '
import json, sys
d = json.loads(sys.stdin.read())
sys.exit(0 if not d.get("is_error") and "OK" in str(d.get("result", "")) else 1)
' 2>/dev/null; then
  echo "A chave NÃO funcionou. Nada foi gravado. Resposta do Claude:" >&2
  printf '%s\n' "$saida" | grep -o '"result":"[^"]*"' | head -1 >&2 || true
  exit 1
fi

umask 077
mkdir -p "$PASTA"
chmod 700 "$PASTA"
tmp=$(mktemp "$PASTA/.token.XXXXXX")
printf 'CLAUDE_CODE_OAUTH_TOKEN=%s\n' "$token" > "$tmp"
mv "$tmp" "$ARQ"
date +%F > "$PASTA/criado_em"
unset token
echo "Chave gravada em $ARQ (só o seu usuário lê) e testada: funcionou."
echo "Ela vale 1 ano; o aviso de vencimento começa 30 dias antes ($(date -d '+335 days' +%d/%m/%Y))."
