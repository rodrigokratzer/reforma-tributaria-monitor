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

Instruções para quem (ou o que) escreve `analises/AAAA-MM-DD-<turno>.md`. O objetivo é
o mesmo de toda análise manual já publicada no projeto: separar o que exige
ação do que é só contexto, e explicar o impacto em termos que um contador ou
um cliente entenda — não apenas descrever o que foi publicado.

## Ciclos, entradas e saídas

A rotina roda duas vezes por dia: turno **matinal** (05h) e turno **noturna**
(17h). Cada execução analisa só o que ainda não foi analisado por nenhuma
execução anterior — a lista já vem pronta no arquivo de lacuna indicado no
prompt (mesmo formato da saída de `scripts/lacuna_analise.py`; cada item traz
o campo `chave`). Não recalcule a lacuna e não analise itens fora dela.

Toda execução grava **exatamente três arquivos** e mais nada:

1. `analises/AAAA-MM-DD-<turno>.md` — a análise (formato abaixo). **Sempre**,
   mesmo sem novidade relevante: o painel guarda o histórico de todas as
   execuções, e quem abre um dia precisa ler o que chegou e por que não
   importa.
2. `dados/analise_status.json` — status da execução (formato abaixo).
3. `dados/triagem_pendente.json` — um veredito por item da lacuna (formato
   abaixo).

**Não rode nenhum comando git.** Um script valida os três arquivos, marca os
itens como analisados e faz o commit. Se faltar algum arquivo, ou se o status
vier com data/turno diferentes dos do prompt, a execução inteira é descartada
e os itens voltam para a próxima.

## Estrutura

Uma análise segue, nesta ordem, só as seções que tiverem conteúdo:

1. **Título de uma linha em negrito**, resumindo o achado do período. Ex:
   `**30 itens novos entre 18 e 20/08; três importam, e um deles é urgente.**`
   O intervalo de datas do título vem de `dias_com_dados_na_janela` no
   arquivo de lacuna — primeiro e último dia dessa lista (se for um dia só,
   cite só ele), não invente o período de outra forma.
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

Cada item de `itens` (no arquivo de lacuna) pode trazer um
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

Escreva mesmo assim `analises/AAAA-MM-DD-<turno>.md`, curto: título em negrito
(ex.: `**12 itens novos em 29/09; nenhum muda prazo ou obrigação.**`) e um
parágrafo de 2 a 4 frases agrupando o que chegou e por que ficou de fora
(ex.: "9 portarias da SUSEP sobre autorização de seguradoras, 2 soluções de
consulta de IRPJ..."). Sem as seções de Ação/Acompanhar. Grave o status com
`"situacao": "sem_novidade"`.

### Gravando o status da execução

Ao final de toda execução — com novidade, sem novidade, ou com dados do dia
ainda não disponíveis — grave (sobrescrevendo) `dados/analise_status.json`:

```json
{"data": "AAAA-MM-DD", "turno": "matinal|noturna",
 "situacao": "publicada|sem_novidade|dados_pendentes", "acoes": 1,
 "gerado_em": "AAAA-MM-DDTHH:MM:SSZ", "resumo_curto": "3 novidades, 1 exige ação"}
```

- `data` e `turno` são exatamente os do prompt.
- `acoes` é o número de itens na seção "Ação requerida" (0 se não houver). É
  ele que decide se o alerta no celular sai com prioridade alta.
- `resumo_curto` é uma frase curta, no estilo do título, contando quantas
  novidades e quantas exigem ação — vai no alerta (push/e-mail), então
  precisa se sustentar sozinha. Em `sem_novidade`, algo como "12 itens, nenhum
  relevante".

### Triagem por item (`dados/triagem_pendente.json`)

O filtro do DOU marca muitos itens como `revisar` — é um filtro largo de
propósito (ver armadilhas abaixo). Quem fecha a questão é você: para **cada**
item da lacuna, de qualquer fonte, grave um veredito. O painel mostra esse
veredito no lugar de "revisar" e deixa o leitor esconder o ruído.

```json
[{"chave": "<campo chave do item>", "veredito": "relevante",
  "motivo": "prorroga prazo de opção pelo regime regular do IBS/CBS"},
 {"chave": "...", "veredito": "ruido", "motivo": "autorização de seguradora, sem relação com a reforma"}]
```

- `relevante` — entrou em Ação requerida ou Acompanhar.
- `contexto` — entrou em Contexto, ou é da reforma mas sem efeito prático.
- `ruido` — sem relação com a reforma do consumo.
- `motivo` — uma frase curta (até ~120 caracteres), baseada no texto lido.
- Use a `chave` exatamente como veio; chave inventada é descartada.

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
