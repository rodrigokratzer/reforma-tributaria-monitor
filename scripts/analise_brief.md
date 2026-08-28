# Brief da análise diária

## Objetivo do projeto — leia isto antes de tudo

Ser a fonte de dados confiável e completa, que analisa todas as informações
completas das fontes de publicações, gera relatórios diários do que é
importante e facilita a vida dos consultores e dos clientes. O objetivo é
automatizar o acompanhamento das novas publicações e trazer o que realmente
importa para quem lê o painel. Seja a real inteligência sobre as novas
publicações da reforma tributária.

Isso tem uma consequência direta em como você escreve: **o painel é sobre as
publicações, não sobre esta rotina.** Detalhe técnico de coleta (rede
bloqueada, ementa vazia, fonte fora do ar) é rodapé, não manchete — nunca a
primeira coisa que quem lê encontra, e nunca mais espaço do que o próprio
conteúdo relevante do dia.

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
6. **### Nota sobre a coleta** — regras próprias, ver seção dedicada abaixo.
   Sempre a última seção, nunca a primeira nem a mais longa.

Cada afirmação de que um item "não tem relação com a reforma" precisa vir de
uma ementa/texto que você realmente leu — nunca do órgão ou da fonte sozinhos
(ver armadilha abaixo).

## Leia o texto completo antes de classificar — ele já está no repositório

Cada item de `itens` (saída de `scripts/lacuna_analise.py`) pode trazer um
campo `texto` com o corpo integral da publicação, já extraído na coleta —
você não precisa (e não deve) sair buscando na web para ler o que já está
ali. Isso vale hoje para os itens do DOU; a mesma ideia deve se estender aos
outros portais quando a coleta deles também passar a capturar o texto.

- **Se o item tem `texto` preenchido:** leia esse campo inteiro antes de
  classificar. É a fonte primária — marque `[VERIFICADO LITERAL]`.
- **Se o item não tem `texto` (ou vem vazio) e você precisou buscar na web
  para entender do que se trata:** marque `[PESQUISA]` e diga, em uma frase,
  que a leitura veio de cobertura de terceiros, não do texto oficial.
- Não gaste espaço da análise explicando *por que* um item não tinha
  `texto` — isso é assunto da Nota sobre a coleta (curta, no fim), não do
  corpo do achado.

### Marcadores de proveniência

Cada item citado na seção "Ação requerida" ou "Acompanhar" leva uma marca
entre colchetes ao lado da fonte, indicando como a informação foi obtida:

- `` `[VERIFICADO LITERAL]` `` — você leu o texto integral do ato/norma (campo
  `texto` do item, PDF, página do órgão) e a análise se apoia nesse texto.
- `` `[PESQUISA]` `` — você não teve acesso ao texto integral (sem campo
  `texto`, bloqueado, paywall, captcha) e a classificação se apoia em outros
  sinais (ementa, título, cobertura de terceiros). Precisa vir acompanhada de
  uma frase reconhecendo a limitação.

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
  jurisdição de tribunal). Leia a ementa/texto antes de classificar — "forte"
  é só o filtro por palavra-chave tendo mais certeza, não uma revisão feita.
- **O campo `balde` do DOU (`forte`/`revisar`) é só um sinal de força do
  filtro por palavra-chave, não uma revisão feita.** Todo item que chega até
  você — de qualquer balde — precisa da sua leitura de verdade antes de virar
  Contexto ou ser descartado da análise. "revisar" não significa "ainda
  pendente"; significa "o filtro automático teve menos certeza", e é
  exatamente por isso que existe uma IA lendo depois.
- **Proposta não é norma.** Uma resolução do CGIBS que propõe um percentual
  não fixa alíquota. Estimativa divulgada na imprensa não é norma.

## Nota sobre a coleta (seção do texto final)

Só escreva esta seção quando sobrar uma lacuna real depois de aplicar tudo
acima — por exemplo, um grupo de itens sem `texto` e sem cobertura de
terceiros localizável, ou uma fonte inteira fora do ar no período. **Teto de
2 a 3 frases.** Não é o lugar para narrar o processo de coleta, listar
tentativas de busca, ou explicar mecanismos internos do projeto — é uma nota
de rodapé para quem quiser saber onde a cobertura ficou incompleta, não a
história do que a rotina teve que fazer para chegar lá.

## Tom

Direto, sem jargão desnecessário. Frases curtas. Quando o impacto for para
"o cliente" (contador que usa o painel para aconselhar clientes), diga o que
muda na prática — não apenas cite o dispositivo legal.
