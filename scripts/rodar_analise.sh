#!/usr/bin/env bash
# Raia da analise de um ciclo (matinal ou noturna). Uso: rodar_analise.sh TURNO
#
# Diferenca em relacao a antiga rodar_analise_diaria.sh: o claude so' escreve
# arquivos. Quem valida, marca os itens como analisados, regenera o painel e
# faz commit/push e' este script - a parte nao deterministica fica menor, e
# uma execucao que bateu em limite de uso nao marca nada como analisado.
set -uo pipefail
cd "$(dirname "$0")/.."
TURNO="${1:?uso: rodar_analise.sh matinal|noturna}"
HOJE=$(date +%Y-%m-%d)
PY=.venv/bin/python3

# Mesma guarda das outras raias: rebase conflitado nao pode seguir adiante.
scripts/publicar.sh --sincronizar || exit 1

ESTADO="$HOME/.local/state/reforma"
mkdir -p "$ESTADO"
LACUNA="$ESTADO/lacuna-$HOJE-$TURNO.json"
SAIDA="$ESTADO/analise-$HOJE-$TURNO.json"
ARQ="analises/$HOJE-$TURNO.md"

# A lacuna e' congelada aqui, antes do claude: as chaves marcadas como
# analisadas no fim sao exatamente as que ele recebeu, nem uma a mais.
$PY scripts/lacuna_analise.py "$HOJE" > "$LACUNA" || exit 1
n=$($PY -c "import json,sys; print(len(json.load(open(sys.argv[1]))['itens']))" "$LACUNA")

if [ "$n" -eq 0 ]; then
  # Nada novo desde a ultima analise: nao gasta uma chamada do claude, mas
  # deixa registro do ciclo, para o historico do painel nao ter buraco.
  aguard=$($PY -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('aguardando_leitura', [])))" "$LACUNA" 2>/dev/null || echo 0)
  if [ "${aguard:-0}" -gt 0 ]; then
    cat > "$ARQ" <<EOF
**Sem publicações para analisar neste ciclo.**

$aguard publicação(ões) aguardando a leitura do texto integral; entram na próxima análise.
EOF
  else
    cat > "$ARQ" <<EOF
**Sem publicações novas desde a última análise.**

Nenhuma das fontes monitoradas trouxe item novo neste ciclo ($TURNO de $(date +%d/%m/%Y)).
EOF
  fi
  $PY - "$HOJE" "$TURNO" <<'EOF'
import json, sys, datetime
json.dump({"data": sys.argv[1], "turno": sys.argv[2], "situacao": "sem_novidade",
           "acoes": 0,
           "gerado_em": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "resumo_curto": "nenhuma publicação nova"},
          open("dados/analise_status.json", "w"), ensure_ascii=False)
EOF
  resumo="sem publicacoes novas"
else
  PROMPT="Leia scripts/analise_brief.md e siga as instrucoes dele por completo. Data de hoje: $HOJE. Turno: $TURNO. A lacuna de cobertura (os $n itens que voce deve analisar, com o texto integral quando disponivel) ja foi calculada e esta em $LACUNA - leia esse arquivo, nao rode lacuna_analise.py de novo. Produza os tres arquivos obrigatorios que o brief especifica: $ARQ, dados/analise_status.json (com data=$HOJE e turno=$TURNO) e dados/triagem_pendente.json (um veredito para cada um dos $n itens). Siga tambem a secao 'Manter o painel em dia': se algum item mudar prazo, pendencia ou marco (ou houver prazo em destaque vencido), grave dados/estado_proposta.json - nunca edite estado.json direto. NAO rode nenhum comando git - o commit e feito depois por outro script. Nao pergunte nada - decida e execute sozinho."

  # tee: a saida crua vai para o journal (systemd) e para $SAIDA.
  claude -p "$PROMPT" --permission-mode bypassPermissions --output-format json | tee "$SAIDA"
  codigo=$?
  if [ $codigo -ne 0 ]; then
    echo "claude -p saiu com codigo $codigo - analise $TURNO NAO concluida. Ver $SAIDA" >&2
    exit $codigo
  fi
  resumo=$($PY -c "import json; print(json.load(open('dados/analise_status.json')).get('resumo_curto','')[:90])" 2>/dev/null || echo "")
  # estado.json so' muda pela proposta validada (atualizar_estado.py): se o
  # claude editou o arquivo direto, a edicao e' desfeita aqui
  git checkout -- estado.json 2>/dev/null || true
fi

# Codigo 0 do claude nao prova nada (limite de uso, recusa). fechar_analise
# confere arquivo e status do turno; se faltar algo, sai 1 e nada e' marcado.
if ! $PY scripts/fechar_analise.py "$HOJE" "$TURNO" "$LACUNA"; then
  echo "fechar_analise recusou o resultado - itens continuam pendentes para o proximo ciclo" >&2
  # O que o claude escreveu vai para $ESTADO (para diagnostico), nao fica
  # solto no checkout, onde o 'git add analises' do proximo ciclo o pegaria.
  mv -f "$ARQ" "$ESTADO/" 2>/dev/null || true
  mv -f dados/triagem_pendente.json "$ESTADO/triagem_pendente-$HOJE-$TURNO.json" 2>/dev/null || true
  mv -f dados/estado_proposta.json "$ESTADO/estado_proposta-$HOJE-$TURNO.json" 2>/dev/null || true
  git checkout -- dados/analise_status.json 2>/dev/null || true
  exit 1
fi

$PY scripts/gerar_painel.py >/dev/null
scripts/publicar.sh "analise $HOJE $TURNO: ${resumo:-ver analise}" analises dados docs estado.json || exit 1
echo "Analise $TURNO concluida ($n itens)."
