# Brief da análise diária

Instruções para quem (ou o que) escreve `analises/AAAA-MM-DD.md`. O objetivo é
o mesmo de toda análise manual já publicada no projeto: separar o que exige
ação do que é só contexto, e explicar o impacto em termos que um contador ou
um cliente entenda — não apenas descrever o que foi publicado.

## Estrutura

Uma análise segue, nesta ordem, só as seções que tiverem conteúdo:

1. **Título de uma linha em negrito**, resumindo o achado do período. Ex:
   `**30 itens novos entre 18 e 20/08; três importam, e um deles é urgente.**`
   O intervalo de datas do título vem de `dias_com_dados_na_janela` na saída
   de `scripts/lacuna_analise.py` — primeiro e último dia dessa lista, não
   invente o período de outra forma.
2. **### Ação requerida** — itens que mudam prazo, obrigação ou decisão de
   alguém. Cada item:
   - título em negrito com o achado principal, fonte e data
   - `**Antes:**` / `**Agora:**` quando houver mudança de regra
   - `**Impacto para o cliente:**` em termos práticos, não jurídicos
   - `**O que não resolve:**` quando a norma deixa algo em aberto
   - `**Fonte:**` link
3. **### Acompanhar** — relevante, mas sem ação imediata. Mesmo formato,
   mais enxuto.
4. **### Contexto** — publicações que não afetam o contribuinte (ex:
   governança interna, nomeação de diretoria). Uma ou duas frases, sem as
   subseções acima.
5. **### No radar** — prazos próximos relevantes, formato `**N dias** — DD/MM:
   descrição`. Os prazos vêm de `estado.json` (`prazos_destaque` e
   `pendencias`, campo `data`/`prazo`); "N dias" é a diferença entre essa
   data e a data de hoje, arredondada. Não invente prazo que não esteja lá.
6. **### Nota sobre a coleta** — só quando houver algo digno de registro sobre
   a qualidade da coleta do período (ex: taxa de falso positivo do filtro,
   fonte que falhou).

Cada afirmação de que um item "não tem relação com a reforma" precisa vir de
uma ementa/texto que você realmente leu — nunca do órgão ou da fonte sozinhos
(ver armadilha abaixo). Quando um grupo de itens não tiver ementa disponível
na coleta, diga isso explicitamente e separe esse grupo do que foi
confirmado por leitura — não junte os dois sob a mesma afirmação categórica.

### Marcadores de proveniência

Cada item citado na seção "Ação requerida" ou "Acompanhar" leva uma marca
entre colchetes ao lado da fonte, indicando como a informação foi obtida:

- `` `[VERIFICADO LITERAL]` `` — você leu o texto integral do ato/norma (PDF,
  página do órgão) e a análise se apoia nesse texto.
- `` `[PESQUISA]` `` — você não teve acesso ao texto integral (bloqueado,
  paywall, captcha) e a classificação se apoia em outros sinais (ementa,
  título, contexto do período). Precisa vir acompanhada de uma frase
  reconhecendo a limitação.

### Sem novidade relevante

Não escreva o arquivo `analises/AAAA-MM-DD.md` nesse caso. Grave
`dados/analise_status.json` com `"situacao": "sem_novidade"` (ver formato
abaixo) — é esse arquivo, não a ausência da análise, que sinaliza ao painel
que a rotina rodou e não achou nada.

### Gravando o status da execução

Ao final de toda execução — com novidade, sem novidade, ou com dados do dia
ainda não disponíveis — grave (sobrescrevendo) `dados/analise_status.json`:

```json
{"data": "AAAA-MM-DD", "situacao": "publicada|sem_novidade|dados_pendentes",
 "gerado_em": "AAAA-MM-DDTHH:MM:SSZ", "resumo_curto": "3 novidades, 1 exige ação"}
```

`resumo_curto` só se aplica a `situacao: "publicada"` — uma frase curta
contando quantas novidades e quantas exigem ação, no mesmo estilo do título
da análise. Omita o campo (ou deixe vazio) nos outros dois casos.

## Critério de relevância

- **Muda prazo, obrigação, ou decisão de um contribuinte real** → Ação
  requerida.
- **Afeta como um sistema ou processo deve ser ajustado, mesmo sem prazo
  formal** → Acompanhar.
- **Ato interno do órgão sem efeito externo** (eleição de diretoria, ata de
  reunião, ajuste de convênio) → Contexto, ou nem cite.
- **Extrato de contrato, edital de licitação, aviso de dispensa, resultado de
  julgamento administrativo sem relação com a reforma** → não cite. É ruído
  do filtro, não notícia.

## Armadilhas conhecidas (do README do projeto)

- **Data declarada pode estar errada.** Antes de tratar uma publicação como
  antiga ou fora de janela, confira contra a pasta de upload do arquivo, não
  só a data no título.
- **Nunca julgue relevância pelo remetente ou pela URL conterem o termo.**
  `cgibs.gov.br` contém "cgibs", "Comitê Gestor do IBS" contém "IBS" — isso
  não torna o conteúdo relevante. O termo tem que estar no *assunto* da
  publicação.
- **Item "forte" do filtro do DOU pode ser falso positivo** (ex: ato de
  jurisdição de tribunal). Leia a ementa antes de classificar.
- **Proposta não é norma.** Uma resolução do CGIBS que propõe um percentual
  não fixa alíquota. Estimativa divulgada na imprensa não é norma.

## Tom

Direto, sem jargão desnecessário. Frases curtas. Quando o impacto for para
"o cliente" (contador que usa o painel para aconselhar clientes), diga o que
muda na prática — não apenas cite o dispositivo legal.
