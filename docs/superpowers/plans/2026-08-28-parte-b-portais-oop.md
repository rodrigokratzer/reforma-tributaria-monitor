# Parte B — Portais web orientados a objetos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reestruturar a varredura dos portais web para que cada fonte seja um objeto `Portal` com pontos de extensão próprios (`filtro_relevancia`, `extrai_texto`), e implementar a captura de texto completo das notícias do CGIBS — sem alterar o comportamento observável das outras fontes.

**Architecture:** Novo pacote `scripts/portais/` com uma classe base `Portal` que absorve, como métodos, a mecânica de coleta hoje espalhada em funções livres de `scripts/varredura.py` (browser + fallback HTTP + filtro por regex global). `CGIBSPortal(Portal)` é a única subclasse desta rodada: sobrescreve `extrai_texto()` para ler o corpo `<div class="artigo__texto">` das páginas de notícia do CGIBS via HTTP puro (as páginas de artigo vêm renderizadas no HTML, ao contrário das páginas de listagem). `scripts/varredura.py` fica só com orquestração (`main`), gravação (`grava_resultado`) e o DOU (`coleta_dou`), importando a lista `PORTAIS` de `scripts/portais/registro.py`.

**Tech Stack:** Python 3 stdlib apenas (`html.parser.HTMLParser`, `urllib`, `unittest`, `unittest.mock`). Playwright 1.56.0 (já no `requirements.txt`) para a coleta de links. Nenhuma dependência nova.

**Spec:** `docs/superpowers/specs/2026-08-28-parte-b-portais-oop-design.md`

## Global Constraints

- **Nenhuma dependência pip nova.** `requirements.txt` fica `playwright==1.56.0` + `markdown==3.7`. Sem BeautifulSoup, sem lib de PDF.
- **Todo texto de código, comentário, docstring e log em português** (segue o padrão do repo; sem acentuação obrigatória nos comentários, como no código existente).
- **Falhas nunca são silenciosas para o operador, mas nunca derrubam a coleta.** Uma fonte com problema não pode afetar as outras 11 — garantia que já existe hoje e deve ser preservada. `extrai_texto()` que falha resulta em `texto` ausente no item + log em `stderr`, nunca exceção propagada.
- **Comportamento observável das fontes não-CGIBS não muda.** Mesmos itens no `historico.json`, mesma ordem de varredura (a ordem importa: o orçamento de tempo faz as últimas fontes serem puladas sob pressão).
- **Schema dos JSON não muda**, exceto a adição opcional da chave `texto` nos itens do CGIBS (mesmo formato que a Parte A já trouxe para os itens do DOU — `scripts/analise_brief.md` já sabe lê-la).
- **Scripts rodam como `python scripts/<nome>.py`** (não `-m`), então `scripts/` fica em `sys.path[0]` e `import portais.base` resolve. Testes fazem `sys.path.insert(0, .../scripts)` antes de importar.
- **Não há passo de teste em CI.** A suíte roda manualmente: `python3 -m unittest discover tests -v`. A validação end-to-end é um disparo manual do workflow `Varredura Reforma Tributária` pelo usuário, como na Parte A.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `scripts/portais/__init__.py` | Marcador de pacote (só docstring). |
| `scripts/portais/base.py` | Constantes e utilitários genéricos de coleta (movidos de `varredura.py`) + classe `Portal` (mecânica de coleta como método; `filtro_relevancia` e `extrai_texto` como pontos de extensão com default = comportamento atual). |
| `scripts/portais/cgibs.py` | `CGIBSPortal(Portal)` + o parser stdlib `_ExtratorArtigo` e o helper puro `_extrai_do_html(html)`. |
| `scripts/portais/registro.py` | Lista `PORTAIS` — as 12 fontes como instâncias, na ordem atual de `FONTES`. |
| `scripts/varredura.py` | Fica só com `RAIZ`/`DADOS`, `ORCAMENTO_S`, `coleta_dou`, `grava_resultado`, `main`. Importa `PORTAIS` e `chave`/`UA` de `portais`. |
| `tests/test_portais_base.py` | Comportamento default de `Portal.filtro_relevancia`, `Portal._filtra`, `Portal.extrai_texto`, e `Portal.coletar` com rede mockada. |
| `tests/test_portal_cgibs.py` | `_extrai_do_html` (parsing) e `CGIBSPortal.extrai_texto` (roteamento PDF/HTML, orçamento) com `via_http` mockado. |

**Sequência e por que:** Task 1 cria o pacote e a classe base **copiando** a mecânica de `varredura.py` (que segue intacto e funcional). Tasks 2–3 constroem `CGIBSPortal` e o registro em cima da base. Task 4 é o ponto de consolidação: religa `varredura.py` para importar de `portais` e **remove as cópias** — é aqui que a duplicação temporária introduzida na Task 1 desaparece, e é um checkpoint de revisão por si só ("a religação preservou o comportamento?"). Task 5 alinha a documentação.

> **Duplicação temporária (Task 1 → Task 4), intencional:** entre a Task 1 e a Task 4, `via_browser`/`via_http`/`filtra`/`monta_item`/etc. existem em dois lugares (`varredura.py` e `portais/base.py`). Isso é deliberado: mantém cada task com fronteira de revisão limpa e `varredura.py` sempre executável. A Task 4 elimina a cópia de `varredura.py`.

---

## Task 1: Pacote `portais` + classe base `Portal`

**Files:**
- Create: `scripts/portais/__init__.py`
- Create: `scripts/portais/base.py`
- Create: `tests/test_portais_base.py`
- Não toca `scripts/varredura.py` nesta task.

**Interfaces:**
- Consumes: nada (primeira task).
- Produces:
  - `class Portal` com:
    - `__init__(self, nome: str, url: str, precisa_js: bool | None = None)` — `precisa_js` default de classe é `True`; passar `False` sobrescreve.
    - atributos de instância `self.nome`, `self.url`, `self.precisa_js`
    - `filtro_relevancia(self, titulo: str, url: str) -> bool` — default: `RELEVANTE` contra `titulo` ou `caminho_normalizado(url)`
    - `extrai_texto(self, ctx, item: dict, limite: float | None = None) -> str | None` — default: `None`
    - `_filtra(self, pares: list[tuple[str, str]]) -> list[dict]` — loop de dedup/comprimento + `monta_item`
    - `coletar(self, ctx, limite: float | None = None) -> dict` — dict com chaves `fonte, url, metodo, http_status, erro, erro_browser, total, itens`
  - Funções livres em `portais.base`, reexportáveis: `extrai_data`, `data_do_arquivo`, `chave`, `monta_item`, `caminho_normalizado`, `via_http`, `via_browser`, `class ColetorLinks`
  - Constantes em `portais.base`: `UA`, `GOTO_MS_1`, `GOTO_MS_2`, `HTTP_TIMEOUT_S`, `RELEVANTE`, `MESES`, `RE_NUM`, `RE_EXT`, `RE_PASTA`, `TOLERANCIA_MESES`

- [ ] **Step 1: Criar o marcador de pacote**

Create `scripts/portais/__init__.py`:

```python
"""Pacote das fontes web da varredura da reforma tributaria.

Cada fonte e' uma instancia de Portal (ou de uma subclasse, quando precisa
de regra propria). A lista completa vive em portais.registro.PORTAIS.
"""
```

- [ ] **Step 2: Criar `scripts/portais/base.py` — utilitários movidos + classe `Portal`**

Create `scripts/portais/base.py`. As funções/constantes abaixo são **cópia verbatim** de `scripts/varredura.py` (linhas indicadas), seguidas da classe `Portal` nova.

Copie de `scripts/varredura.py`, sem alterar uma linha:
- `UA` (linhas 30-31)
- `GOTO_MS_1, GOTO_MS_2` e `HTTP_TIMEOUT_S` (linhas 53-54) — **não** copie `ORCAMENTO_S` (fica em `varredura.py`)
- `RELEVANTE` (linhas 56-62)
- `MESES`, `RE_NUM`, `RE_EXT`, `RE_PASTA` (linhas 64-68)
- `extrai_data` (linhas 73-89)
- `data_do_arquivo` (linhas 92-94)
- `chave` (linhas 97-99)
- `TOLERANCIA_MESES` (linha 102)
- `monta_item` (linhas 105-129)
- `caminho_normalizado` (linhas 132-142)
- `class ColetorLinks` (linhas 161-187)
- `via_http` (linhas 190-207)
- `via_browser` (linhas 212-231)

Imports no topo de `base.py` (só o que essas funções + a classe usam):

```python
#!/usr/bin/env python3
"""Mecanica de coleta generica + classe base Portal.

As funcoes livres (via_http, via_browser, monta_item, ...) eram funcoes de
scripts/varredura.py ate' a Parte B; agora vivem aqui para que os objetos
Portal as usem. O comportamento e' identico ao da varredura v2.
"""
import re, ssl, sys, time, datetime, hashlib
import urllib.parse
import urllib.request, urllib.error
from html.parser import HTMLParser
```

**NÃO** copie `filtra` (linhas 145-156) nem `coleta` (linhas 236-268) — viram métodos de `Portal`, definidos a seguir.

Adicione, ao final de `base.py`, a classe `Portal`:

```python
class Portal:
    """Uma fonte web da varredura.

    A classe base reproduz exatamente o comportamento generico que valia
    para as 12 fontes ate' a Parte B: 2 tentativas via navegador, fallback
    HTTP puro, filtro por um regex global unico. Subclasses sobrescrevem
    filtro_relevancia() e/ou extrai_texto() quando uma fonte precisa de
    regra propria; adicionar uma fonte sem regra especial e' so' uma linha
    Portal(...) em portais.registro.
    """

    precisa_js = True

    def __init__(self, nome, url, precisa_js=None):
        self.nome = nome
        self.url = url
        if precisa_js is not None:
            self.precisa_js = precisa_js

    # -- pontos de extensao ----------------------------------------------

    def filtro_relevancia(self, titulo, url):
        """True se o item interessa.

        Default: o regex global RELEVANTE contra o titulo OU o caminho da
        URL (nunca o dominio — ver caminho_normalizado; casar contra o
        dominio faria todo link de cgibs.gov.br passar).
        """
        return bool(RELEVANTE.search(titulo)
                    or RELEVANTE.search(caminho_normalizado(url)))

    def extrai_texto(self, ctx, item, limite=None):
        """Corpo integral da publicacao do item, ou None.

        Default: None — ate' a Parte B nenhuma fonte web capturava texto
        completo. Chamado so' para itens que ja' passaram no filtro de
        relevancia, nunca para o volume bruto de links de uma pagina.
        `limite` e' o instante (time.monotonic) em que o orcamento da
        varredura acaba; a implementacao deve desistir se estiver perto.
        """
        return None

    # -- mecanica de coleta (identica a coleta() da varredura v2) --------

    def _filtra(self, pares):
        """pares = [(texto, href)] -> itens relevantes, sem repetir url."""
        itens, vistos = [], set()
        for t, h in pares:
            t = re.sub(r"\s+", " ", (t or "")).strip()
            if not t or len(t) < 12 or len(t) > 350 or not h or h in vistos:
                continue
            if not self.filtro_relevancia(t, h):
                continue
            vistos.add(h)
            itens.append(monta_item(t, h))
        return itens

    def coletar(self, ctx, limite=None):
        reg = {"fonte": self.nome, "url": self.url, "metodo": None,
               "http_status": None, "erro": None, "erro_browser": None,
               "total": 0, "itens": []}

        pares = None
        for tentativa, tmo in ((1, GOTO_MS_1), (2, GOTO_MS_2)):
            pares, err = via_browser(ctx, self.url, self.precisa_js, tmo)
            if pares is not None:
                reg["metodo"] = "browser"
                break
            reg["erro_browser"] = err
            if tentativa == 1:
                time.sleep(3)

        if pares is None:
            html, status, err = via_http(self.url)
            reg["http_status"] = status
            if not html:
                reg["erro"] = f"browser: {reg['erro_browser']} | http: {err}"
                return reg
            p = ColetorLinks(self.url)
            try:
                p.feed(html)
            except Exception:
                pass
            reg["metodo"] = "http"
            pares = p.pares

        reg["itens"] = self._filtra(pares)
        reg["total"] = len(reg["itens"])
        if reg["metodo"] == "http" and reg["total"] == 0 and self.precisa_js:
            reg["erro"] = ("browser falhou e o HTTP puro nao traz os itens "
                           "(pagina montada por script)")

        for it in reg["itens"]:
            try:
                txt = self.extrai_texto(ctx, it, limite)
            except Exception as e:
                txt = None
                print(f"      extrai_texto falhou em {it.get('url')}: "
                      f"{type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            if txt:
                it["texto"] = txt

        return reg
```

- [ ] **Step 3: Escrever os testes que devem falhar**

Create `tests/test_portais_base.py`:

```python
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from portais.base import Portal


class TestFiltroRelevancia(unittest.TestCase):
    def setUp(self):
        self.p = Portal("teste", "https://exemplo.gov.br/x")

    def test_titulo_com_termo_da_reforma_passa(self):
        self.assertTrue(self.p.filtro_relevancia(
            "Portaria CGIBS no 8 sobre o IBS", "https://x/y"))

    def test_dominio_cgibs_sozinho_nao_passa(self):
        # a armadilha classica: o dominio contem "cgibs" mas o titulo e o
        # caminho nao tem termo relevante
        self.assertFalse(self.p.filtro_relevancia(
            "Pagina inicial do portal", "https://www.cgibs.gov.br/inicial"))

    def test_termo_no_caminho_da_url_passa(self):
        self.assertTrue(self.p.filtro_relevancia(
            "Documento sem titulo util", "https://x/resolucoes/nova"))

    def test_texto_irrelevante_nao_passa(self):
        self.assertFalse(self.p.filtro_relevancia(
            "Aviso de manutencao do site nesta sexta", "https://x/avisos/123"))


class TestFiltra(unittest.TestCase):
    def setUp(self):
        self.p = Portal("teste", "https://exemplo.gov.br/x")

    def test_dedup_por_href(self):
        pares = [("Resolucao CGIBS numero 1", "https://x/r/1"),
                 ("Resolucao CGIBS numero 1 (copia)", "https://x/r/1")]
        self.assertEqual(len(self.p._filtra(pares)), 1)

    def test_titulo_curto_demais_e_ignorado(self):
        self.assertEqual(self.p._filtra([("IBS", "https://x/r/2")]), [])

    def test_item_relevante_vira_dict_com_titulo_e_url(self):
        itens = self.p._filtra([("Nova resolucao sobre o IBS", "https://x/r/3")])
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["url"], "https://x/r/3")
        self.assertEqual(itens[0]["titulo"], "Nova resolucao sobre o IBS")


class TestExtraiTextoDefault(unittest.TestCase):
    def test_default_e_none(self):
        p = Portal("teste", "https://x/y")
        self.assertIsNone(p.extrai_texto(None, {"url": "https://x/artigo"}))


class TestColetar(unittest.TestCase):
    """coletar() com rede mockada: confirma que o fluxo browser/http e o
    filtro continuam produzindo os mesmos itens da varredura v2."""

    def test_sucesso_via_browser_nao_toca_no_http(self):
        p = Portal("teste", "https://x/lista", precisa_js=True)
        pares = [("Resolucao CGIBS sobre o IBS", "https://x/r/1"),
                 ("Link irrelevante qualquer aqui", "https://x/sobre")]
        with patch("portais.base.via_browser", return_value=(pares, None)) as vb, \
             patch("portais.base.via_http") as vh:
            reg = p.coletar(None)
        vh.assert_not_called()
        self.assertEqual(reg["metodo"], "browser")
        self.assertEqual(reg["total"], 1)
        self.assertEqual(reg["itens"][0]["url"], "https://x/r/1")

    def test_fallback_http_quando_browser_falha(self):
        p = Portal("teste", "https://x/lista", precisa_js=False)
        html = ('<a href="https://x/r/9">Nova portaria sobre o IBS</a>'
                '<a href="https://x/home">Inicio</a>')
        with patch("portais.base.via_browser", return_value=(None, "Timeout")), \
             patch("portais.base.via_http", return_value=(html, 200, None)):
            reg = p.coletar(None)
        self.assertEqual(reg["metodo"], "http")
        self.assertEqual(reg["total"], 1)

    def test_browser_e_http_falham_registra_erro(self):
        p = Portal("teste", "https://x/lista")
        with patch("portais.base.via_browser", return_value=(None, "Timeout")), \
             patch("portais.base.via_http", return_value=(None, None, "DNS")):
            reg = p.coletar(None)
        self.assertIsNone(reg["metodo"])
        self.assertIn("browser:", reg["erro"])

    def test_extrai_texto_que_lanca_nao_derruba_coleta(self):
        class Explode(Portal):
            def extrai_texto(self, ctx, item, limite=None):
                raise RuntimeError("erro proposital")

        p = Explode("teste", "https://x/lista")
        pares = [("Resolucao CGIBS sobre o IBS", "https://x/r/1")]
        with patch("portais.base.via_browser", return_value=(pares, None)):
            reg = p.coletar(None)
        self.assertEqual(reg["total"], 1)
        self.assertNotIn("texto", reg["itens"][0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Rodar os testes e confirmar que falham**

Run: `python3 -m unittest tests.test_portais_base -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'portais'` (o Step 2 ainda não foi confirmado se este for o primeiro run) ou, se o pacote já existe mas está vazio, `ImportError` de `Portal`.

> Se você acabou de criar `base.py` no Step 2, os testes já devem **passar** aqui — nesse caso pule para o Step 5 e confirme que passam. A ordem "teste falha primeiro" vale quando o arquivo de teste é escrito antes da implementação; aqui a implementação é majoritariamente cópia, então o valor está em ter os testes verdes contra o comportamento copiado.

- [ ] **Step 5: Rodar os testes e confirmar que passam**

Run: `python3 -m unittest tests.test_portais_base -v`
Expected: PASS — todos os testes verdes.

Run também a suíte existente, que **não pode** ter regredido (nada foi tocado nela, mas confirme):
Run: `python3 -m unittest discover tests -v`
Expected: PASS — os 11 testes de `test_lacuna_analise` + os novos.

- [ ] **Step 6: Smoke test de import isolado**

Run:
```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); from portais.base import Portal, via_http, via_browser, monta_item, chave, RELEVANTE; print('ok', Portal('a','b').precisa_js)"
```
Expected: `ok True`

Run (varredura.py continua intacto e importável):
```bash
python3 -m py_compile scripts/varredura.py scripts/portais/__init__.py scripts/portais/base.py
```
Expected: sem saída, exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/portais/__init__.py scripts/portais/base.py tests/test_portais_base.py
git commit -m "feat: pacote portais com classe base Portal (Parte B)

Extrai a mecanica de coleta de scripts/varredura.py para portais/base.py
como metodos de Portal, com filtro_relevancia e extrai_texto como pontos
de extensao (default = comportamento atual). varredura.py ainda tem as
copias; a Task 4 consolida.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: `CGIBSPortal` com captura de texto das notícias

**Files:**
- Create: `scripts/portais/cgibs.py`
- Create: `tests/test_portal_cgibs.py`

**Interfaces:**
- Consumes de `portais.base`: `class Portal`, `via_http(url, timeout=HTTP_TIMEOUT_S) -> (html|None, status|None, erro|None)`, `HTTP_TIMEOUT_S`
- Produces:
  - `class CGIBSPortal(Portal)` — sobrescreve só `extrai_texto(self, ctx, item, limite=None) -> str | None`
  - `_extrai_do_html(html: str | None) -> str | None` — função pura, sem rede, testável isoladamente
  - `class _ExtratorArtigo(HTMLParser)` — captura o texto de `<div class="artigo__texto">`
  - Constantes: `MARGEM_ORCAMENTO_S = 45`, `TETO_TEXTO = 20000`

**Contexto verificado (28/08/2026, via `curl` nas páginas reais):**
- As páginas de **notícia** do CGIBS (`https://www.cgibs.gov.br/<slug>`) vêm **renderizadas no HTML** — `via_http` puro basta, não precisa de navegador. Estrutura estável em 3 artigos testados: `<article class="artigo ...">` contém `<h1 class="artigo__titulo">`, `<p class="artigo__subtitulo">`, `<time datetime="...">` e `<div class="artigo__texto">` com o corpo em `<p>`/`<ul>`/`<ol>`.
- As páginas de **listagem** (`/noticias`, `/resolucoes`, ...) são montadas por JS (Plone) — por isso `precisa_js=True`; isso não muda, a coleta de links continua pelo navegador.
- Muitos itens do CGIBS são **links diretos de PDF** (`https://www.cgibs.gov.br/upload/arquivos/AAAAMM/...pdf`) — atos, portarias, relatórios. O repo não tem lib de PDF; esses itens ficam com `texto` ausente (como hoje).

- [ ] **Step 1: Escrever os testes que devem falhar**

Create `tests/test_portal_cgibs.py`:

```python
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from portais.cgibs import CGIBSPortal, _extrai_do_html


ARTIGO_HTML = """
<html><body>
<article class="artigo artigo__noticia--semcolunalateral">
  <ol class="breadcrumb"><li><a href="/inicial">Inicial</a></li></ol>
  <header class="artigo__cabecalho">
    <h1 class="artigo__titulo">CGIBS e RFB esclarecem prazos da DeRE</h1>
    <p class="artigo__subtitulo">Veja detalhes sobre o Marco Inicial</p>
    <p class="artigo__pubdate"><time datetime="2026-08-26T15:41:00-0300">26/08/2026</time></p>
  </header>
  <div class="artigo__texto">
    <div>
      <p>O Comite Gestor do IBS e a Receita Federal esclarecem os prazos.</p>
      <p><strong>1. Marco Inicial</strong></p>
      <ul><li>D-1001 Informacoes do Contribuinte</li>
      <li>D-1011 Plano Geral de Contas</li></ul>
      <script>var x = 1;</script>
    </div>
  </div>
  <div class="artigo__rodape">Voltar Imprimir</div>
</article>
</body></html>
"""

SHELL_SEM_ARTIGO = "<html><body><div id='app'></div></body></html>"


class TestExtraiDoHtml(unittest.TestCase):
    def test_captura_o_corpo_do_artigo(self):
        txt = _extrai_do_html(ARTIGO_HTML)
        self.assertIn("O Comite Gestor do IBS e a Receita Federal", txt)
        self.assertIn("D-1001 Informacoes do Contribuinte", txt)

    def test_nao_captura_fora_do_artigo_texto(self):
        txt = _extrai_do_html(ARTIGO_HTML)
        self.assertNotIn("Voltar Imprimir", txt)
        self.assertNotIn("Veja detalhes sobre o Marco Inicial", txt)  # subtitulo
        self.assertNotIn("var x = 1", txt)  # script

    def test_html_sem_artigo_texto_devolve_none(self):
        self.assertIsNone(_extrai_do_html(SHELL_SEM_ARTIGO))

    def test_html_vazio_ou_none_devolve_none(self):
        self.assertIsNone(_extrai_do_html(""))
        self.assertIsNone(_extrai_do_html(None))

    def test_html_malformado_nao_lanca(self):
        self.assertIsNone(_extrai_do_html("<article><div class='artigo__texto'><p>oi"))


class TestExtraiTexto(unittest.TestCase):
    def setUp(self):
        self.p = CGIBSPortal("CGIBS - Noticias", "https://www.cgibs.gov.br/noticias")

    def test_pdf_nao_e_baixado(self):
        item = {"url": "https://www.cgibs.gov.br/upload/arquivos/202608/17-portaria.pdf"}
        with patch("portais.cgibs.via_http") as vh:
            self.assertIsNone(self.p.extrai_texto(None, item))
        vh.assert_not_called()

    def test_noticia_html_e_lida(self):
        item = {"url": "https://www.cgibs.gov.br/cgibs-e-rfb-esclarecem-prazos"}
        with patch("portais.cgibs.via_http",
                   return_value=(ARTIGO_HTML, 200, None)):
            txt = self.p.extrai_texto(None, item)
        self.assertIn("O Comite Gestor do IBS", txt)

    def test_orcamento_perto_do_fim_pula_sem_baixar(self):
        item = {"url": "https://www.cgibs.gov.br/alguma-noticia"}
        limite = time.monotonic() + 5  # faltam 5s, MARGEM e' 45s
        with patch("portais.cgibs.via_http") as vh:
            self.assertIsNone(self.p.extrai_texto(None, item, limite))
        vh.assert_not_called()

    def test_erro_http_devolve_none_sem_lancar(self):
        item = {"url": "https://www.cgibs.gov.br/alguma-noticia"}
        with patch("portais.cgibs.via_http", return_value=(None, 503, "HTTP 503")):
            self.assertIsNone(self.p.extrai_texto(None, item))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `python3 -m unittest tests.test_portal_cgibs -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'portais.cgibs'`

- [ ] **Step 3: Implementar `scripts/portais/cgibs.py`**

Create `scripts/portais/cgibs.py`:

```python
#!/usr/bin/env python3
"""Portal do CGIBS (cgibs.gov.br).

Alem do comportamento padrao de Portal, captura o corpo das noticias em
HTML — mesma ideia que a Parte A trouxe para o DOU, para que a analise
diaria leia o texto do repo em vez de depender de busca externa (bloqueada
no sandbox da rotina). As paginas de artigo do CGIBS vem renderizadas no
HTML, entao via_http puro basta. Links de PDF (/upload/arquivos/...) nao
sao lidos: o repo nao tem biblioteca de PDF, e o item fica sem `texto`,
como ja acontecia.
"""
import re, sys, time, urllib.parse
from html.parser import HTMLParser

from portais.base import Portal, via_http, HTTP_TIMEOUT_S

MARGEM_ORCAMENTO_S = 45   # nao inicia uma extracao se falta menos que isto
TETO_TEXTO = 20000        # teto defensivo, igual ao do DOU (dou.artigos)


class _ExtratorArtigo(HTMLParser):
    """Captura o texto dentro de <div class="artigo__texto">.

    Rastreia a profundidade de <div> desde o alvo para saber onde o corpo
    termina; ignora <script>/<style>; trata tags de bloco como quebra de
    linha para o texto nao ficar grudado.
    """
    ALVO = "artigo__texto"
    IGNORA = {"script", "style"}
    QUEBRA = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "div"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._prof = 0
        self._dentro = False
        self._ignora = 0
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if not self._dentro:
            if tag == "div":
                classes = (dict(attrs).get("class") or "").split()
                if self.ALVO in classes:
                    self._dentro = True
                    self._prof = 1
            return
        if tag == "div":
            self._prof += 1
        if tag in self.IGNORA:
            self._ignora += 1
        if tag in self.QUEBRA:
            self._buf.append("\n")

    def handle_startendtag(self, tag, attrs):
        if self._dentro and tag in self.QUEBRA:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if not self._dentro:
            return
        if tag in self.IGNORA and self._ignora:
            self._ignora -= 1
        if tag == "div":
            self._prof -= 1
            if self._prof <= 0:
                self._dentro = False

    def handle_data(self, data):
        if self._dentro and not self._ignora:
            self._buf.append(data)

    def texto(self):
        t = "".join(self._buf)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)*", "\n\n", t)
        return t.strip()


def _extrai_do_html(html):
    """Corpo do artigo, ou None se a pagina nao tiver <div artigo__texto>."""
    if not html:
        return None
    p = _ExtratorArtigo()
    try:
        p.feed(html)
    except Exception:
        return None
    t = p.texto()
    return t[:TETO_TEXTO] if t else None


class CGIBSPortal(Portal):
    """As secoes do site do CGIBS. Uma instancia por URL de listagem."""

    def extrai_texto(self, ctx, item, limite=None):
        url = item.get("url") or ""
        caminho = urllib.parse.urlparse(url).path.lower()
        if caminho.endswith(".pdf") or "/upload/arquivos/" in caminho:
            return None
        if limite is not None and time.monotonic() > limite - MARGEM_ORCAMENTO_S:
            return None
        html, status, err = via_http(url, timeout=HTTP_TIMEOUT_S)
        if not html:
            print(f"      CGIBS extrai_texto: {url} -> http {status} "
                  f"{err or ''}", file=sys.stderr)
            return None
        return _extrai_do_html(html)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `python3 -m unittest tests.test_portal_cgibs -v`
Expected: PASS — todos verdes.

- [ ] **Step 5: Verificação contra uma página real (rede necessária; opcional se offline)**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
from portais.base import via_http
from portais.cgibs import _extrai_do_html
html,_,_ = via_http('https://www.cgibs.gov.br/cgibs-e-rfb-esclarecem-prazos-de-cumprimento-das-obrigacoes-relativas-a-dere-estabelecidos-pelo-ato-conjunto-n-4')
t = _extrai_do_html(html)
print('chars:', len(t or ''))
print((t or '')[:300])
"
```
Expected: algumas milhares de chars, começando com "O Comitê Gestor do Imposto sobre Bens e Serviços (CGIBS)...". Se a rede estiver bloqueada, registre isso no report e siga — os testes com HTML embutido cobrem o parsing.

- [ ] **Step 6: Commit**

```bash
git add scripts/portais/cgibs.py tests/test_portal_cgibs.py
git commit -m "feat: CGIBSPortal le o corpo das noticias do CGIBS (Parte B)

extrai_texto() baixa a pagina do artigo (via_http puro — o CGIBS renderiza
o artigo no HTML) e captura <div class=artigo__texto>. Links de PDF ficam
sem texto (sem lib de PDF no repo). Respeita o orcamento de tempo da
varredura.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Registro `PORTAIS`

**Files:**
- Create: `scripts/portais/registro.py`
- Modify: `tests/test_portais_base.py` (adiciona uma classe de teste do registro)

**Interfaces:**
- Consumes: `portais.base.Portal`, `portais.cgibs.CGIBSPortal`
- Produces: `PORTAIS: list[Portal]` — 12 instâncias, **na mesma ordem** de `FONTES` em `scripts/varredura.py` (a ordem é significativa: o orçamento de tempo em `main()` pula as últimas fontes sob pressão).

- [ ] **Step 1: Escrever o teste que deve falhar**

Adicione ao final de `tests/test_portais_base.py` (antes do `if __name__`):

```python
class TestRegistro(unittest.TestCase):
    def test_doze_portais_na_ordem_das_fontes(self):
        from portais.registro import PORTAIS
        nomes = [p.nome for p in PORTAIS]
        self.assertEqual(nomes, [
            "CGIBS - Noticias",
            "CGIBS - Resolucoes",
            "CGIBS - Atos Conjuntos",
            "CGIBS - Atos Tecnicos Conj.",
            "CGIBS - Portarias",
            "RFB - Noticias 2026",
            "RFB - Reforma do Consumo",
            "Portal DF-e SVRS - Noticias",
            "Portal NF-e - Informes/NTs",
            "CGIBS - Regulamentos",
            "CGIBS - Leis",
            "CGIBS - Relatorios",
        ])

    def test_cgibs_usa_a_subclasse_e_precisa_js(self):
        from portais.registro import PORTAIS
        from portais.cgibs import CGIBSPortal
        cgibs = [p for p in PORTAIS if p.nome.startswith("CGIBS")]
        self.assertEqual(len(cgibs), 8)
        self.assertTrue(all(isinstance(p, CGIBSPortal) for p in cgibs))
        self.assertTrue(all(p.precisa_js for p in cgibs))

    def test_fontes_sem_js_sao_marcadas(self):
        from portais.registro import PORTAIS
        sem_js = {p.nome for p in PORTAIS if not p.precisa_js}
        self.assertEqual(sem_js, {
            "RFB - Noticias 2026", "RFB - Reforma do Consumo",
            "Portal DF-e SVRS - Noticias", "Portal NF-e - Informes/NTs",
        })
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python3 -m unittest tests.test_portais_base.TestRegistro -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'portais.registro'`

- [ ] **Step 3: Criar `scripts/portais/registro.py`**

Confira antes as URLs exatas em `scripts/varredura.py` linhas 34-47 e copie-as sem alterar.

```python
#!/usr/bin/env python3
"""As fontes web da varredura, como instancias de Portal.

Ordem = a mesma de FONTES na varredura v2. A ordem importa: o orcamento de
tempo em varredura.main() pula as ultimas fontes quando o tempo acaba.

Adicionar uma fonte sem regra propria: uma linha Portal(nome, url, precisa_js=...).
Adicionar uma fonte com regra propria: uma subclasse pequena em outro
modulo deste pacote (so' o metodo que muda) + uma linha aqui.
"""
from portais.base import Portal
from portais.cgibs import CGIBSPortal

PORTAIS = [
    CGIBSPortal("CGIBS - Noticias",            "https://www.cgibs.gov.br/noticias"),
    CGIBSPortal("CGIBS - Resolucoes",          "https://www.cgibs.gov.br/resolucoes"),
    CGIBSPortal("CGIBS - Atos Conjuntos",      "https://www.cgibs.gov.br/atos-conjuntos"),
    CGIBSPortal("CGIBS - Atos Tecnicos Conj.", "https://www.cgibs.gov.br/atos-tecnicos-conjuntos"),
    CGIBSPortal("CGIBS - Portarias",           "https://www.cgibs.gov.br/portarias"),
    Portal("RFB - Noticias 2026",
           "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026",
           precisa_js=False),
    Portal("RFB - Reforma do Consumo",
           "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/noticias",
           precisa_js=False),
    Portal("Portal DF-e SVRS - Noticias",
           "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias",
           precisa_js=False),
    Portal("Portal NF-e - Informes/NTs",
           "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false",
           precisa_js=False),
    CGIBSPortal("CGIBS - Regulamentos",        "https://www.cgibs.gov.br/regulamentos"),
    CGIBSPortal("CGIBS - Leis",                "https://www.cgibs.gov.br/leis"),
    CGIBSPortal("CGIBS - Relatorios",          "https://www.cgibs.gov.br/relatorios"),
]
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `python3 -m unittest discover tests -v`
Expected: PASS — 11 de `test_lacuna_analise` + `test_portais_base` (com `TestRegistro`) + `test_portal_cgibs`.

- [ ] **Step 5: Commit**

```bash
git add scripts/portais/registro.py tests/test_portais_base.py
git commit -m "feat: portais.registro.PORTAIS com as 12 fontes como objetos

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Religar `varredura.py` e remover a duplicação

**Files:**
- Modify: `scripts/varredura.py` (remove ~200 linhas movidas; adiciona 2 imports; reescreve o loop de `main`)
- Não toca `scripts/dou_diario.py` (continua importando `coleta_dou, grava_resultado` de `varredura` — ambos permanecem).

**Interfaces:**
- Consumes: `portais.base.UA`, `portais.base.chave`, `portais.registro.PORTAIS`
- Produces: `scripts/varredura.py` com API pública inalterada para `dou_diario.py`: `coleta_dou(hoje) -> dict`, `grava_resultado(hoje, resultado, arquivo_dados, arquivo_novidades) -> None`.

- [ ] **Step 1: Reescrever o cabeçalho e os imports de `scripts/varredura.py`**

Substitua as linhas 20-24 (imports atuais):

```python
import json, os, re, sys, time, ssl, datetime, hashlib
import urllib.parse
import urllib.request, urllib.error
from html.parser import HTMLParser
from pathlib import Path
```

por:

```python
import json, os, sys, time, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portais.base import UA, chave
from portais.registro import PORTAIS
```

> `sys.path.insert` aqui espelha o que `dou_diario.py` já faz — garante que `import portais` resolve mesmo se o script for chamado de outro diretório. Rodando como `python scripts/varredura.py`, `sys.path[0]` já é `scripts/`, mas a linha não custa nada e blinda contra chamadas via caminho absoluto.

- [ ] **Step 2: Remover todo o código que foi para `portais/base.py`**

Delete de `scripts/varredura.py` (verifique cada bloco pelo nome antes de apagar):
- `UA` (linhas 30-31) — agora importado
- `FONTES` (linhas 33-47) — substituído por `PORTAIS`
- `GOTO_MS_1, GOTO_MS_2` e `HTTP_TIMEOUT_S` das linhas 53-54 — **mantenha `ORCAMENTO_S` (linha 52)**
- `RELEVANTE` (linhas 56-62)
- `MESES, RE_NUM, RE_EXT, RE_PASTA` (linhas 64-68)
- `extrai_data` (linhas 73-89)
- `data_do_arquivo` (linhas 92-94)
- `chave` (linhas 97-99) — agora importado
- `TOLERANCIA_MESES` (linha 102)
- `monta_item` (linhas 105-129)
- `caminho_normalizado` (linhas 132-142)
- `filtra` (linhas 145-156)
- `class ColetorLinks` (linhas 159-187, incluindo o comentário de seção)
- `via_http` (linhas 190-207)
- `via_browser` (linhas 210-231, incluindo o comentário de seção)
- `coleta` (linhas 234-268, incluindo o comentário de seção `# --- principal`)

**Mantenha intactos:** `RAIZ`, `DADOS` (linhas 26-28), `ORCAMENTO_S` (linha 52), `coleta_dou` (271-302), `grava_resultado` (305-355), a estrutura de `main` (será editada no Step 3), o bloco `if __name__ == "__main__"`.

- [ ] **Step 3: Reescrever o loop de `main()`**

Em `main()`, substitua o bloco `for nome, url, js in FONTES:` (linhas 368-381) por:

```python
        for portal in PORTAIS:
            if time.monotonic() > limite:
                resultado.append({"fonte": portal.nome, "url": portal.url,
                                  "metodo": None, "http_status": None,
                                  "total": 0, "itens": [],
                                  "erro": "nao tentada: orcamento de tempo esgotado"})
                print(f"  {portal.nome:32} PULADA (tempo esgotado)", file=sys.stderr)
                continue
            r = portal.coletar(ctx, limite)
            resultado.append(r)
            print(f"  {portal.nome:32} metodo={r['metodo'] or 'FALHOU':7} "
                  f"itens={r['total']:3} http={r['http_status']} "
                  f"[{int(limite - time.monotonic())}s restantes]", file=sys.stderr)
            if r["erro"]:
                print(f"      {r['erro'][:150]}", file=sys.stderr)
```

O resto de `main()` (o `with sync_playwright()`, o `nav.new_context(... user_agent=UA ...)`, o `grava_resultado(hoje, resultado, f"{hoje}.json", "novidades.json")` final) não muda.

- [ ] **Step 4: Verificar sintaxe e imports de todos os scripts afetados**

Run:
```bash
python3 -m py_compile scripts/varredura.py scripts/dou_diario.py scripts/portais/__init__.py scripts/portais/base.py scripts/portais/cgibs.py scripts/portais/registro.py
```
Expected: sem saída, exit 0.

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
import varredura
from dou_diario import main as dm
assert callable(varredura.coleta_dou) and callable(varredura.grava_resultado)
assert len(varredura.PORTAIS) == 12
print('varredura + dou_diario ok; PORTAIS =', len(varredura.PORTAIS))
"
```
Expected: `varredura + dou_diario ok; PORTAIS = 12`

Run (garante que nenhum nome removido ficou referenciado):
```bash
python3 -c "
import sys, warnings; sys.path.insert(0,'scripts')
warnings.simplefilter('error')
import varredura
for nome in ('filtra','coleta','via_http','via_browser','ColetorLinks','RELEVANTE','monta_item','FONTES'):
    assert not hasattr(varredura, nome), f'{nome} ainda em varredura.py'
print('limpeza ok')
"
```
Expected: `limpeza ok`

- [ ] **Step 5: Rodar a suíte completa**

Run: `python3 -m unittest discover tests -v`
Expected: PASS — 11 de `test_lacuna_analise` + `test_portais_base` + `test_portal_cgibs`, sem regressão.

- [ ] **Step 6: Teste offline de `main()` com Playwright e rede mockados**

Este teste confirma que `main()` monta o `resultado` no formato que `grava_resultado`/`gerar_painel` esperam, sem tocar a rede. Salve como script temporário e rode (não committar):

```bash
python3 - <<'EOF'
import sys, types
sys.path.insert(0, "scripts")

# stub do playwright para nao abrir navegador de verdade
fake = types.ModuleType("playwright"); fakes = types.ModuleType("playwright.sync_api")
class _Ctx:
    def new_page(self): raise RuntimeError("sem navegador no teste")
class _Nav:
    def new_context(self, **k): return _Ctx()
    def close(self): pass
class _P:
    class chromium:
        @staticmethod
        def launch(**k): return _Nav()
class _SP:
    def __enter__(self): return _P()
    def __exit__(self, *a): return False
fakes.sync_playwright = lambda: _SP()
fake.sync_api = fakes
sys.modules["playwright"] = fake; sys.modules["playwright.sync_api"] = fakes

import portais.base as base
base.via_browser = lambda ctx, url, js, tmo=0: (None, "sem navegador (teste)")
base.via_http = lambda url, timeout=15: (
    '<a href="https://x/resolucao-sobre-ibs">Nova resolucao sobre o IBS</a>', 200, None)

import importlib, varredura, os, json, tempfile
d = tempfile.mkdtemp()
varredura.DADOS = __import__("pathlib").Path(d)
os.environ["DATA_REF"] = "2026-08-28"
os.environ.pop("INLABS_EMAIL", None); os.environ.pop("INLABS_SENHA", None)
varredura.main()
saida = json.load(open(f"{d}/2026-08-28.json"))
print("fontes no resultado:", len(saida["fontes"]))
assert len(saida["fontes"]) == 12
for f in saida["fontes"]:
    assert set(("fonte","url","total","itens")) <= set(f), f
print("formato do resultado ok")
EOF
```
Expected: `fontes no resultado: 12` e `formato do resultado ok`.

- [ ] **Step 7: Commit**

```bash
git add scripts/varredura.py
git commit -m "refactor: varredura.py usa portais.PORTAIS; remove a mecanica duplicada

varredura.py fica so' com orquestracao (main), gravacao (grava_resultado)
e o DOU (coleta_dou). A mecanica de coleta agora vive em portais/base.py
(Task 1). Comportamento das 12 fontes inalterado; a ordem de FONTES foi
preservada em PORTAIS porque o orcamento de tempo a torna significativa.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Atualizar `CLAUDE.md` e `README.md`

**Files:**
- Modify: `CLAUDE.md` (seção "Architecture")
- Modify: `README.md` (seção de estrutura/arquitetura)

**Interfaces:** nenhuma (documentação).

- [ ] **Step 1: Atualizar `CLAUDE.md`**

Na seção `## Architecture`, no bullet de **Fatos**, troque a menção a `scripts/varredura.py` para refletir o pacote. O texto atual:

```
- **Fatos** (facts) — `scripts/varredura.py` (12 web sources) and `scripts/dou_diario.py`
  (DOU/INLABS) run on their own GitHub Actions schedules, write JSON, and never
  interpret anything. No AI, no judgment calls.
```

Substitua por:

```
- **Fatos** (facts) — `scripts/varredura.py` (12 web sources, via the
  `scripts/portais/` package) and `scripts/dou_diario.py` (DOU/INLABS) run on
  their own GitHub Actions schedules, write JSON, and never interpret anything.
  No AI, no judgment calls.
```

E adicione, logo após o parágrafo que começa em "5. `scripts/gerar_painel.py` reads..." na subseção **Data flow**, um novo item:

```
### Os scrapers web (`scripts/portais/`)

Cada fonte web é um objeto `Portal` (`scripts/portais/base.py`). A classe base
tem toda a mecânica de coleta (2 tentativas via navegador, fallback HTTP puro,
filtro por um regex global) e dois pontos de extensão: `filtro_relevancia()` e
`extrai_texto()`. `scripts/portais/registro.py` lista as 12 instâncias, na
ordem que importa para o orçamento de tempo. `CGIBSPortal`
(`scripts/portais/cgibs.py`) é a única subclasse: lê o corpo `<div
class="artigo__texto">` das notícias do CGIBS (links de PDF ficam sem texto —
não há lib de PDF). Adicionar um portal sem regra própria é uma linha em
`registro.py`; com regra própria, uma subclasse pequena + a linha.
```

- [ ] **Step 2: Atualizar `README.md`**

Localize no `README.md` a descrição da varredura das fontes web (procure por "varredura.py" ou "12 fontes" / "Doze fontes"). Ajuste o texto para mencionar que os scrapers agora são objetos `Portal` em `scripts/portais/`, e que o CGIBS captura o texto completo das notícias (mesmo ganho que a Parte A trouxe para o DOU). Mantenha o tom e o tamanho da seção existente — é um ajuste de uma a três frases, não uma seção nova. Se houver uma seção de "Decisões de projeto"/"Gotchas", adicione um item curto:

```
- **Cada fonte web é um objeto `Portal` (`scripts/portais/`).** A classe base
  concentra a mecânica de coleta; subclasses só sobrescrevem o filtro de
  relevância ou a extração de texto quando a fonte precisa. Isso saiu de uma
  lista plana de tuplas em `varredura.py` (Parte B, 28/08/2026) para dar a
  cada portal regras próprias e facilitar incluir novos sites.
```

- [ ] **Step 3: Verificar que nada quebrou e commitar**

Run: `python3 -m unittest discover tests -v`
Expected: PASS (documentação não afeta testes, mas confirma o estado da árvore).

```bash
git add CLAUDE.md README.md
git commit -m "docs: pacote scripts/portais/ no CLAUDE.md e README (Parte B)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Rollout e validação end-to-end (após o merge)

O efeito real só aparece quando a varredura roda com o código novo:

1. **Disparo manual** (usuário): Actions → **Varredura Reforma Tributária** → **Run workflow**.
2. **Conferir** `dados/novidades.json` (ou `dados/AAAA-MM-DD.json`): itens de "CGIBS - Noticias" que forem notícias em HTML devem ter a chave `texto` preenchida; itens de PDF (`/upload/arquivos/`) seguem sem `texto`, como antes.
3. **Itens já vistos não ganham `texto` retroativo** — a dedup do `historico.json` não sobrescreve chave existente (mesma situação da Parte A com o DOU). Só notícias do CGIBS vistas pela primeira vez após o merge terão o campo. Se for necessário reprocessar uma notícia específica já conhecida, remover a chave dela do `historico.json` (como foi feito na validação da Parte A).
4. **Próxima análise diária** (rotina agendada, dia útil ~07:15): as notícias novas do CGIBS com `texto` devem ser classificadas com `[VERIFICADO LITERAL]` em vez de `[PESQUISA]`.

---

## Self-Review (feita na escrita do plano)

**1. Cobertura da spec:**
- "Classe base `Portal` em `scripts/portais/base.py`" → Task 1 ✓
- "`coletar()` = a função `coleta()` virando método, sem mudança de comportamento" → Task 1 Step 2 (refactor preserva o fluxo; testes em Task 1 Step 3 + teste offline em Task 4 Step 6) ✓
- "`filtro_relevancia()` default = `filtra()` atual" → Task 1 (`_filtra` + `filtro_relevancia`), testes `TestFiltroRelevancia`/`TestFiltra` ✓
- "`extrai_texto()` default = `None`" → Task 1, teste `TestExtraiTextoDefault` ✓
- "funções utilitárias de data continuam livres em `base.py`" → Task 1 Step 2 (movidas para `base.py`) ✓
- "`scripts/portais/cgibs.py` — `CGIBSPortal(Portal)` sobrescreve `extrai_texto()`" → Task 2 ✓
- "as 8 entradas CGIBS compartilham a classe" → Task 3 (`registro.py`), teste `test_cgibs_usa_a_subclasse_e_precisa_js` ✓
- "CGIBS sem sobrescrever `filtro_relevancia`" → Task 2 (só `extrai_texto` é sobrescrito) ✓
- "`scripts/portais/registro.py` substitui `FONTES`" → Task 3 ✓
- "`varredura.py` importa `PORTAIS`, loop chama `portal.coletar(ctx)`; `grava_resultado`, `coleta_dou`, `main` não mudam de responsabilidade" → Task 4 ✓
- "escopo de `extrai_texto` = só CGIBS nesta rodada" → Tasks 2-3 (os 4 Portal base não sobrescrevem) ✓
- "orçamento de tempo: checar antes de visitar cada página, desistir silencioso" → Task 2 (`MARGEM_ORCAMENTO_S`, `limite` em `coletar`→`extrai_texto`), teste `test_orcamento_perto_do_fim_pula_sem_baixar` ✓
- "`extrai_texto()` nunca propaga exceção para `coletar()`" → Task 1 (`try/except` no loop de `coletar`), teste `test_extrai_texto_que_lanca_nao_derruba_coleta` ✓
- "campo `texto` opcional nos itens do CGIBS, mesmo formato do DOU; brief não muda" → Task 2 + Rollout (nenhuma edição em `analise_brief.md`) ✓
- "`tests/test_portais_base.py` e `tests/test_portal_cgibs.py` novos; `test_lacuna_analise.py` não muda" → Tasks 1-3 ✓
- Decisão assumida "nome do pacote `scripts/portais/`" → adotada; "uma classe única para as 8 URLs do CGIBS" → adotada (Task 3) ✓

**Desvios da spec (documentados):**
- `extrai_texto(self, ctx, item)` da spec vira `extrai_texto(self, ctx, item, limite=None)` e `coletar(self, ctx)` vira `coletar(self, ctx, limite=None)` — o parâmetro `limite` é necessário para cumprir a própria seção "Orçamento de tempo" da spec (checar o tempo restante antes de cada visita).
- A spec sugere que `CGIBSPortal.extrai_texto()` reaproveite "a mesma sessão de browser já aberta". Verificação real (28/08) mostrou que as páginas de artigo do CGIBS vêm renderizadas no HTML — `via_http` puro basta, é mais simples e não gasta aba do navegador. `ctx` fica na assinatura para portais futuros que precisem de JS.
- Task 1 **copia** a mecânica em vez de mover; Task 4 remove a cópia de `varredura.py`. Duplicação temporária e intencional, explicada na seção "File Structure".

**2. Placeholders:** nenhum "TBD"/"TODO"/"add error handling"; todo passo de código tem bloco completo; testes têm corpo real.

**3. Consistência de tipos:** `Portal.coletar(ctx, limite=None)`, `Portal.extrai_texto(ctx, item, limite=None)`, `Portal.filtro_relevancia(titulo, url)`, `Portal._filtra(pares)` usados de forma idêntica nas Tasks 1-4. `_extrai_do_html(html)` e `via_http(url, timeout=...)` idem. `PORTAIS` é `list[Portal]` nas Tasks 3-4.
