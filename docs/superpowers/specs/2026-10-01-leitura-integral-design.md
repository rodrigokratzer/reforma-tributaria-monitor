# Leitura integral das publicações — design

**Data:** 01/10/2026
**Objetivo:** toda notícia e publicação coletada nas fontes chega à análise com o
texto integral oficial, de modo que o Claude marque `[VERIFICADO LITERAL]` e não
`[PESQUISA]`. Quando a leitura não for possível, isso fica registrado e visível,
nunca silencioso.

## Diagnóstico (01/10/2026, `dados/historico.json`, 385 itens)

| Fonte | Situação | Causa |
|---|---|---|
| DOU (INLABS) | texto em 100% desde 28/08 | Parte A. Os 52 itens de 17 a 24/08 (baldes "revisar"/"forte") ficaram sem texto |
| CGIBS – Notícias | texto desde 07/09 | Parte B. 14 itens anteriores sem texto |
| CGIBS – Resoluções, Atos Conjuntos, Atos Técnicos, Portarias, Regulamentos, Relatórios | 0 de 44 | São PDFs, e o repo não lê PDF |
| RFB – Notícias 2026 / Reforma do Consumo | 0 de 27 | Sem extrator. Além disso, entram links de menu (`gov.br/pt-br/servicos/...`, `www8.receita...`) |
| Portal DF-e SVRS | 0 de 9, **e as notícias reais nunca foram coletadas** | As notícias ficam *inline* na página (`<article class="conteudo-lista__item">`, link `#`). O coletor pega só links soltos e rótulos de categoria |
| Portal NF-e – Informes/NTs | 0 de 6, **e os informes reais nunca foram coletados** | Os informes ficam *inline* (`<div class="divInforme">`). O coletor pega o menu do site. Os atos e as NTs ficam em páginas `listaConteudo.aspx` com links `exibirArquivo.aspx` (PDF), que nunca foram visitadas. O site exige cookie de sessão (sem ele, entra em loop de redirect) |

PDFs testados: 3 de 4 têm camada de texto (pdftotext). O Ato Conjunto RFB/CGIBS
de 29/05 é "Microsoft: Print To PDF", só imagem: rende 156 caracteres (o carimbo da
assinatura). Por isso o OCR é obrigatório.

As notícias do gov.br às vezes têm o conteúdo real num anexo (PDF linkado no
corpo). Ler só o HTML não basta.

## Decisões

1. **Nova raia "Leitura", separada da coleta.** A coleta (`varredura.py`) continua
   rápida e com orçamento de 600 s, e só lista. Um script novo, `scripts/ler_textos.py`,
   roda logo depois, no notebook, e lê o texto integral de cada item do histórico
   que ainda não tem texto: HTML por domínio, PDF por `pdftotext`, OCR por
   `tesseract` nas páginas sem texto e anexos linkados no corpo. Ele tem orçamento
   próprio e generoso (45 min por ciclo, sem limite no backfill manual). OCR é
   lento e isso é aceito.
   O GitHub Actions (plano B) não roda a leitura: o que ele coletar é lido no
   próximo ciclo local.
2. **O texto integral fica fora do `historico.json`**, em `dados/textos/<chave>.txt`,
   um arquivo por item, sem corte de tamanho. O Regulamento do IBS tem cerca de 965 mil
   caracteres, e o corte atual de 20 mil perderia 98% dele. Um arquivo por chave
   não tem condição de corrida: dois escritores nunca escrevem a mesma chave
   (mesmo princípio da gotcha "nunca mesclar a saída de dois coletores").
3. **Metadados da leitura em arquivo próprio**, `dados/leituras.json`
   (`{chave: {status, origem, chars, paginas_ocr, anexos, tentativas, erro, lido_em}}`),
   escrito **só** pelo `ler_textos.py`. Status: `lido`, `falhou` (tenta de novo no
   próximo ciclo) e `desistiu` (depois de `MAX_TENTATIVAS = 4`, ou seja, 2 dias).
   Origem: `coleta` (o coletor já trouxe), `html`, `pdf`, `pdf+ocr`, `inlabs`.
3a. **Coletores que já têm o texto em mãos** (DOU/INLABS, informes do NF-e,
   notícias do SVRS) mandam `texto_integral` no item. `grava_resultado()` grava
   esse campo em `dados/textos/<chave>.txt` e o retira do item, então ele nunca
   entra no `historico.json`.
4. **A análise espera a leitura.** `lacuna_analise.py` adia por até 2 dias os itens
   ainda não lidos com status `falhou` (ou sem nenhuma tentativa), para que a
   análise não os veja sem texto só porque o OCR ainda não terminou. Depois de
   `desistiu`, ou de 3 dias sem nenhuma tentativa (rede de segurança se a raia de
   leitura quebrar), o item é liberado sem texto, com o motivo. A lacuna injeta
   `texto` (até 60 mil caracteres), `texto_chars`, `texto_truncado`,
   `texto_arquivo` e `texto_origem`, e o brief manda ler o arquivo quando o texto
   vier truncado.
5. **Fontes corrigidas na coleta:**
   - RFB: só entra link cujo caminho contém `/noticias/` e não é a própria listagem.
   - SVRS: um parser das `<article>` da listagem. Cada notícia vira um item com
     `url = <listagem>#<id>`, data e `texto_integral`. Só as 30 mais recentes.
   - NF-e: um parser das `divInforme` (cada informe é um item, `url = <página>#<a name>`)
     e quatro fontes novas `listaConteudo.aspx` (Atos RFB/CGIBS, Atos Técnicos
     RFB/CGIBS, Notas Técnicas, Informes Técnicos), cujos links `exibirArquivo.aspx`
     são lidos como PDF pela raia de leitura. Tudo via HTTP com cookie de sessão.
   - CGIBS: deixa de extrair texto na coleta. `CGIBSPortal` e o hook
     `Portal.extrai_texto` saem, e o extrator `artigo__texto` vai para
     `scripts/leitura/paginas.py`.
6. **Primeira coleta das fontes novas não pode inundar a análise.** As fontes NF-e
   e SVRS listam anos de histórico. Um script de semeadura marca como analisados
   os itens dessas fontes com data anterior a 30 dias. Eles continuam sendo lidos e
   ficam no histórico, mas não vão para a análise.
7. **Sem dependência pip nova.** PDF e OCR usam binários do sistema no lenovo-claude
   (`poppler-utils`, que já está instalado, e `tesseract-ocr` + `tesseract-ocr-por`,
   a instalar). Os testes que dependem dos binários usam `skipUnless`.
8. **Backfill:** a primeira execução manual, `ler_textos.py --sem-limite`, lê o acervo
   web inteiro. `scripts/reler_dou.py` busca no INLABS o texto dos 52 itens antigos
   do DOU, se o INLABS ainda tiver aquelas edições. `scripts/cobertura_textos.py`
   mostra a cobertura por fonte, antes e depois.
9. **Prazo do ciclo:** o `TimeoutStartSec` do `reforma-ciclo.service` sobe de 2 h
   para 4 h (DOU até 60 min no pior caso, mais coleta, mais leitura de 45 min, mais
   análise).

## Fora de escopo

- Reanalisar itens antigos que já foram analisados com `[PESQUISA]`. Depois do
  backfill, os textos ficam disponíveis, e a decisão de reanalisar é do usuário.
- Páginas atrás de reCAPTCHA (`consultaRecaptcha.aspx`): não são publicações, e as
  correções do item 5 as tiram da coleta.
- Badge de "texto lido" no painel.
