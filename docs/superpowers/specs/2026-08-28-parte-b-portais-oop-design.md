# Parte B — Portais web orientados a objetos

**Status:** aguardando revisão do usuário (design elaborado sem interação
em tempo real — ver nota abaixo).

**Nota de processo:** este spec foi escrito enquanto o usuário estava
ausente ("consegue seguir a parte B... ficarei ausente", depois "continue
o trabalho, tive que desligar o mac"). Sem possibilidade de perguntas
síncronas, as decisões de design abaixo foram tomadas com base no que já
tinha sido combinado nesta conversa (ver "Decisões assumidas sem
confirmação" no fim) — não foi seguido o fluxo pergunta-a-pergunta padrão
do brainstorming. **Implementação não deve começar até o usuário revisar
este documento.**

## Objetivo

Reestruturar `scripts/varredura.py` — hoje uma lista plana de 12 tuplas
`(nome, url, precisa_js)` processadas por funções genéricas e compartilhadas
— para que cada portal seja um objeto com suas próprias regras (filtro de
relevância, extração de texto completo), sem alterar o comportamento
observável dos 11 portais que não ganham regra nova nesta rodada.

Motivação, nas palavras do usuário: *"seria oportuno trabalharmos como
programação orientada em objetos, para que cada consulta seja individual e
possamos criar regras especificas para cada uma. Inclusive caso eu preciso
incluir novos sites ou portais para varredura."*

Isso serve diretamente o objetivo maior do projeto (`scripts/analise_brief.md`):
quanto mais portais capturarem texto completo na coleta (rede livre, sem
IA), menos a análise diária depende de busca externa bloqueada pelo sandbox
— o mesmo ganho que a Parte A já trouxe para o DOU.

## Estado atual (`scripts/varredura.py`)

- `FONTES`: lista de 12 tuplas `(nome, url, precisa_js)` — dado puro, sem
  comportamento.
- `coleta(ctx, nome, url, precisa_js)`: para cada fonte, tenta 2x via
  `via_browser()`, cai para `via_http()` se o browser falhar. Igual para
  todos os 12 portais.
- `filtra(pares)`: aplica **um único regex global** (`RELEVANTE`) contra
  título e caminho da URL — igual para todos os 12 portais, sem exceção.
- `monta_item(titulo, url)`: extrai data declarada, compara com a pasta do
  arquivo, gera alerta se implausível — lógica genérica, não específica de
  portal.
- Nenhum dos 12 portais extrai texto completo do artigo — só título +
  URL chegam ao `historico.json`. (Contraste: `scripts/dou.py`, que já
  extrai texto completo do XML do INLABS — é o modelo que esta Parte B
  estende aos portais web.)
- `coleta_dou()` já vive fora do loop de `FONTES`, roda em workflow
  próprio (`dou.yml`, 02h) — não é afetada por esta mudança.

## Decisão de arquitetura

### Classe base `Portal`

Novo pacote `scripts/portais/`:

- `scripts/portais/base.py` — classe `Portal`:
  - Atributos de instância: `nome`, `url`, `precisa_js`.
  - Método `coletar(self, ctx) -> dict`: **hoje é a função `coleta()`
    inteira, virando método.** Mesma mecânica (2 tentativas via browser,
    fallback HTTP, aba isolada por fonte) — nenhuma mudança de
    comportamento aqui. Chama `self.filtro_relevancia()` e, quando
    aplicável, `self.extrai_texto()` internamente.
  - Método `filtro_relevancia(self, texto, url) -> bool`: **default =
    comportamento atual de `filtra()`** (regex `RELEVANTE` global contra
    título e `caminho_normalizado(url)`). Subclasses sobrescrevem só
    quando precisam de regra diferente.
  - Método `extrai_texto(self, ctx, item) -> str | None`: **default =
    `None`** (preserva o comportamento de hoje: nenhum portal captura
    texto completo). Só é chamado para itens que já passaram em
    `filtro_relevancia` — nunca para o volume bruto de links de uma
    página.
  - `monta_item()` e as funções utilitárias de data
    (`extrai_data`, `data_do_arquivo`, `caminho_normalizado`) continuam
    como funções livres em `scripts/portais/base.py` (ou permanecem em
    `varredura.py` e são importadas) — são genéricas, não pertencem a
    nenhum portal específico.

- `scripts/portais/cgibs.py` — classe `CGIBSPortal(Portal)`:
  - Sobrescreve `extrai_texto()`: visita a página do artigo (via `ctx`,
    reaproveitando a mesma sessão de browser já aberta) e extrai o
    corpo do texto — mesmo padrão de "ler o que já está no repo" que a
    Parte A implementou para o DOU. As 5 fontes CGIBS (Notícias,
    Resoluções, Atos Conjuntos, Atos Técnicos, Portarias, Regulamentos,
    Leis, Relatórios — hoje 8 entradas em `FONTES` apontam para
    `cgibs.gov.br`) compartilham esta classe, uma instância por URL.
  - Sem sobrescrever `filtro_relevancia` — continua com o regex global
    padrão da base.

- `scripts/portais/registro.py` — substitui a lista `FONTES` por uma
  lista de instâncias:
  ```python
  from .base import Portal
  from .cgibs import CGIBSPortal

  PORTAIS = [
      CGIBSPortal("CGIBS - Noticias", "https://www.cgibs.gov.br/noticias"),
      CGIBSPortal("CGIBS - Resolucoes", "https://www.cgibs.gov.br/resolucoes"),
      # ... demais 6 entradas CGIBS, mesma classe
      Portal("RFB - Noticias 2026", "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026", precisa_js=False),
      Portal("RFB - Reforma do Consumo", "...", precisa_js=False),
      Portal("Portal DF-e SVRS - Noticias", "...", precisa_js=False),
      Portal("Portal NF-e - Informes/NTs", "...", precisa_js=False),
  ]
  ```
  Adicionar um portal novo sem regra especial = uma linha `Portal(...)`.
  Adicionar um portal com regra especial = uma subclasse pequena (só o
  método que muda) + uma linha no registro.

- `scripts/varredura.py` fica mais enxuto: importa `PORTAIS` de
  `scripts.portais.registro`, o loop em `main()` passa a chamar
  `portal.coletar(ctx)` em vez da função `coleta(ctx, nome, url, js)`.
  `grava_resultado()`, `coleta_dou()`, `main()` **não mudam** — já são
  genéricos, não pertencem a nenhum portal.

### Por que não todos os 12 portais ganham `extrai_texto` agora

Escopo desta rodada = CGIBS, porque foi exatamente o portal que faltou
texto completo no teste real da Parte A (item da DeRE, precisou de
`WebSearch` porque o acesso direto a `cgibs.gov.br` está bloqueado no
sandbox da rotina de análise — mas a **coleta** roda no GitHub Actions,
com rede livre, então capturar o texto ali resolve o mesmo problema que a
Parte A resolveu para o DOU). Os outros 4 portais (RFB, SVRS, NF-e) não
têm um caso comprovado de necessidade ainda — o mecanismo fica pronto
(basta sobrescrever `extrai_texto` numa subclasse) mas YAGNI não implementa
sem um item real que precise.

### Orçamento de tempo

`ORCAMENTO_S = 600` (10 min) é compartilhado por todos os portais. Visitar
a página do artigo para extrair texto é uma chamada de rede a mais **por
item que já passou no filtro de relevância** — não por link bruto da
página, o que limita o custo a poucos itens por dia (a experiência da
Parte A: 16-17 itens/dia no DOU, tipicamente 0-3 relevantes nos portais
CGIBS). Ainda assim, `CGIBSPortal.extrai_texto()` deve checar o orçamento
restante antes de visitar cada página e desistir silenciosamente (deixando
`texto=None`) se o tempo estiver perto do limite — nunca deixar a extração
de texto derrubar a coleta de links, que é a função mais importante do
script.

### Tratamento de erro

`extrai_texto()` nunca pode propagar exceção para `coletar()` — falha ao
extrair texto de um artigo específico deve resultar em `texto=None` para
aquele item (log de aviso, sem interromper a coleta dos demais links da
mesma fonte). Mantém a garantia que já existe hoje: uma fonte com problema
nunca derruba as outras 11.

## Fluxo de dados

Sem mudança de schema em `dados/*.json`/`historico.json` fora da adição
opcional do campo `texto` nos itens do CGIBS (mesmo formato que a Parte A
já trouxe para os itens do DOU) — o brief (`scripts/analise_brief.md`) já
sabe ler esse campo quando presente, nenhuma mudança necessária ali.

## Testes

- `tests/test_portais_base.py` (novo): comportamento default de
  `Portal.filtro_relevancia` — casos que hoje são cobertos implicitamente
  pelo regex `RELEVANTE` (ex: `cgibs.gov.br` sozinho não deve passar,
  título com "IBS" deve passar) viram testes explícitos pela primeira vez.
- `tests/test_portal_cgibs.py` (novo): `CGIBSPortal.extrai_texto()` contra
  um HTML de exemplo salvo como fixture (sem chamada de rede real no teste)
  — cobre extração bem-sucedida e falha graciosa (HTML inesperado → `None`,
  sem exceção).
- `tests/test_lacuna_analise.py`: não muda.

## Decisões assumidas sem confirmação do usuário

Como não houve janela para perguntas síncronas, estas escolhas foram
feitas com base no contexto já combinado e devem ser conferidas quando o
usuário revisar este spec:

1. **Escopo de `extrai_texto` limitado ao CGIBS nesta rodada**, não aos 12
   portais de uma vez. Risco se errado: usuário queria os 12 já nesta
   entrega — nesse caso é extensão direta do mesmo padrão, task adicional
   no plano de implementação.
2. **Nome do pacote `scripts/portais/`** (em vez de, por exemplo,
   `scripts/fontes/` ou manter tudo em `varredura.py`). Risco se errado:
   rename mecânico, baixo custo.
3. **CGIBS como uma única classe para as 8 URLs do site**, não uma
   subclasse por seção (Notícias vs Resoluções etc.). Assume que a
   estrutura de página é a mesma nas 8 seções do CGIBS — não verificado
   item a item nesta rodada. Se alguma seção tiver HTML diferente, vira
   ajuste dentro do mesmo método, não uma classe nova.
