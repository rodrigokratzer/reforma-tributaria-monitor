# Resumo diário: notícias do bolso + reforma (desenho, 17/11/2026)

## Por quê

O painel deixa de ser só monitor da reforma e vira o **resumo diário (matinal e
noturno)** que o Rodrigo e a Carolina Loth usam para se atualizar e tirar pauta
para as redes da Carolina (perfil sobre o bolso das pessoas e das empresas; ver
o projeto `conteudo_post`). Em vez de a Carolina consultar portais de notícia,
ela abre o painel e lê, no topo, um resumo de poucas linhas; se uma notícia
interessa, abre o detalhe logo abaixo.

Só os dois leem o painel. Copiar trecho literal da matéria é desejado (evita
reescrever), sempre com o link da fonte.

## Escopo

- Entra: notícias dos principais portais que afetam **o bolso do empreendedor**
  (MEI, pequeno negócio: imposto, crédito, juros, caixa, regras, prazos) e
  **o bolso das pessoas** (preços, conta de luz, juros, Selic, salário mínimo,
  INSS, IR, Pix, golpes financeiros, benefícios). Reforma tributária continua.
- Sai do painel: **linha do tempo** e **placar de pendências** (os dados ficam em
  `estado.json`; só não são mostrados).
- Fica: histórico das análises/resumos (seletor de edição), busca nas
  publicações antigas (agora inclui as notícias), prazos da reforma (compacto),
  fontes consultadas (recolhido).

## Caminho escolhido: C (RSS + busca extra da análise)

1. **Coletor de notícias** (`scripts/noticias.py`, camada Fatos, stdlib, sem IA):
   lê feeds RSS de economia dos portais e grava pelos caminhos de sempre.
2. **Análise** (o mesmo `claude -p` dos turnos 05h/17h) faz a triagem das
   notícias junto com as publicações, escreve o resumo estruturado e, quando um
   assunto estiver quente e os feeds não cobrirem, pode buscar na web
   (`origem: "busca"`).
3. **Painel** mostra o resumo no topo.

Alternativas descartadas: A (análise pesquisa tudo sozinha) não deixa rastro do
que foi lido nem histórico pesquisável; B puro foi preterido pelo usuário em
favor de C.

## Contrato 1: item de notícia no `dados/historico.json`

Gravado por `grava_resultado(hoje, resultado, "AAAA-MM-DD-noticias.json",
"novidades_noticias.json")` (arquivos próprios, regra "dois coletores nunca
escrevem o mesmo arquivo"). Chave = `chave()` de `portais/base.py` (URL + título).

```json
{"primeira_vez": "2026-11-17", "fonte": "g1 Economia", "tipo": "noticia",
 "titulo": "...", "url": "https://...", "data": "2026-11-17",
 "publicado_em": "2026-11-17T09:12:00-03:00",
 "ementa": "<descrição/linha fina do RSS, sem HTML, até ~600 caracteres>",
 "visto_em": "..."}
```

- `tipo: "noticia"` é o que distingue notícia de publicação oficial em todo o
  código (leitura, lacuna, fechamento, painel). Publicação oficial não tem `tipo`.
- `ementa` reaproveita o campo que o painel e a busca já usam.
- Notícias **não passam pela raia de leitura** (`ler_textos.py` as ignora) e
  **nunca ficam em `aguardando_leitura`** na lacuna. A análise abre a matéria
  na web quando quiser mais detalhe.
- Só entra notícia publicada há no máximo ~36 h (evita feed velho inundar o
  histórico na primeira execução).

## Contrato 2: resumo estruturado da análise

Arquivo `analises/resumos/AAAA-MM-DD-<turno>.json` (mesmo stem da análise `.md`),
escrito pela análise em toda execução:

```json
{"data": "2026-11-17", "turno": "matinal",
 "manchete": "Uma frase que resume a edição",
 "em_30_segundos": ["3 a 5 linhas curtas, as mais importantes primeiro"],
 "noticias": [
  {"chave": "<chave do histórico ou null quando origem=busca>",
   "tema": "empreendedor|pessoas|reforma",
   "titulo": "...", "fonte": "g1", "url": "https://...",
   "publicado_em": "AAAA-MM-DD ou ISO",
   "linha": "uma frase: o que aconteceu, em termos de dinheiro",
   "trecho": "trecho literal da matéria/ato (copiado, sem reescrever)",
   "por_que_importa": "1 a 3 frases: quanto, quem, a partir de quando",
   "ideia_post": "gancho ou ângulo para um post da Carolina (opcional)",
   "origem": "rss|busca|oficial"}],
 "lidas": 42}
```

- `noticias` em ordem de importância; tipicamente 4 a 10 itens. Reforma entra
  com `tema: "reforma"` e `origem: "oficial"` para os itens relevantes da
  análise da reforma.
- `lidas` = quantos itens (notícias + publicações) a execução avaliou.
- Opcional para o fechamento: se faltar ou for inválido, a execução da reforma
  continua valendo (o painel cai para a análise `.md`). `fechar_analise.py`
  valida o formato e avisa no stderr; não descarta a execução por isso.
- A análise `.md` da reforma continua como hoje (seções Ação requerida etc.) e
  continua obrigatória.

## Triagem

- Notícias da lacuna também recebem veredito em `triagem_pendente.json`
  (`relevante` = entrou no resumo; `contexto`; `ruido`). Para não pesar no
  turno, **notícia sem veredito é fechada como `ruido`** automaticamente por
  `fechar_analise.py` (motivo "não selecionada para o resumo"). Publicação
  oficial continua exigindo leitura de verdade.

## Painel (ordem de cima para baixo)

1. Cabeçalho: "Resumo do dia", data/turno da edição, contagem ("42 lidas, 6
   importam"), seletor de edição (‹ select › e data), alternar tema.
2. **Em 30 segundos**: os bullets de `em_30_segundos` (cartão de destaque).
3. Filtro por tema (chips com contagem): Tudo · Bolso do empreendedor · Bolso
   das pessoas · Reforma.
4. Lista de notícias: etiqueta do tema, fonte e hora, título, `linha`. Clique
   abre o detalhe: `trecho` (citação), "Por que importa", "Ideia de post" e
   "Abrir a matéria" (link). Teclado acessível (botão/`aria-expanded`).
5. Recolhidos: "Análise completa da reforma" (o `.md` da edição), "Prazos da
   reforma" (tiles de `prazos_destaque`), "Fontes consultadas".
6. "Todas as notícias e publicações": a busca do histórico atual, com filtro de
   tipo (notícias / publicações oficiais) além de fonte, período, triagem e texto.
7. Edição sem resumo (antigas ou falha): mostra o título/manchete da análise
   `.md` no lugar e o corpo da análise aberto.

Visual: mantém a marca (marinho/dourado, Lora nos títulos, Inter no corpo, tema
claro/escuro), mobile primeiro (a Carolina lê no celular), sem rolagem lateral.

## Decisões do construtor (calls do Claude)

- Feeds iniciais (validar ao vivo; descartar o que não responder): g1 Economia,
  Folha Mercado, Estadão Economia, InfoMoney, Valor, CNN Brasil Economia/Business,
  Agência Brasil Economia, Exame, UOL Economia, Poder360 Economia, Agência Gov,
  Agência Senado, Agência Câmara (economia). Lista em `scripts/noticias.py`.
- Coletor roda no início de `rodar_varredura.sh` (antes da varredura web) e
  publica junto; falha de um feed não derruba os outros nem a varredura.
- Push (`notificar.py`): quando houver resumo, a mensagem usa a `manchete` e os
  2 primeiros bullets.
