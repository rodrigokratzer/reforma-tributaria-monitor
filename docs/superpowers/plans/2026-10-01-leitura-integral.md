# Leitura integral das publicações — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toda notícia e publicação coletada chega à análise com o texto integral oficial (HTML, PDF ou PDF escaneado via OCR), para que o Claude marque `[VERIFICADO LITERAL]`. Quando a leitura falha, isso fica registrado e visível.

**Architecture:** Uma raia nova, `scripts/ler_textos.py`, roda no notebook depois da varredura. Ela percorre `dados/historico.json` e, para cada item sem texto, baixa a URL com sessão de cookies, extrai o corpo (HTML por domínio, PDF por `pdftotext` página a página, OCR `tesseract` nas páginas sem texto, e os anexos linkados no corpo) e grava o resultado em `dados/textos/<chave>.txt`, com o status em `dados/leituras.json`. Os coletores que já têm o texto em mãos (DOU, informes do NF-e, notícias do SVRS) mandam `texto_integral`, que `grava_resultado()` grava no mesmo lugar. `lacuna_analise.py` injeta o texto na lacuna e adia por até 2 dias os itens ainda não lidos. As fontes SVRS e NF-e ganham parsers próprios, porque hoje coletam o menu do site em vez das publicações.

**Tech Stack:** Python 3 stdlib (`html.parser`, `urllib`, `http.cookiejar`, `subprocess`, `unittest`). Binários do sistema no lenovo-claude: `poppler-utils` (`pdfinfo`, `pdftotext`, `pdftoppm`, já instalado) e `tesseract-ocr` + `tesseract-ocr-por` (a instalar). Nenhuma dependência pip nova.

**Spec:** `docs/superpowers/specs/2026-10-01-leitura-integral-design.md`

## Global Constraints

- **Nenhuma dependência pip nova.** `requirements.txt` não muda. PDF e OCR só por binários do sistema chamados via `subprocess`.
- **Código, comentários, docstrings e logs em português**, sem acentuação obrigatória nos comentários (padrão do repo).
- **Scripts rodam como `python3 scripts/<nome>.py`**, com `scripts/` em `sys.path[0]`. Testes fazem `sys.path.insert(0, .../scripts)` antes de importar.
- **Suíte:** `python3 -m unittest discover -s tests -v`. Precisa passar ao fim de cada task. Testes que dependem de `pdftotext`/`tesseract` usam `@unittest.skipUnless(shutil.which(...))`.
- **Um escritor por arquivo.** `dados/leituras.json` só é escrito por `scripts/ler_textos.py`. `dados/textos/<chave>.txt` pode ser escrito por coletores (`grava_resultado`), por `ler_textos.py` e por `reler_dou.py`, mas cada arquivo é de uma chave só e é escrito de forma atômica (tmp + `replace`). `ler_textos.py` nunca escreve `dados/historico.json`.
- **Falha de leitura nunca derruba nada.** Um item que falha vira `status: "falhou"` com o erro registrado. A raia inteira falhando não impede a publicação da varredura (`rodar_varredura.sh` segue). Nada falha em silêncio: todo erro vai para `stderr` e para `leituras.json`.
- **O texto integral nunca entra em `dados/historico.json` nem em `dados/AAAA-MM-DD*.json`.** Itens novos não carregam mais `texto`. Os itens legados que já têm `texto` ficam como estão.
- **Constantes** (valores exatos): `ORCAMENTO_S = 2700` (`ler_textos.py`), `MAX_TENTATIVAS = 4`, `DIAS_SEM_LEITURA = 3` (`textos.py`), `TETO_LACUNA = 60000` (`lacuna_analise.py`), `LIMIAR_PAGINA = 300` e `DPI_OCR = 300` (`leitura/pdf.py`), `MAX_ANEXOS = 10`, `MINIMO_CHARS = 50` (`ler_textos.py`), `MAX_NOTICIAS = 30` (SVRS), `TimeoutStartSec=14400`.

## Review Focus

1. **Página de erro ou "Em construção" respondendo 200** (ex.: `cgibs.gov.br/regulamento-aaaaaaaa`): o esperado é `falhou` com "sem conteudo legivel", não `lido` com lixo. Teste na Task 5 (`test_pagina_quase_vazia_falha`).
2. **PDF corrompido, criptografado ou HTML disfarçado de `.pdf`:** o esperado é `ErroPDF` registrado no item, sem derrubar a execução. Teste na Task 3 (`test_pdf_corrompido_levanta_erro_pdf`) e na Task 5 (`test_erro_inesperado_em_um_item_nao_para_os_outros`).
3. **Documento gigante** (Regulamento do IBS, cerca de 965 mil caracteres): o arquivo guarda tudo, e a lacuna corta em 60 mil com `texto_truncado: true` e `texto_arquivo`. Teste na Task 6 (`test_texto_grande_vem_truncado_com_arquivo`).
4. **Raia de leitura parada por dias** (tesseract quebrado, script com erro): a análise não pode travar para sempre. O item é liberado depois de `DIAS_SEM_LEITURA`. Teste na Task 6 (`test_libera_depois_de_tres_dias_sem_leitura`).
5. **Execução interrompida no meio** (timeout do systemd, queda de energia): o que já foi lido não se perde. `leituras.json` é gravado a cada item. Teste na Task 5 (`test_leituras_gravado_a_cada_item`).

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `scripts/textos.py` (novo) | Caminho, leitura e gravação atômica de `dados/textos/<chave>.txt`. Constantes `MAX_TENTATIVAS` e `DIAS_SEM_LEITURA`, compartilhadas por leitura e lacuna. |
| `scripts/leitura/__init__.py` (novo) | Marcador de pacote. |
| `scripts/leitura/paginas.py` (novo) | Extração do corpo HTML por domínio (CGIBS, gov.br, genérico) e lista de anexos. Absorve o extrator de `portais/cgibs.py`. |
| `scripts/leitura/pdf.py` (novo) | `pdftotext` página a página e OCR por página. |
| `scripts/leitura/baixar.py` (novo) | `Sessao` HTTP com cookies, limite de tamanho, `eh_pdf()`. |
| `scripts/ler_textos.py` (novo) | Orquestrador da raia de leitura. |
| `scripts/semear_analisados.py` (novo) | Marca como analisados os itens antigos de fontes recém-incluídas. |
| `scripts/cobertura_textos.py` (novo) | Relatório de cobertura de texto por fonte. |
| `scripts/reler_dou.py` (novo) | Backfill do texto dos itens antigos do DOU via INLABS. |
| `scripts/portais/govbr.py` (novo) | `GovBrNoticiasPortal`: filtro só para notícias. |
| `scripts/portais/svrs.py` (novo) | `SVRSNoticiasPortal`: notícias inline da listagem. |
| `scripts/portais/nfe.py` (novo) | `NFeInformesPortal` (divInforme) e `NFeListaPortal` (`listaConteudo.aspx`). |
| `scripts/portais/base.py` | Remove o hook `extrai_texto` e adiciona `_registro_vazio()`. |
| `scripts/portais/cgibs.py` | **Removido** (o extrator vai para `leitura/paginas.py`). |
| `scripts/portais/registro.py` | Novas classes e 4 fontes NF-e novas (16 no total). |
| `scripts/varredura.py` | `grava_resultado()` grava `texto_integral` em `dados/textos/`. |
| `scripts/dou.py` | Item passa `texto_integral` (completo) em vez de `texto` (cortado). |
| `scripts/lacuna_analise.py` | Injeta o texto e adia os itens aguardando leitura. |
| `scripts/analise_brief.md` | Regras de leitura: `texto_truncado`, `texto_arquivo`, OCR, anexos. |
| `scripts/rodar_varredura.sh` | Chama `ler_textos.py` depois de `varredura.py`. |
| `deploy/systemd/reforma-ciclo.service` | `TimeoutStartSec=14400`. |
| `CLAUDE.md`, `docs/operacao-local.md`, `README.md` | Documentação da raia nova. |
| Testes novos | `tests/util_pdf.py`, `tests/test_textos.py`, `tests/test_leitura_paginas.py`, `tests/test_leitura_pdf.py`, `tests/test_leitura_baixar.py`, `tests/test_ler_textos.py`, `tests/test_portais_fontes.py`, `tests/test_semear_analisados.py`, `tests/test_cobertura_textos.py` |
| Testes alterados | `tests/test_portais_base.py`, `tests/test_lacuna_analise.py`. **Removido:** `tests/test_portal_cgibs.py`. |

**Sequência:** Tasks 1 a 5 constroem a raia de leitura sem mexer na coleta, e o CGIBS continua extraindo na coleta até a Task 7. Task 6 liga a leitura à análise. Tasks 7 e 8 corrigem as fontes. Task 9 evita a enxurrada na primeira coleta das fontes novas. Task 10 coloca tudo em produção. Task 11 faz o backfill e mede.

---

### Task 1: Armazenamento de texto integral (`textos.py`) + coletores gravando nele

**Files:**
- Create: `scripts/textos.py`
- Modify: `scripts/varredura.py` (`grava_resultado`, import)
- Modify: `scripts/dou.py:276` (campo `texto` → `texto_integral`)
- Test: `tests/test_textos.py`

**Interfaces:**
- Consumes: `portais.base.chave(item) -> str`
- Produces:
  - `textos.caminho(dados: Path|str, chave: str) -> Path`
  - `textos.existe(dados, chave) -> bool`
  - `textos.grava(dados, chave, texto: str) -> Path` (atômico)
  - `textos.le(dados, chave) -> str | None`
  - `textos.MAX_TENTATIVAS = 4`, `textos.DIAS_SEM_LEITURA = 3`
  - Contrato de item de coletor: chave opcional `texto_integral: str`. `grava_resultado` a remove do item (com `pop`) e grava o arquivo se ele ainda não existir.

- [ ] **Step 1: Write the failing test**

`tests/test_textos.py`:
```python
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import textos
import varredura
from portais.base import chave


class TestTextos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_grava_e_le(self):
        textos.grava(self.dados, "abc", "corpo integral")
        self.assertTrue(textos.existe(self.dados, "abc"))
        self.assertEqual(textos.le(self.dados, "abc"), "corpo integral")
        self.assertEqual(textos.caminho(self.dados, "abc"),
                         self.dados / "textos" / "abc.txt")

    def test_le_inexistente_e_none(self):
        self.assertIsNone(textos.le(self.dados, "nada"))
        self.assertFalse(textos.existe(self.dados, "nada"))

    def test_grava_sem_corte_de_tamanho(self):
        grande = "x" * 1_000_000
        textos.grava(self.dados, "g", grande)
        self.assertEqual(len(textos.le(self.dados, "g")), 1_000_000)

    def test_nao_deixa_tmp_para_tras(self):
        textos.grava(self.dados, "abc", "a")
        self.assertEqual([p.name for p in (self.dados / "textos").iterdir()], ["abc.txt"])


class TestGravaResultadoTextoIntegral(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self.tmp.name)
        self.p = patch.object(varredura, "DADOS", self.dados)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def _resultado(self, **extra):
        it = {"titulo": "Resolucao CGIBS n 9", "url": "https://x/r9", "data": None,
              "pasta_arquivo": None, "alerta": None, **extra}
        return [{"fonte": "F", "url": "https://x", "metodo": "http", "total": 1,
                 "erro": None, "itens": [it]}], it

    def test_texto_integral_vai_para_arquivo_e_sai_dos_json(self):
        res, it = self._resultado(texto_integral="CORPO INTEGRAL")
        k = chave(it)
        varredura.grava_resultado("2026-10-01", res, "2026-10-01.json", "novidades.json")
        self.assertEqual(textos.le(self.dados, k), "CORPO INTEGRAL")
        hist = json.loads((self.dados / "historico.json").read_text("utf-8"))
        self.assertNotIn("texto_integral", hist[k])
        dia = (self.dados / "2026-10-01.json").read_text("utf-8")
        self.assertNotIn("CORPO INTEGRAL", dia)
        nov = (self.dados / "novidades.json").read_text("utf-8")
        self.assertNotIn("CORPO INTEGRAL", nov)

    def test_item_ja_no_historico_ganha_arquivo_se_faltava(self):
        res, it = self._resultado()
        varredura.grava_resultado("2026-10-01", res, "a.json", "n.json")
        res2, it2 = self._resultado(texto_integral="AGORA COM TEXTO")
        varredura.grava_resultado("2026-10-02", res2, "b.json", "n.json")
        self.assertEqual(textos.le(self.dados, chave(it2)), "AGORA COM TEXTO")

    def test_nao_sobrescreve_arquivo_existente(self):
        res, it = self._resultado(texto_integral="PRIMEIRO")
        varredura.grava_resultado("2026-10-01", res, "a.json", "n.json")
        res2, _ = self._resultado(texto_integral="SEGUNDO")
        varredura.grava_resultado("2026-10-01", res2, "a.json", "n.json")
        self.assertEqual(textos.le(self.dados, chave(it)), "PRIMEIRO")

    def test_texto_integral_vazio_nao_cria_arquivo(self):
        res, it = self._resultado(texto_integral="   ")
        varredura.grava_resultado("2026-10-01", res, "a.json", "n.json")
        self.assertFalse(textos.existe(self.dados, chave(it)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_textos -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'textos'`

- [ ] **Step 3: Write minimal implementation**

`scripts/textos.py`:
```python
#!/usr/bin/env python3
"""Texto integral das publicacoes: um arquivo por item, dados/textos/<chave>.txt.

Fica fora do historico.json de proposito:
  * sem corte de tamanho — o Regulamento do IBS tem ~965 mil caracteres, e o
    corte de 20.000 que o DOU usava no historico perderia quase tudo;
  * sem condicao de corrida — cada arquivo e' de uma chave so'; dois
    escritores (coletor e raia de leitura) nunca disputam o mesmo arquivo
    ao mesmo tempo, e a gravacao e' atomica (tmp + replace).

As constantes de tentativa ficam aqui porque ler_textos.py (quem tenta) e
lacuna_analise.py (quem espera) precisam concordar sobre elas.
"""
from pathlib import Path

PASTA = "textos"
MAX_TENTATIVAS = 4      # 2 ciclos por dia -> 2 dias tentando antes de desistir
DIAS_SEM_LEITURA = 3    # rede de seguranca: raia de leitura parada nao segura a analise


def caminho(dados, chave):
    return Path(dados) / PASTA / f"{chave}.txt"


def existe(dados, chave):
    return caminho(dados, chave).exists()


def grava(dados, chave, texto):
    p = caminho(dados, chave)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(texto, "utf-8")
    tmp.replace(p)
    return p


def le(dados, chave):
    p = caminho(dados, chave)
    return p.read_text("utf-8") if p.exists() else None
```

Em `scripts/varredura.py`, troque o import:
```python
from portais.base import UA, chave
from portais.registro import PORTAIS
import textos
```
e o laço de `grava_resultado` por:
```python
    for f in resultado:
        for it in f["itens"]:
            # O texto integral vai para dados/textos/<chave>.txt (textos.py),
            # nunca para os JSON: sem corte de tamanho e sem inchar o historico.
            integral = it.pop("texto_integral", None)
            k = chave(it)
            if integral and integral.strip() and not textos.existe(DADOS, k):
                textos.grava(DADOS, k, integral)
            if k not in historico:
                # primeira_vez e' so' a data; com dois ciclos por dia, visto_em
                # (UTC) diz em qual deles o item apareceu
                historico[k] = {"primeira_vez": hoje, "fonte": f["fonte"], **it,
                                "visto_em": visto_em}
                novidades.append(historico[k])
```
Atualize também a docstring do módulo (bloco "Grava:") com a linha:
```
  dados/textos/<chave>.txt  texto integral, quando o coletor o traz (texto_integral)
```

Em `scripts/dou.py`, no dict montado em `coleta()` (hoje `"texto": a.get("_texto", ""),`), troque por:
```python
                    # integral, sem corte: grava_resultado() o leva para
                    # dados/textos/<chave>.txt e o tira do item
                    "texto_integral": a.get("_texto_integral", a.get("_texto", "")),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_textos -v && python3 -m unittest discover -s tests -v`
Expected: tudo PASS. Se algum teste de `test_dou.py` ou `medir_inlabs.py` depender do campo `texto` do item de `coleta()`, rode `grep -n '"texto"' scripts/medir_inlabs.py tests/test_dou.py` e troque para `texto_integral`.

- [ ] **Step 5: Commit**

```bash
git add scripts/textos.py scripts/varredura.py scripts/dou.py tests/test_textos.py
git commit -m "feat: texto integral em dados/textos/<chave>.txt, gravado pelos coletores"
```

---

### Task 2: Extração de corpo HTML por domínio (`leitura/paginas.py`)

**Files:**
- Create: `scripts/leitura/__init__.py`, `scripts/leitura/paginas.py`
- Test: `tests/test_leitura_paginas.py`
- Não toca `scripts/portais/cgibs.py` nesta task (ele sai na Task 7).

**Interfaces:**
- Produces:
  - `paginas.extrai_pagina(url: str, html: str) -> tuple[str | None, list[str]]`: (texto do corpo, URLs absolutas de anexos achados dentro do corpo, sem fragmento, sem repetição, sem a própria URL)
  - `paginas.extrai_artigo_cgibs(html, base="") -> tuple[str|None, list[str]]`
  - `paginas.extrai_govbr(html, base="") -> tuple[str|None, list[str]]`
  - `paginas.extrai_generico(html, base="") -> tuple[str|None, list[str]]`
  - `paginas.eh_anexo(url: str) -> bool`
  - `paginas.MINIMO_GENERICO = 200`

- [ ] **Step 1: Write the failing test**

`tests/test_leitura_paginas.py`:
```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from leitura import paginas

CGIBS = """
<html><body>
<article class="artigo">
  <header class="artigo__cabecalho"><h1 class="artigo__titulo">CGIBS e RFB esclarecem prazos</h1>
  <p class="artigo__subtitulo">Subtitulo fora do corpo</p></header>
  <div class="artigo__texto">
    <div>
      <p>O Comite Gestor do IBS e a Receita Federal esclarecem os prazos.</p>
      <ul><li>D-1001 Informacoes do Contribuinte</li></ul>
      <p>Veja o <a href="/upload/arquivos/202609/ato-4.pdf">Ato Conjunto n 4</a>.</p>
      <script>var x = 1;</script>
    </div>
  </div>
  <div class="artigo__rodape">Voltar Imprimir</div>
</article></body></html>
"""

GOVBR = """
<html><body>
<div id="portal-menu"><a href="/servicos">Servicos</a></div>
<div property="rnews:description" class="documentDescription">Ate o momento, 392.117 solicitacoes.</div>
<div id="viewlet-above-content-body"><a href="http://facebook.com/share">Compartilhe</a></div>
<div id="content-core">
  <div id="parent-fieldname-text" class="">
    <div property="rnews:articleBody"><p>Das solicitacoes, 246.601 indeferidas.</p>
    <p>Integra: <a href="https://www.gov.br/receitafederal/pt-br/x/orientacao.pdf/@@download/file">orientacao</a>
    e <a href="https://www.gov.br/receitafederal/pt-br/x/orientacao.pdf/@@download/file#p2">de novo</a></p></div>
  </div>
</div>
<div class="documentActions">Imprimir</div>
</body></html>
"""

GENERICO = """
<html><body><nav>Menu Inicio Contato</nav><header>Cabecalho do portal</header>
<main><h1>Nota Tecnica 2026.001</h1><p>""" + ("Texto da nota tecnica sobre o leiaute do IBS. " * 10) + """</p>
<a href="exibirArquivo.aspx?conteudo=abc=">baixar</a></main>
<footer>Rodape</footer></body></html>
"""


class TestCGIBS(unittest.TestCase):
    def test_captura_o_corpo_e_nao_o_resto(self):
        t, _ = paginas.extrai_pagina("https://www.cgibs.gov.br/noticia-x", CGIBS)
        self.assertIn("O Comite Gestor do IBS e a Receita Federal", t)
        self.assertIn("D-1001 Informacoes do Contribuinte", t)
        self.assertNotIn("Subtitulo fora do corpo", t)
        self.assertNotIn("Voltar Imprimir", t)
        self.assertNotIn("var x = 1", t)

    def test_anexo_pdf_absoluto(self):
        _, anexos = paginas.extrai_pagina("https://www.cgibs.gov.br/noticia-x", CGIBS)
        self.assertEqual(anexos, ["https://www.cgibs.gov.br/upload/arquivos/202609/ato-4.pdf"])

    def test_html_malformado_nao_lanca(self):
        t, _ = paginas.extrai_artigo_cgibs("<div class='artigo__texto'><p>abc<div>sem fechar")
        self.assertIn("abc", t)

    def test_vazio_ou_none(self):
        self.assertEqual(paginas.extrai_artigo_cgibs(""), (None, []))
        self.assertEqual(paginas.extrai_artigo_cgibs(None), (None, []))


class TestGovBr(unittest.TestCase):
    URL = "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/setembro/balanco"

    def test_resumo_mais_corpo(self):
        t, _ = paginas.extrai_pagina(self.URL, GOVBR)
        self.assertIn("392.117 solicitacoes", t)
        self.assertIn("246.601 indeferidas", t)
        self.assertLess(t.index("392.117"), t.index("246.601"))
        self.assertNotIn("Compartilhe", t)
        self.assertNotIn("Servicos", t)

    def test_anexo_download_sem_repetir_e_sem_fragmento(self):
        _, anexos = paginas.extrai_pagina(self.URL, GOVBR)
        self.assertEqual(anexos, [
            "https://www.gov.br/receitafederal/pt-br/x/orientacao.pdf/@@download/file"])


class TestGenerico(unittest.TestCase):
    URL = "https://www.nfe.fazenda.gov.br/portal/pagina.aspx"

    def test_main_sem_nav_header_footer(self):
        t, anexos = paginas.extrai_pagina(self.URL, GENERICO)
        self.assertIn("Nota Tecnica 2026.001", t)
        self.assertNotIn("Menu Inicio", t)
        self.assertNotIn("Rodape", t)
        self.assertEqual(anexos, [
            "https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=abc="])

    def test_pagina_quase_vazia_devolve_none(self):
        self.assertEqual(paginas.extrai_pagina(self.URL, "<html><body><p>Em construcao</p></body></html>"),
                         (None, []))

    def test_govbr_sem_parent_fieldname_cai_no_generico(self):
        t, _ = paginas.extrai_pagina("https://www.gov.br/pt-br/servicos/x", GENERICO)
        self.assertIn("Nota Tecnica 2026.001", t)


class TestEhAnexo(unittest.TestCase):
    def test_casos(self):
        self.assertTrue(paginas.eh_anexo("https://x/a/b.PDF"))
        self.assertTrue(paginas.eh_anexo("https://www.cgibs.gov.br/upload/arquivos/2026/x"))
        self.assertTrue(paginas.eh_anexo("https://www.gov.br/x/y/@@download/file"))
        self.assertTrue(paginas.eh_anexo("https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=a"))
        self.assertFalse(paginas.eh_anexo("https://www.gov.br/receitafederal/noticia"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_leitura_paginas -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'leitura'`

- [ ] **Step 3: Write minimal implementation**

`scripts/leitura/__init__.py`:
```python
"""Raia de leitura: texto integral das publicacoes (HTML, PDF, OCR).

Usado por scripts/ler_textos.py. Ver
docs/superpowers/specs/2026-10-01-leitura-integral-design.md.
"""
```

`scripts/leitura/paginas.py`:
```python
#!/usr/bin/env python3
"""Corpo integral de paginas HTML, com regra por dominio.

  cgibs.gov.br    -> <div class="artigo__texto"> (veio de portais/cgibs.py)
  *.gov.br (Plone)-> resumo <div class="documentDescription"> +
                     corpo <div id="parent-fieldname-text">
  qualquer outro  -> <article>, <main>, #content, #conteudo, <body>, nessa
                     ordem, descartando nav/header/footer/aside/form

Devolve tambem os links de anexo achados DENTRO do corpo: nas noticias do
gov.br o conteudo de verdade as vezes esta' num PDF anexo, e ler so' o HTML
nao e' leitura integral.
"""
import re
import urllib.parse
from html.parser import HTMLParser

MINIMO_GENERICO = 200   # abaixo disto o "corpo" generico e' casca, nao conteudo


class _Bloco(HTMLParser):
    """Texto (e links) dentro do primeiro elemento <tag> que casa com `casa`.

    Conta a profundidade so' da propria tag-alvo para saber onde o bloco
    termina. Trade-off herdado do extrator do CGIBS: se o bloco tiver uma
    tag-alvo aberta e nunca fechada, a contagem nao zera e o extrator segue
    ate' o fim do documento — sobre-captura, nunca texto truncado.
    """
    IGNORA_SEMPRE = {"script", "style", "noscript", "template"}
    QUEBRA = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "blockquote", "hr", "table", "td", "div", "section", "article"}

    def __init__(self, base, tag, casa, ignora_extra=()):
        super().__init__(convert_charrefs=True)
        self.base, self.tag, self.casa = base, tag, casa
        self.ignora = self.IGNORA_SEMPRE | set(ignora_extra)
        self._prof, self._ign = 0, 0
        self._dentro, self._feito = False, False
        self._buf, self.links = [], []

    def handle_starttag(self, tag, attrs):
        if self._feito:
            return
        a = dict(attrs)
        if not self._dentro:
            if tag == self.tag and self.casa(a):
                self._dentro, self._prof = True, 1
            return
        if tag == self.tag:
            self._prof += 1
        if tag in self.ignora:
            self._ign += 1
        if tag in self.QUEBRA:
            self._buf.append("\n")
        if tag == "a" and a.get("href") and not self._ign:
            self.links.append(urllib.parse.urljoin(self.base, a["href"]))

    def handle_startendtag(self, tag, attrs):
        if self._dentro and not self._feito and tag in self.QUEBRA:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if not self._dentro or self._feito:
            return
        if tag in self.ignora and self._ign:
            self._ign -= 1
        if tag == self.tag:
            self._prof -= 1
            if self._prof <= 0:
                self._dentro, self._feito = False, True

    def handle_data(self, data):
        if self._dentro and not self._feito and not self._ign:
            self._buf.append(data)

    def texto(self):
        t = "".join(self._buf)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)*", "\n\n", t)
        return t.strip()


def _extrai(html, base, tag, casa, ignora_extra=()):
    if not html:
        return None, []
    p = _Bloco(base, tag, casa, ignora_extra)
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass        # devolve o que ja' capturou
    t = p.texto()
    return (t or None), p.links


def _classe(nome):
    return lambda a: nome in (a.get("class") or "").split()


def _id(nome):
    return lambda a: a.get("id") == nome


def _qualquer(a):
    return True


def extrai_artigo_cgibs(html, base=""):
    return _extrai(html, base, "div", _classe("artigo__texto"))


def extrai_govbr(html, base=""):
    resumo, _ = _extrai(html, base, "div", _classe("documentDescription"))
    corpo, links = _extrai(html, base, "div", _id("parent-fieldname-text"))
    if not corpo:
        return None, []
    return (f"{resumo}\n\n{corpo}" if resumo else corpo), links


SEM_CONTEUDO = ("nav", "header", "footer", "aside", "form")


def extrai_generico(html, base=""):
    for tag, casa in (("article", _qualquer), ("main", _qualquer),
                      ("div", _id("content")), ("div", _id("conteudo")),
                      ("body", _qualquer)):
        t, links = _extrai(html, base, tag, casa, SEM_CONTEUDO)
        if t and len(t) >= MINIMO_GENERICO:
            return t, links
    return None, []


def eh_anexo(url):
    p = urllib.parse.urlparse(url).path.lower()
    return (p.endswith(".pdf") or "/upload/arquivos/" in p
            or "@@download" in p or p.endswith("exibirarquivo.aspx"))


def extrai_pagina(url, html):
    """(texto | None, [anexos]) — regra pelo dominio, generico como reserva."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    texto, links = None, []
    if host == "cgibs.gov.br" or host.endswith(".cgibs.gov.br"):
        texto, links = extrai_artigo_cgibs(html, url)
    elif host == "gov.br" or host.endswith(".gov.br"):
        texto, links = extrai_govbr(html, url)
    if not texto:
        texto, links = extrai_generico(html, url)
    proprio = url.split("#")[0]
    anexos = []
    for l in links:
        l = l.split("#")[0]
        if eh_anexo(l) and l != proprio and l not in anexos:
            anexos.append(l)
    return texto, anexos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_leitura_paginas -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add scripts/leitura/__init__.py scripts/leitura/paginas.py tests/test_leitura_paginas.py
git commit -m "feat: leitura/paginas extrai corpo HTML por dominio e lista anexos"
```

---

### Task 3: PDF com OCR por página (`leitura/pdf.py`)

**Files:**
- Create: `scripts/leitura/pdf.py`
- Create: `tests/util_pdf.py` (gerador de PDF mínimo para testes)
- Test: `tests/test_leitura_pdf.py`
- Pré-requisito de ambiente para os testes de integração: `sudo apt-get install -y tesseract-ocr tesseract-ocr-por` (no lenovo-claude, que é exclusivo do Claude; ver Task 10). Sem ele, os testes de OCR real são pulados, e os demais passam.

**Interfaces:**
- Produces:
  - `pdf.extrai_pdf(dados: bytes) -> dict` com `{"texto": str, "paginas": int, "paginas_ocr": list[int], "origem": "pdf" | "pdf+ocr"}`. O texto traz marcadores `[pagina N]`.
  - `pdf.ErroPDF(Exception)`
  - `pdf.num_paginas(arq) -> int`, `pdf.texto_pagina(arq, n) -> str`, `pdf.ocr_pagina(arq, n, pasta) -> str`, `pdf.tem_ocr() -> bool`
  - `pdf.LIMIAR_PAGINA = 300`, `pdf.DPI_OCR = 300`

- [ ] **Step 1: Write the failing test**

`tests/util_pdf.py`:
```python
"""PDF minimo de 1 pagina com texto em Helvetica, montado na mao (sem lib)."""


def pdf_minimo(linhas, tamanho=12):
    corpo = " ".join(f"({l}) Tj T*" for l in linhas)
    conteudo = f"BT /F1 {tamanho} Tf 72 720 Td {tamanho + 4} TL {corpo} ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return out
```

`tests/test_leitura_pdf.py`:
```python
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from leitura import pdf
from util_pdf import pdf_minimo

TEM_POPPLER = all(shutil.which(b) for b in ("pdfinfo", "pdftotext", "pdftoppm"))
TEM_TESSERACT = shutil.which("tesseract") is not None
LONGO = "x" * 400


class TestDecisaoPorPagina(unittest.TestCase):
    """Logica de decisao com os binarios simulados."""

    def _roda(self, textos_paginas, ocr_por_pagina, tem_ocr=True):
        with patch.object(pdf, "num_paginas", return_value=len(textos_paginas)), \
             patch.object(pdf, "texto_pagina", side_effect=lambda a, n: textos_paginas[n - 1]), \
             patch.object(pdf, "ocr_pagina", side_effect=lambda a, n, p: ocr_por_pagina[n]) as ocr, \
             patch.object(pdf, "tem_ocr", return_value=tem_ocr):
            return pdf.extrai_pdf(b"%PDF-1.4 falso"), ocr

    def test_paginas_com_texto_nao_passam_por_ocr(self):
        r, ocr = self._roda([LONGO, LONGO], {})
        self.assertEqual(r["origem"], "pdf")
        self.assertEqual(r["paginas_ocr"], [])
        self.assertEqual(r["paginas"], 2)
        ocr.assert_not_called()

    def test_pagina_so_com_carimbo_vai_para_ocr(self):
        carimbo = "FLAVIO CESAR Assinado de forma digital"
        r, _ = self._roda([carimbo], {1: "ATO CONJUNTO RFB/CGIBS " + LONGO})
        self.assertEqual(r["origem"], "pdf+ocr")
        self.assertEqual(r["paginas_ocr"], [1])
        self.assertIn("ATO CONJUNTO RFB/CGIBS", r["texto"])

    def test_pdf_misto_ocr_so_na_pagina_escaneada(self):
        r, ocr = self._roda([LONGO, "", LONGO], {2: "pagina escaneada " + LONGO})
        self.assertEqual(r["paginas_ocr"], [2])
        self.assertEqual(ocr.call_count, 1)
        self.assertIn("[pagina 2]\npagina escaneada", r["texto"])

    def test_ocr_pior_que_texto_mantem_texto(self):
        r, _ = self._roda(["curto mas real"], {1: ""})
        self.assertEqual(r["origem"], "pdf")
        self.assertIn("curto mas real", r["texto"])

    def test_sem_tesseract_e_pagina_vazia_levanta(self):
        with self.assertRaises(pdf.ErroPDF) as cm:
            self._roda([LONGO, ""], {}, tem_ocr=False)
        self.assertIn("tesseract", str(cm.exception))


@unittest.skipUnless(TEM_POPPLER, "poppler-utils ausente")
class TestPopplerReal(unittest.TestCase):
    def test_pdf_com_texto(self):
        linhas = [f"Linha {i} do Ato Conjunto RFB CGIBS sobre o IBS e a CBS" for i in range(12)]
        r = pdf.extrai_pdf(pdf_minimo(linhas))
        self.assertEqual(r["paginas"], 1)
        self.assertIn("Linha 11 do Ato Conjunto", r["texto"])
        self.assertEqual(r["origem"], "pdf")

    def test_pdf_corrompido_levanta_erro_pdf(self):
        with self.assertRaises(pdf.ErroPDF):
            pdf.extrai_pdf(b"%PDF-1.4\nlixo sem estrutura nenhuma")


@unittest.skipUnless(TEM_POPPLER and TEM_TESSERACT, "tesseract ausente")
class TestOCRReal(unittest.TestCase):
    def test_ocr_le_pagina_renderizada(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "a.pdf"
            arq.write_bytes(pdf_minimo(["RESOLUCAO CGIBS NUMERO SETE"], tamanho=28))
            t = pdf.ocr_pagina(arq, 1, d)
        self.assertIn("CGIBS", t.upper())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_leitura_pdf -v`
Expected: FAIL com `ImportError: cannot import name 'pdf' from 'leitura'`

- [ ] **Step 3: Write minimal implementation**

`scripts/leitura/pdf.py`:
```python
#!/usr/bin/env python3
"""Texto de PDF: pdftotext pagina a pagina; OCR (tesseract, portugues) nas
paginas que vem praticamente sem texto.

Binarios do sistema (lenovo-claude): poppler-utils (pdfinfo, pdftotext,
pdftoppm) e tesseract-ocr + tesseract-ocr-por. Sem dependencia pip.

Por que a decisao e' por pagina: o Ato Conjunto RFB/CGIBS de 29/05/2026 e'
"Microsoft: Print To PDF" — imagem pura; o pdftotext devolve so' o carimbo
da assinatura digital (156 caracteres). Um limiar no documento inteiro nao
pegaria um PDF misto (paginas de texto + paginas escaneadas).

OCR e' lento (segundos por pagina) e isso e' aceito: o orcamento da raia de
leitura (ler_textos.ORCAMENTO_S) e' de 45 min e o backfill roda sem limite.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LIMIAR_PAGINA = 300          # caracteres nao-brancos abaixo disto -> tenta OCR
DPI_OCR = 300
TIMEOUT_TEXTO_S = 120
TIMEOUT_OCR_S = 600          # por pagina: lento e tudo bem, so' nao pode travar


class ErroPDF(Exception):
    pass


def _roda(cmd, timeout=TIMEOUT_TEXTO_S):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ErroPDF(f"{cmd[0]} passou de {timeout}s") from e
    except FileNotFoundError as e:
        raise ErroPDF(f"{cmd[0]} nao instalado") from e
    if r.returncode != 0:
        raise ErroPDF(f"{cmd[0]} saiu com {r.returncode}: "
                      f"{r.stderr[:200].decode('utf-8', 'replace').strip()}")
    return r.stdout


def tem_ocr():
    return shutil.which("tesseract") is not None


def num_paginas(arq):
    saida = _roda(["pdfinfo", str(arq)]).decode("utf-8", "replace")
    m = re.search(r"^Pages:\s+(\d+)", saida, re.M)
    if not m:
        raise ErroPDF("pdfinfo sem contagem de paginas")
    return int(m.group(1))


def texto_pagina(arq, n):
    return _roda(["pdftotext", "-layout", "-enc", "UTF-8", "-f", str(n), "-l", str(n),
                  str(arq), "-"]).decode("utf-8", "replace")


def ocr_pagina(arq, n, pasta):
    raiz = Path(pasta) / f"ocr-p{n}"
    _roda(["pdftoppm", "-r", str(DPI_OCR), "-gray", "-png", "-singlefile",
           "-f", str(n), "-l", str(n), str(arq), str(raiz)], timeout=TIMEOUT_OCR_S)
    png = raiz.with_suffix(".png")
    try:
        return _roda(["tesseract", str(png), "stdout", "-l", "por"],
                     timeout=TIMEOUT_OCR_S).decode("utf-8", "replace")
    finally:
        png.unlink(missing_ok=True)


def _uteis(t):
    return len(re.sub(r"\s+", "", t or ""))


def extrai_pdf(dados):
    with tempfile.TemporaryDirectory(prefix="leitura-pdf-") as pasta:
        arq = Path(pasta) / "doc.pdf"
        arq.write_bytes(dados)
        n = num_paginas(arq)
        partes, ocr, sem_ocr = [], [], []
        for i in range(1, n + 1):
            t = texto_pagina(arq, i)
            if _uteis(t) < LIMIAR_PAGINA:
                if not tem_ocr():
                    sem_ocr.append(i)
                else:
                    o = ocr_pagina(arq, i, pasta)
                    if _uteis(o) > _uteis(t):
                        t = o
                        ocr.append(i)
            partes.append(f"[pagina {i}]\n{t.strip()}")
    if sem_ocr:
        raise ErroPDF(f"paginas {sem_ocr} sem texto e tesseract nao instalado")
    return {"texto": "\n\n".join(partes), "paginas": n, "paginas_ocr": ocr,
            "origem": "pdf+ocr" if ocr else "pdf"}
```

Observação: `test_ocr_pior_que_texto_mantem_texto` tem uma página com menos de 300 caracteres e `tem_ocr=True`. O OCR roda, devolve vazio, e o texto original fica.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_leitura_pdf -v`
Expected: PASS. `TestOCRReal` aparece como `skipped` se o tesseract ainda não estiver instalado. Nesse caso, instale (`sudo apt-get install -y tesseract-ocr tesseract-ocr-por`), rode de novo e confirme o PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/leitura/pdf.py tests/util_pdf.py tests/test_leitura_pdf.py
git commit -m "feat: leitura/pdf extrai texto por pagina com OCR tesseract nas paginas sem texto"
```

---

### Task 4: Download com sessão de cookies (`leitura/baixar.py`)

**Files:**
- Create: `scripts/leitura/baixar.py`
- Test: `tests/test_leitura_baixar.py`

**Interfaces:**
- Consumes: `portais.base.UA`
- Produces:
  - `baixar.Resposta` (namedtuple `dados: bytes, tipo: str, charset: str|None, url: str`), em que `url` é a URL final, depois de redirects
  - `baixar.ErroDownload(Exception)`
  - `baixar.Sessao(timeout=90)` com `.baixa(url) -> Resposta` e `.baixa_html(url) -> tuple[str, str]` (html decodificado, URL final)
  - `baixar.eh_pdf(dados: bytes) -> bool`
  - `baixar.MAX_BYTES = 100 * 1024 * 1024`

- [ ] **Step 1: Write the failing test**

`tests/test_leitura_baixar.py`:
```python
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from leitura import baixar


class _Handler(BaseHTTPRequestHandler):
    """Imita o Portal NF-e: sem cookie de sessao, redireciona para si mesmo."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/sessao"):
            if "ASP.NET_SessionId=ok" not in (self.headers.get("Cookie") or ""):
                self.send_response(302)
                self.send_header("Set-Cookie", "ASP.NET_SessionId=ok; path=/")
                self.send_header("Location", self.path)
                self.end_headers()
                return
            corpo = "<html><body>informe é aqui</body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/doc":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(b"%PDF-1.4\n...")
        elif self.path == "/grande":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 5000)
        else:
            self.send_response(404)
            self.end_headers()


class TestSessao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_cookie_de_sessao_resolve_o_loop_de_redirect(self):
        html, url = baixar.Sessao(timeout=5).baixa_html(self.base + "/sessao?x=1")
        self.assertIn("informe é aqui", html)
        self.assertTrue(url.endswith("/sessao?x=1"))

    def test_pdf_reconhecido_pelo_conteudo_nao_pelo_cabecalho(self):
        r = baixar.Sessao(timeout=5).baixa(self.base + "/doc")
        self.assertTrue(baixar.eh_pdf(r.dados))

    def test_404_vira_erro_download(self):
        with self.assertRaises(baixar.ErroDownload) as cm:
            baixar.Sessao(timeout=5).baixa(self.base + "/nada")
        self.assertIn("404", str(cm.exception))

    def test_arquivo_grande_demais(self):
        with patch.object(baixar, "MAX_BYTES", 1000):
            with self.assertRaises(baixar.ErroDownload):
                baixar.Sessao(timeout=5).baixa(self.base + "/grande")

    def test_host_inexistente_vira_erro_download(self):
        with self.assertRaises(baixar.ErroDownload):
            baixar.Sessao(timeout=3).baixa("http://127.0.0.1:1/x")


class TestEhPdf(unittest.TestCase):
    def test_casos(self):
        self.assertTrue(baixar.eh_pdf(b"%PDF-1.7\n"))
        self.assertTrue(baixar.eh_pdf(b"\r\n  %PDF-1.4"))
        self.assertFalse(baixar.eh_pdf(b"<html>%PDF</html>"[:4]))
        self.assertFalse(baixar.eh_pdf(b"<!DOCTYPE html>"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_leitura_baixar -v`
Expected: FAIL com `ImportError: cannot import name 'baixar'`

- [ ] **Step 3: Write minimal implementation**

`scripts/leitura/baixar.py`:
```python
#!/usr/bin/env python3
"""Download com sessao (cookies), para a raia de leitura e para as fontes
que exigem sessao.

O Portal NF-e (nfe.fazenda.gov.br) responde 302 para a propria URL ate'
receber o cookie ASP.NET_SessionId que ele mesmo manda — sem cookie jar, o
cliente entra em loop de redirect (curl: "Maximum (50) redirects"). O
urllib puro de portais.base.via_http nao guarda cookie; por isso esta
classe existe.
"""
import http.cookiejar
import ssl
import urllib.error
import urllib.request
from collections import namedtuple

from portais.base import UA

TIMEOUT_S = 90
MAX_BYTES = 100 * 1024 * 1024

Resposta = namedtuple("Resposta", "dados tipo charset url")


class ErroDownload(Exception):
    pass


def eh_pdf(dados):
    return dados[:1024].lstrip().startswith(b"%PDF-")


class Sessao:
    def __init__(self, timeout=TIMEOUT_S):
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def baixa(self, url):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                dados = r.read(MAX_BYTES + 1)
                if len(dados) > MAX_BYTES:
                    raise ErroDownload(f"maior que {MAX_BYTES} bytes")
                return Resposta(dados, r.headers.get_content_type(),
                                r.headers.get_content_charset(), r.geturl())
        except ErroDownload:
            raise
        except urllib.error.HTTPError as e:
            raise ErroDownload(f"HTTP {e.code}") from e
        except Exception as e:
            raise ErroDownload(f"{type(e).__name__}: {str(e)[:160]}") from e

    def baixa_html(self, url):
        r = self.baixa(url)
        return r.dados.decode(r.charset or "utf-8", "replace"), r.url
```

Nota: `eh_pdf` usa `lstrip()` porque alguns servidores mandam `\r\n` antes do `%PDF`. O caso `b"<htm"` do teste confere que HTML não é tomado por PDF.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_leitura_baixar -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/leitura/baixar.py tests/test_leitura_baixar.py
git commit -m "feat: leitura/baixar com sessao de cookies e limite de tamanho"
```

---

### Task 5: Orquestrador da raia de leitura (`ler_textos.py`)

**Files:**
- Create: `scripts/ler_textos.py`
- Test: `tests/test_ler_textos.py`

**Interfaces:**
- Consumes: `textos.*` (Task 1), `paginas.extrai_pagina` (Task 2), `pdf.extrai_pdf`, `pdf.ErroPDF` (Task 3), `baixar.Sessao`, `baixar.eh_pdf`, `baixar.ErroDownload`, `baixar.Resposta` (Task 4)
- Produces:
  - `ler_textos.executa(dados: Path, orcamento: int | None = ORCAMENTO_S, chaves: set[str] | None = None, sessao=None) -> collections.Counter` (contagem por status)
  - `ler_textos.le_item(sessao, item: dict) -> dict` `{"texto", "origem", "paginas_ocr": int, "anexos": list[str], "anexos_falhos": list[dict]}`, que levanta `ErroLeitura`, `ErroDownload` ou `ErroPDF`
  - `ler_textos.a_ler(dados, historico, leituras, chaves=None) -> list[str]`
  - Schema de `dados/leituras.json`: `{chave: {"status": "lido"|"parcial"|"falhou"|"desistiu", "origem": "coleta"|"coleta_cortada"|"inlabs"|"html"|"pdf"|"pdf+ocr", "chars": int, "paginas_ocr": int, "anexos": [url], "anexos_falhos": [{"url","erro"}], "tentativas": int, "erro": str, "lido_em"|"tentado_em": "AAAA-MM-DDTHH:MM:SSZ"}}`
  - CLI: `python3 scripts/ler_textos.py [--orcamento S] [--sem-limite] [--chave K ...]`

- [ ] **Step 1: Write the failing test**

`tests/test_ler_textos.py`:
```python
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ler_textos
import textos
from leitura import baixar, pdf

LONGO = "Corpo integral da publicacao sobre o IBS e a CBS. " * 10


def html_govbr(corpo, anexo=None):
    a = f'<a href="{anexo}">anexo</a>' if anexo else ""
    return (f'<html><body><div id="parent-fieldname-text"><p>{corpo}</p>{a}</div>'
            f'</body></html>').encode("utf-8")


class FakeSessao:
    def __init__(self, mapa):
        self.mapa, self.pedidos = mapa, []

    def baixa(self, url):
        self.pedidos.append(url)
        v = self.mapa.get(url)
        if v is None:
            raise baixar.ErroDownload("HTTP 404")
        if isinstance(v, Exception):
            raise v
        return baixar.Resposta(v, "text/html", "utf-8", url)


def item(url, fonte="RFB - Noticias 2026", primeira_vez="2026-10-01", **extra):
    return {"titulo": "T " + url, "url": url, "fonte": fonte,
            "primeira_vez": primeira_vez, "visto_em": primeira_vez + "T08:00:00Z", **extra}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dados = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def hist(self, d):
        (self.dados / "historico.json").write_text(json.dumps(d), "utf-8")

    def leituras(self):
        return json.loads((self.dados / "leituras.json").read_text("utf-8"))

    def roda(self, sessao, **kw):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return ler_textos.executa(self.dados, sessao=sessao, **kw)


class TestExecuta(Base):
    def test_html_lido_vai_para_arquivo_e_leituras(self):
        u = "https://www.gov.br/receitafederal/noticia-a"
        self.hist({"k1": item(u)})
        self.roda(FakeSessao({u: html_govbr(LONGO)}))
        self.assertIn("Corpo integral", textos.le(self.dados, "k1"))
        l = self.leituras()["k1"]
        self.assertEqual((l["status"], l["origem"], l["tentativas"]), ("lido", "html", 1))
        self.assertEqual(l["chars"], len(textos.le(self.dados, "k1")))

    def test_historico_nunca_e_escrito(self):
        u = "https://www.gov.br/x/noticia-a"
        self.hist({"k1": item(u)})
        antes = (self.dados / "historico.json").read_bytes()
        self.roda(FakeSessao({u: html_govbr(LONGO)}))
        self.assertEqual((self.dados / "historico.json").read_bytes(), antes)

    def test_pdf_direto(self):
        u = "https://www.cgibs.gov.br/upload/arquivos/202606/ato.pdf"
        self.hist({"k1": item(u, fonte="CGIBS - Atos Conjuntos")})
        with patch.object(pdf, "extrai_pdf", return_value={
                "texto": "[pagina 1]\n" + LONGO, "paginas": 1, "paginas_ocr": [1],
                "origem": "pdf+ocr"}):
            self.roda(FakeSessao({u: b"%PDF-1.4 ..."}))
        l = self.leituras()["k1"]
        self.assertEqual((l["status"], l["origem"], l["paginas_ocr"]), ("lido", "pdf+ocr", 1))

    def test_anexo_e_lido_e_concatenado(self):
        u = "https://www.gov.br/x/orientacao"
        a = "https://www.gov.br/x/orientacao.pdf"
        self.hist({"k1": item(u)})
        with patch.object(pdf, "extrai_pdf", return_value={
                "texto": "TEXTO DO ANEXO", "paginas": 1, "paginas_ocr": [], "origem": "pdf"}):
            self.roda(FakeSessao({u: html_govbr(LONGO, anexo=a), a: b"%PDF-1.4"}))
        t = textos.le(self.dados, "k1")
        self.assertIn("===== ANEXO: " + a, t)
        self.assertIn("TEXTO DO ANEXO", t)
        self.assertEqual(self.leituras()["k1"]["anexos"], [a])

    def test_anexo_que_falha_deixa_parcial_e_tenta_de_novo(self):
        u = "https://www.gov.br/x/orientacao"
        a = "https://www.gov.br/x/orientacao.pdf"
        self.hist({"k1": item(u)})
        self.roda(FakeSessao({u: html_govbr(LONGO, anexo=a)}))     # anexo da 404
        l = self.leituras()["k1"]
        self.assertEqual(l["status"], "parcial")
        self.assertEqual(l["anexos_falhos"][0]["url"], a)
        self.assertTrue(textos.existe(self.dados, "k1"))
        s = FakeSessao({u: html_govbr(LONGO, anexo=a)})
        self.roda(s)
        self.assertIn(u, s.pedidos)                                   # tentou de novo

    def test_pagina_quase_vazia_falha(self):
        u = "https://www.cgibs.gov.br/regulamento-aaaaaaaa"
        self.hist({"k1": item(u, fonte="CGIBS - Regulamentos")})
        self.roda(FakeSessao({u: b"<html><body><p>Em construcao</p></body></html>"}))
        l = self.leituras()["k1"]
        self.assertEqual(l["status"], "falhou")
        self.assertIn("sem conteudo legivel", l["erro"])
        self.assertFalse(textos.existe(self.dados, "k1"))

    def test_desiste_depois_de_max_tentativas(self):
        u = "https://www.gov.br/x/fora"
        self.hist({"k1": item(u)})
        for _ in range(textos.MAX_TENTATIVAS):
            self.roda(FakeSessao({}))
        self.assertEqual(self.leituras()["k1"]["status"], "desistiu")
        s = FakeSessao({})
        self.roda(s)
        self.assertEqual(s.pedidos, [])                               # nao tenta mais

    def test_erro_inesperado_em_um_item_nao_para_os_outros(self):
        u1, u2 = "https://www.gov.br/x/a", "https://www.gov.br/x/b"
        self.hist({"k1": item(u1, primeira_vez="2026-10-01"),
                   "k2": item(u2, primeira_vez="2026-09-30")})
        self.roda(FakeSessao({u1: RuntimeError("bug"), u2: html_govbr(LONGO)}))
        l = self.leituras()
        self.assertEqual(l["k1"]["status"], "falhou")
        self.assertIn("RuntimeError", l["k1"]["erro"])
        self.assertEqual(l["k2"]["status"], "lido")

    def test_leituras_gravado_a_cada_item(self):
        u1, u2 = "https://www.gov.br/x/a", "https://www.gov.br/x/b"
        self.hist({"k1": item(u1, primeira_vez="2026-10-01"),
                   "k2": item(u2, primeira_vez="2026-09-30")})

        class Interrompe(FakeSessao):
            def baixa(s, url):
                if url == u2:
                    raise KeyboardInterrupt
                return super().baixa(url)

        with self.assertRaises(KeyboardInterrupt):
            self.roda(Interrompe({u1: html_govbr(LONGO)}))
        self.assertEqual(self.leituras()["k1"]["status"], "lido")

    def test_mais_recentes_primeiro_e_orcamento(self):
        u1, u2 = "https://www.gov.br/x/velho", "https://www.gov.br/x/novo"
        self.hist({"kv": item(u1, primeira_vez="2026-08-17"),
                   "kn": item(u2, primeira_vez="2026-10-01")})
        s = FakeSessao({u1: html_govbr(LONGO), u2: html_govbr(LONGO)})
        # chamadas: limite, checagem do 1o, t0, impressao do 1o, checagem do 2o
        with patch.object(ler_textos.time, "monotonic", side_effect=[0, 0, 0, 0, 10_000]):
            self.roda(s, orcamento=60)
        self.assertEqual(s.pedidos, [u2])

    def test_dou_nunca_e_baixado(self):
        u = "http://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp?data=17/08/2026"
        self.hist({"k1": item(u, fonte="DOU DO1 (revisar)")})
        s = FakeSessao({})
        self.roda(s)
        self.assertEqual(s.pedidos, [])

    def test_chave_explicita_rele_mesmo_ja_lido(self):
        u = "https://www.gov.br/x/a"
        self.hist({"k1": item(u)})
        self.roda(FakeSessao({u: html_govbr(LONGO)}))
        s = FakeSessao({u: html_govbr("NOVA VERSAO " + LONGO)})
        self.roda(s, chaves={"k1"})
        self.assertIn("NOVA VERSAO", textos.le(self.dados, "k1"))


class TestLegado(Base):
    def test_texto_no_historico_migra_para_arquivo(self):
        self.hist({"k1": item("https://www.cgibs.gov.br/n", fonte="CGIBS - Noticias",
                              texto="corpo antigo do CGIBS")})
        s = FakeSessao({})
        self.roda(s)
        self.assertEqual(textos.le(self.dados, "k1"), "corpo antigo do CGIBS")
        self.assertEqual(self.leituras()["k1"]["origem"], "coleta")
        self.assertEqual(s.pedidos, [])

    def test_dou_legado_com_20000_fica_marcado_cortado(self):
        self.hist({"k1": item("http://x", fonte="DOU DO1", texto="a" * 20000)})
        self.roda(FakeSessao({}))
        self.assertEqual(self.leituras()["k1"]["origem"], "coleta_cortada")

    def test_arquivo_do_coletor_e_registrado(self):
        self.hist({"k1": item("http://x", fonte="DOU DO1"),
                   "k2": item("https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias#3007",
                              fonte="Portal DF-e SVRS - Noticias")})
        textos.grava(self.dados, "k1", "integral do inlabs")
        textos.grava(self.dados, "k2", "noticia inline")
        self.roda(FakeSessao({}))
        l = self.leituras()
        self.assertEqual((l["k1"]["status"], l["k1"]["origem"]), ("lido", "inlabs"))
        self.assertEqual((l["k2"]["status"], l["k2"]["origem"]), ("lido", "coleta"))

    def test_reler_dou_substitui_cortado(self):
        self.hist({"k1": item("http://x", fonte="DOU DO1", texto="a" * 20000)})
        self.roda(FakeSessao({}))
        textos.grava(self.dados, "k1", "a" * 35000)                   # reler_dou.py
        self.roda(FakeSessao({}))
        l = self.leituras()["k1"]
        self.assertEqual((l["origem"], l["chars"]), ("inlabs", 35000))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ler_textos -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'ler_textos'`

- [ ] **Step 3: Write minimal implementation**

`scripts/ler_textos.py`:
```python
#!/usr/bin/env python3
"""Raia de leitura: texto integral de cada item do historico que ainda nao tem.

Roda depois da varredura, so' no notebook (rodar_varredura.sh; ver
docs/operacao-local.md). O GitHub Actions (plano B) nao roda esta raia: o
que ele coletar e' lido no proximo ciclo local.

Le dados/historico.json e NUNCA o escreve. Escreve so':
  dados/textos/<chave>.txt   texto integral (scripts/textos.py)
  dados/leituras.json        status de cada leitura — unico escritor e' este script

Para cada item: baixa a URL com sessao de cookies; se for PDF, pdftotext
pagina a pagina com OCR nas paginas sem texto; se for HTML, o corpo pela
regra do dominio, mais os anexos (PDF) linkados dentro do corpo.

Itens do DOU nao sao baixados aqui: o texto deles vem do INLABS na coleta
(dou.py) ou, para os antigos, de scripts/reler_dou.py.

Uso:
  python3 scripts/ler_textos.py                  # orcamento padrao (45 min)
  python3 scripts/ler_textos.py --sem-limite     # backfill manual
  python3 scripts/ler_textos.py --chave K [--chave K2]   # rele estes, mesmo ja' lidos
"""
import argparse
import collections
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos
from leitura import baixar, paginas, pdf

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"

ORCAMENTO_S = 2700       # 45 min por ciclo; OCR e' lento e tudo bem
MAX_ANEXOS = 10
MINIMO_CHARS = 50        # menos que isto nao e' publicacao, e' casca de pagina
CORTE_DOU_LEGADO = 20000  # dou.py guardava `texto` cortado neste tamanho


class ErroLeitura(Exception):
    pass


def agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carrega_json(p, padrao):
    return json.loads(p.read_text("utf-8")) if p.exists() else padrao


def grava_json(p, obj):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
    tmp.replace(p)


def _eh_dou(it):
    return (it.get("fonte") or "").startswith("DOU")


def migra_legado(dados, historico, leituras):
    """Itens com `texto` dentro do historico (DOU desde a Parte A, CGIBS desde
    a Parte B) passam para dados/textos/. Texto do DOU com 20.000 caracteres
    veio cortado: fica `coleta_cortada` ate' reler_dou.py trazer o integral."""
    for k, it in historico.items():
        t = (it.get("texto") or "").strip()
        if t and not textos.existe(dados, k):
            textos.grava(dados, k, t)
            cortado = _eh_dou(it) and len(it["texto"]) >= CORTE_DOU_LEGADO
            leituras[k] = {"status": "lido",
                           "origem": "coleta_cortada" if cortado else "coleta",
                           "chars": len(t), "tentativas": 0, "lido_em": agora()}


def registra_coletados(dados, historico, leituras):
    """Arquivo gravado por um coletor (ou por reler_dou.py) sem registro aqui."""
    for k, it in historico.items():
        if not textos.existe(dados, k):
            continue
        meta = leituras.get(k)
        n = len(textos.le(dados, k))
        if meta is None:
            leituras[k] = {"status": "lido", "origem": "inlabs" if _eh_dou(it) else "coleta",
                           "chars": n, "tentativas": 0, "lido_em": agora()}
        elif meta.get("origem") == "coleta_cortada" and n > meta.get("chars", 0):
            leituras[k] = {**meta, "origem": "inlabs", "chars": n, "lido_em": agora()}


def a_ler(dados, historico, leituras, chaves=None):
    """Chaves a ler, mais recentes primeiro (o item novo nao espera o backfill)."""
    out = []
    for k, it in historico.items():
        if chaves is not None:
            if k in chaves and not _eh_dou(it):
                out.append(k)
            continue
        if _eh_dou(it):
            continue
        meta = leituras.get(k, {})
        st = meta.get("status")
        if st in ("lido", "desistiu"):
            continue
        if st == "parcial" and meta.get("tentativas", 0) >= textos.MAX_TENTATIVAS:
            continue
        if st is None and textos.existe(dados, k):
            continue
        out.append(k)
    out.sort(key=lambda k: historico[k].get("visto_em") or historico[k].get("primeira_vez") or "",
             reverse=True)
    return out


def _de_resposta(resp):
    """-> (texto, origem, paginas_ocr, anexos)"""
    if baixar.eh_pdf(resp.dados):
        r = pdf.extrai_pdf(resp.dados)
        return r["texto"], r["origem"], len(r["paginas_ocr"]), []
    html = resp.dados.decode(resp.charset or "utf-8", "replace")
    texto, anexos = paginas.extrai_pagina(resp.url, html)
    return texto, "html", 0, anexos


def le_item(sessao, it):
    texto, origem, ocr, anexos = _de_resposta(sessao.baixa(it["url"]))
    partes = [texto] if texto else []
    lidos, falhos = [], []
    for a in anexos[:MAX_ANEXOS]:
        try:
            t, o, n_ocr, _ = _de_resposta(sessao.baixa(a))   # anexo de anexo nao e' seguido
        except (baixar.ErroDownload, pdf.ErroPDF) as e:
            falhos.append({"url": a, "erro": str(e)[:200]})
            continue
        if t:
            partes.append(f"===== ANEXO: {a} =====\n{t}")
            lidos.append(a)
            ocr += n_ocr
    final = "\n\n".join(partes)
    if len(final.strip()) < MINIMO_CHARS:
        raise ErroLeitura("sem conteudo legivel")
    if ocr and "ocr" not in origem:
        origem += "+ocr"
    return {"texto": final, "origem": origem, "paginas_ocr": ocr,
            "anexos": lidos, "anexos_falhos": falhos}


def executa(dados, orcamento=ORCAMENTO_S, chaves=None, sessao=None):
    dados = Path(dados)
    historico = carrega_json(dados / "historico.json", {})
    arq = dados / "leituras.json"
    leituras = carrega_json(arq, {})
    migra_legado(dados, historico, leituras)
    registra_coletados(dados, historico, leituras)
    grava_json(arq, leituras)

    pend = a_ler(dados, historico, leituras, chaves)
    sessao = sessao or baixar.Sessao()
    limite = time.monotonic() + orcamento if orcamento else None
    cont = collections.Counter()
    print(f"leitura: {len(pend)} item(ns) a ler", file=sys.stderr)
    for i, k in enumerate(pend):
        if limite is not None and time.monotonic() > limite:
            print(f"leitura: orcamento esgotado; {len(pend) - i} item(ns) ficam "
                  "para o proximo ciclo", file=sys.stderr)
            cont["adiado"] += len(pend) - i
            break
        it, ant = historico[k], leituras.get(k, {})
        tent = (0 if chaves else ant.get("tentativas", 0)) + 1
        t0 = time.monotonic()
        try:
            r = le_item(sessao, it)
        except Exception as e:      # um item nunca derruba a raia
            st = "desistiu" if tent >= textos.MAX_TENTATIVAS else "falhou"
            leituras[k] = {**ant, "status": st, "tentativas": tent,
                           "erro": f"{type(e).__name__}: {str(e)[:200]}", "tentado_em": agora()}
        else:
            textos.grava(dados, k, r["texto"])
            st = "parcial" if r["anexos_falhos"] else "lido"
            leituras[k] = {"status": st, "origem": r["origem"], "chars": len(r["texto"]),
                           "paginas_ocr": r["paginas_ocr"], "anexos": r["anexos"],
                           "anexos_falhos": r["anexos_falhos"], "tentativas": tent,
                           "lido_em": agora()}
        grava_json(arq, leituras)    # a cada item: interrupcao nao perde o que ja' foi lido
        cont[st] += 1
        print(f"  {st:8} {time.monotonic() - t0:6.1f}s {it.get('fonte', '')[:28]:28} "
              f"{it['url'][:90]}" + (f"  [{leituras[k].get('erro')}]"
                                     if st in ("falhou", "desistiu") else ""),
              file=sys.stderr)
    print("leitura: " + ", ".join(f"{v} {s}" for s, v in sorted(cont.items())) if cont
          else "leitura: nada a ler", file=sys.stderr)
    return cont


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--orcamento", type=int, default=ORCAMENTO_S)
    ap.add_argument("--sem-limite", action="store_true")
    ap.add_argument("--chave", action="append")
    a = ap.parse_args(argv)
    executa(DADOS, orcamento=None if a.sem_limite else a.orcamento,
            chaves=set(a.chave) if a.chave else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Nota sobre `test_mais_recentes_primeiro_e_orcamento`: o `side_effect` de `time.monotonic` cobre as 5 chamadas na ordem (limite, checagem do 1º item, `t0`, impressão do 1º, checagem do 2º). Se a ordem de chamadas mudar, ajuste a lista. O que importa é que só a URL mais recente seja pedida.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ler_textos -v && python3 -m unittest discover -s tests -v`
Expected: PASS (todos)

- [ ] **Step 5: Smoke test contra a rede real (sem commitar o resultado)**

```bash
cp -r dados /tmp/claude-1000/dados-smoke
.venv/bin/python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
import json, ler_textos
from pathlib import Path
d = Path("/tmp/claude-1000/dados-smoke")
h = json.loads((d / "historico.json").read_text())
ks = {k for k, v in h.items() if "balanco-de-solicitacoes" in v["url"] and v["url"].endswith("-1")}
ks |= {k for k, v in h.items() if "03111600-ato-conjunto" in v["url"]}
print(ler_textos.executa(d, orcamento=None, chaves=ks))
for k in ks: print(k, json.loads((d / "leituras.json").read_text())[k])
EOF
```
Expected: a notícia da RFB de 30/09 com `origem: html` e "145.516" no arquivo. O Ato Conjunto de 29/05 com `origem: pdf+ocr` (com tesseract instalado) ou `falhou` com "tesseract nao instalado" (sem ele). Depois: `rm -rf /tmp/claude-1000/dados-smoke`.

- [ ] **Step 6: Commit**

```bash
git add scripts/ler_textos.py tests/test_ler_textos.py
git commit -m "feat: raia de leitura ler_textos.py (HTML, PDF, OCR, anexos) com status em dados/leituras.json"
```

---

### Task 6: Lacuna com texto integral + espera pela leitura; brief da análise

**Files:**
- Modify: `scripts/lacuna_analise.py`
- Modify: `scripts/analise_brief.md` (seção "Leia o texto completo antes de classificar")
- Test: `tests/test_lacuna_analise.py` (classe nova `TestTextoNaLacuna`)

**Interfaces:**
- Consumes: `textos.le`, `textos.MAX_TENTATIVAS`, `textos.DIAS_SEM_LEITURA`. Schema de `dados/leituras.json` (Task 5).
- Produces:
  - `lacuna(raiz, hoje)` passa a devolver também `"aguardando_leitura": [{"chave", "fonte", "titulo", "status"}]`. Esses itens **não** entram em `"itens"`, então `fechar_analise.py` não os marca.
  - Cada item de `"itens"` ganha `texto` (até `TETO_LACUNA = 60000`), `texto_chars`, `texto_truncado`, `texto_arquivo` (`"dados/textos/<chave>.txt"` ou `None`), `texto_origem` e, quando aplicável, `leitura: {"status", "erro", "anexos_falhos"}`.
  - `lacuna_analise.aguardando_leitura(item: dict, meta: dict | None, tem_texto: bool, hoje: str) -> bool`

- [ ] **Step 1: Write the failing test**

Acrescente a `tests/test_lacuna_analise.py` (os imports `json`, `tempfile`, `Path` e o `sys.path` já existem no arquivo; confira e adicione o que faltar):
```python
import textos as _textos


class TestTextoNaLacuna(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        (self.raiz / "dados").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _hist(self, itens, leituras=None):
        (self.raiz / "dados" / "historico.json").write_text(json.dumps(itens), "utf-8")
        if leituras is not None:
            (self.raiz / "dados" / "leituras.json").write_text(json.dumps(leituras), "utf-8")

    def _it(self, fonte="RFB - Noticias 2026", pv="2026-10-01", **kw):
        return {"titulo": "t", "url": "u", "fonte": fonte, "primeira_vez": pv, **kw}

    def test_texto_do_arquivo_entra_no_item(self):
        self._hist({"k1": self._it()}, {"k1": {"status": "lido", "origem": "pdf+ocr"}})
        _textos.grava(self.raiz / "dados", "k1", "CORPO")
        it = lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"][0]
        self.assertEqual((it["texto"], it["texto_origem"], it["texto_truncado"]),
                         ("CORPO", "pdf+ocr", False))
        self.assertEqual(it["texto_arquivo"], "dados/textos/k1.txt")

    def test_texto_grande_vem_truncado_com_arquivo(self):
        self._hist({"k1": self._it()}, {"k1": {"status": "lido", "origem": "pdf"}})
        _textos.grava(self.raiz / "dados", "k1", "a" * 965_000)
        it = lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"][0]
        self.assertEqual(len(it["texto"]), lacuna_analise.TETO_LACUNA)
        self.assertTrue(it["texto_truncado"])
        self.assertEqual(it["texto_chars"], 965_000)

    def test_texto_legado_do_historico_ainda_vale(self):
        self._hist({"k1": self._it(fonte="DOU DO1", texto="legado")})
        it = lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"][0]
        self.assertEqual(it["texto"], "legado")
        self.assertIsNone(it["texto_arquivo"])

    def test_sem_tentativa_recente_aguarda(self):
        self._hist({"k1": self._it()}, {})
        lac = lacuna_analise.lacuna(self.raiz, "2026-10-01")
        self.assertEqual(lac["itens"], [])
        self.assertEqual(lac["aguardando_leitura"][0]["chave"], "k1")

    def test_falhou_aguarda(self):
        self._hist({"k1": self._it()}, {"k1": {"status": "falhou", "tentativas": 1, "erro": "HTTP 503"}})
        self.assertEqual(lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"], [])

    def test_desistiu_libera_com_motivo(self):
        self._hist({"k1": self._it()}, {"k1": {"status": "desistiu", "tentativas": 4, "erro": "HTTP 503"}})
        it = lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"][0]
        self.assertEqual(it["texto"], "")
        self.assertEqual(it["leitura"]["status"], "desistiu")
        self.assertEqual(it["leitura"]["erro"], "HTTP 503")

    def test_libera_depois_de_tres_dias_sem_leitura(self):
        self._hist({"k1": self._it(pv="2026-09-27")}, {})
        lac = lacuna_analise.lacuna(self.raiz, "2026-10-01")
        self.assertEqual([i["chave"] for i in lac["itens"]], ["k1"])
        self.assertEqual(lac["aguardando_leitura"], [])

    def test_dou_sem_texto_nao_aguarda(self):
        self._hist({"k1": self._it(fonte="DOU DO1")}, {})
        self.assertEqual(len(lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"]), 1)

    def test_parcial_tem_texto_e_avisa_anexo_que_falhou(self):
        self._hist({"k1": self._it()}, {"k1": {"status": "parcial", "origem": "html",
                    "anexos_falhos": [{"url": "a.pdf", "erro": "HTTP 404"}]}})
        _textos.grava(self.raiz / "dados", "k1", "CORPO")
        it = lacuna_analise.lacuna(self.raiz, "2026-10-01")["itens"][0]
        self.assertEqual(it["leitura"]["anexos_falhos"][0]["url"], "a.pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_lacuna_analise.TestTextoNaLacuna -v`
Expected: FAIL (`KeyError: 'aguardando_leitura'`, `AttributeError: TETO_LACUNA` e similares)

- [ ] **Step 3: Write minimal implementation**

Em `scripts/lacuna_analise.py`, depois dos imports:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos

# Texto que vai inline na lacuna. Acima disto o item traz texto_truncado e
# texto_arquivo, e o brief manda ler o arquivo (o Regulamento do IBS tem
# ~965 mil caracteres; inline estouraria o contexto da analise).
TETO_LACUNA = 60000
```
Funções novas (antes de `lacuna`):
```python
def _leituras(raiz):
    p = raiz / "dados" / "leituras.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def aguardando_leitura(item, meta, tem_texto, hoje):
    """A analise espera a raia de leitura, para nao ver sem texto um item que
    so' nao foi lido ainda (OCR na fila, site fora do ar por um ciclo).

    Nunca espera: item com texto, item do DOU (texto vem do INLABS) e item
    em que a leitura desistiu. Rede de seguranca: passados DIAS_SEM_LEITURA
    dias, libera de qualquer jeito — raia parada nao pode travar a analise.
    """
    if tem_texto or (item.get("fonte") or "").startswith("DOU"):
        return False
    if meta and meta.get("status") == "desistiu":
        return False
    try:
        dias = (datetime.date.fromisoformat(hoje)
                - datetime.date.fromisoformat(item["primeira_vez"])).days
    except (KeyError, ValueError):
        return False
    return dias < textos.DIAS_SEM_LEITURA


def _anexa_texto(dados, item, meta):
    k = item["chave"]
    t = textos.le(dados, k)
    item["texto_arquivo"] = f"dados/textos/{k}.txt" if t is not None else None
    if t is None:
        t = item.get("texto") or ""
    item["texto"] = t[:TETO_LACUNA]
    item["texto_chars"] = len(t)
    item["texto_truncado"] = len(t) > TETO_LACUNA
    item["texto_origem"] = (meta or {}).get("origem") or ("coleta" if t else None)
    if meta and (not t or meta.get("anexos_falhos")):
        item["leitura"] = {"status": meta.get("status"), "erro": meta.get("erro"),
                           "anexos_falhos": meta.get("anexos_falhos", [])}
    return bool(t)
```
Em `lacuna()`:
```python
def lacuna(raiz, hoje=None):
    hoje = hoje or datetime.date.today().isoformat()
    leituras = _leituras(raiz)
    itens, aguardando = [], []
    for i in itens_pendentes(raiz, hoje):
        meta = leituras.get(i["chave"])
        tem = _anexa_texto(raiz / "dados", i, meta)
        if aguardando_leitura(i, meta, tem, hoje):
            aguardando.append({"chave": i["chave"], "fonte": i.get("fonte"),
                               "titulo": i.get("titulo"),
                               "status": (meta or {}).get("status", "nao_tentado")})
        else:
            itens.append(i)
    return {
        "ate": hoje,
        "turno": turno_atual(),
        "ultima_analise": ultima_analise(raiz),
        "dados_de_hoje_disponiveis": hoje in dados_disponiveis(raiz),
        "dias_com_dados_na_janela": sorted({i["primeira_vez"] for i in itens}),
        "itens": itens,
        "aguardando_leitura": aguardando,
    }
```
Atualize a docstring do módulo com um parágrafo:
```
Itens ainda nao lidos pela raia de leitura (ler_textos.py) ficam de fora por
ate' textos.DIAS_SEM_LEITURA dias e aparecem em "aguardando_leitura"; como nao
estao em "itens", fechar_analise.py nao os marca e eles voltam no proximo ciclo.
```

Em `scripts/analise_brief.md`, substitua o bloco que vai de "Cada item de `itens` (no arquivo de lacuna) pode trazer um campo `texto`" até o fim da lista "Não gaste espaço..." por:
```markdown
Cada item de `itens` (no arquivo de lacuna) traz o texto integral da
publicação, já extraído pela coleta ou pela raia de leitura (HTML, PDF, PDF
escaneado via OCR e anexos linkados na página). Você não precisa (e não deve)
sair buscando na web o que já está ali. Campos:

- `texto`: o texto, até 60.000 caracteres.
- `texto_truncado` / `texto_chars` / `texto_arquivo`: se `texto_truncado` for
  `true`, o texto inteiro está em `texto_arquivo` (caminho no repositório). Leia o
  arquivo com a ferramenta de leitura antes de classificar. Para documentos muito
  longos (ex.: Regulamento do IBS), leia o sumário e as partes relevantes ao
  achado, e diga na análise quais partes leu.
- `texto_origem`: `html`, `pdf`, `pdf+ocr`, `coleta` (o coletor já trouxe),
  `inlabs` (DOU) ou `coleta_cortada` (DOU antigo, cortado em 20.000 caracteres).
  Em `pdf+ocr`, o texto saiu de reconhecimento óptico: um número ou caractere
  isolado pode estar errado. Ao citar prazo, valor ou número de artigo vindo
  de OCR, confira se faz sentido no contexto.
- Anexos aparecem dentro do `texto`, depois de uma linha `===== ANEXO: <url> =====`.
- `leitura`: só aparece quando a leitura falhou ou ficou parcial (`status`,
  `erro`, `anexos_falhos`).

Regras:

- **Se `texto` está preenchido** (e você leu o arquivo, quando truncado):
  marque `[VERIFICADO LITERAL]`. Em `pdf+ocr`, acrescente " (OCR)" dentro da
  marca: `[VERIFICADO LITERAL (OCR)]`.
- **Se `texto` está vazio** (a leitura desistiu, e o motivo está em `leitura.erro`)
  e você precisou buscar na web: marque `[PESQUISA]` e diga, em uma frase, que a
  leitura veio de cobertura de terceiros, não do texto oficial.
- **`aguardando_leitura`** (no topo da lacuna) lista itens que ainda vão ser
  lidos. Não os analise agora: eles voltam no próximo ciclo, já com texto. Se
  houver algum, registre a quantidade em uma frase na Nota sobre a coleta.
- Não gaste espaço da análise explicando *por que* um item não tinha
  `texto`. Isso é assunto da Nota sobre a coleta (curta, no fim), não do
  corpo do achado.
```
E, em "Marcadores de proveniência", acrescente depois do item `[VERIFICADO LITERAL]`:
```markdown
- `` `[VERIFICADO LITERAL (OCR)]` `` — idem, mas o texto veio de OCR de PDF
  escaneado (`texto_origem: "pdf+ocr"`).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_lacuna_analise -v && python3 -m unittest discover -s tests -v`
Expected: PASS. Os testes antigos de `test_lacuna_analise` não criam `leituras.json`. Se algum falhar porque o item dele agora "aguarda leitura" (fonte web, sem texto, `primeira_vez` recente), ajuste o teste: dê a ele `fonte="DOU DO1"` ou um `leituras.json` com `{"status": "desistiu"}`. Não mude a regra.

- [ ] **Step 5: Commit**

```bash
git add scripts/lacuna_analise.py scripts/analise_brief.md tests/test_lacuna_analise.py
git commit -m "feat: lacuna leva texto integral e espera a raia de leitura; brief com regras de OCR e arquivo"
```

---

### Task 7: Coleta sem extração de texto; RFB só com notícias

**Files:**
- Delete: `scripts/portais/cgibs.py`, `tests/test_portal_cgibs.py`
- Create: `scripts/portais/govbr.py`
- Modify: `scripts/portais/base.py` (remove `extrai_texto` e o laço que o chama em `coletar`; adiciona `_registro_vazio`)
- Modify: `scripts/portais/registro.py`
- Modify: `tests/test_portais_base.py`
- Test: `tests/test_portais_fontes.py` (novo; classe `TestGovBr`)

**Interfaces:**
- Produces:
  - `Portal._registro_vazio(self) -> dict` com `{"fonte", "url", "metodo": None, "http_status": None, "erro": None, "erro_browser": None, "total": 0, "itens": []}` (usado também pela Task 8)
  - `govbr.GovBrNoticiasPortal(Portal)`, com `precisa_js = False` e `filtro_relevancia` restrito a notícias
  - Os 8 portais CGIBS viram `Portal(...)` puro (`precisa_js` padrão `True`)

- [ ] **Step 1: Write the failing test**

`tests/test_portais_fontes.py`:
```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from portais.govbr import GovBrNoticiasPortal

NOT26 = "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026"


class TestGovBr(unittest.TestCase):
    def setUp(self):
        self.p = GovBrNoticiasPortal("RFB - Noticias 2026", NOT26)

    def test_noticia_da_reforma_passa(self):
        self.assertTrue(self.p.filtro_relevancia(
            "Receita Federal atualiza o balanco de opcao pelo Simples Nacional e IBS",
            NOT26 + "/setembro/receita-federal-atualiza-o-balanco-de-solicitacoes-de-opcao"))

    def test_noticia_fora_da_listagem_tambem_passa(self):
        p = GovBrNoticiasPortal("RFB - Reforma do Consumo",
                                "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/x/noticias")
        self.assertTrue(p.filtro_relevancia(
            "Receita Federal, CGIBS e CFC alinham diretrizes da conformidade",
            "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/receita-federal-comite-gestor-do-ibs-e-cfc-alinham"))

    def test_servicos_e_menus_nao_passam(self):
        for t, u in [
            ("Escolher Regime de Apuracao de IBS e CBS",
             "https://www.gov.br/pt-br/servicos/escolher-regime-de-apuracao-de-bens-e-servicos-ibs"),
            ("Simples Nacional", "https://www8.receita.fazenda.gov.br/SimplesNacional/"),
            ("Nota Fiscal de Servico Eletronica (NFS-e)", "https://www.gov.br/nfse/pt-br"),
            ("Conformidade", "https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/paineis/conformidade"),
        ]:
            self.assertFalse(self.p.filtro_relevancia(t, u), u)

    def test_paginas_de_listagem_nao_passam(self):
        self.assertFalse(self.p.filtro_relevancia("Noticias de setembro sobre o IBS",
                                                  NOT26 + "/setembro"))
        self.assertFalse(self.p.filtro_relevancia("Noticias sobre o IBS", NOT26))

    def test_noticia_sem_termo_da_reforma_nao_passa(self):
        self.assertFalse(self.p.filtro_relevancia(
            "Receita Federal apreende mercadorias no porto de Santos",
            NOT26 + "/setembro/receita-federal-apreende-mercadorias-no-porto"))


if __name__ == "__main__":
    unittest.main()
```

Em `tests/test_portais_base.py`:
- apague a classe `TestExtraiTextoDefault` e o teste `test_extrai_texto_que_lanca_nao_derruba_coleta`;
- troque `test_cgibs_usa_a_subclasse_e_precisa_js` por:
```python
    def test_cgibs_e_portal_puro_e_precisa_js(self):
        from portais.registro import PORTAIS
        from portais.base import Portal
        cgibs = [p for p in PORTAIS if p.nome.startswith("CGIBS")]
        self.assertEqual(len(cgibs), 8)
        self.assertTrue(all(type(p) is Portal for p in cgibs))
        self.assertTrue(all(p.precisa_js for p in cgibs))
        self.assertFalse(any(hasattr(p, "extrai_texto") for p in cgibs))

    def test_rfb_usa_govbr(self):
        from portais.registro import PORTAIS
        from portais.govbr import GovBrNoticiasPortal
        rfb = [p for p in PORTAIS if p.nome.startswith("RFB")]
        self.assertEqual(len(rfb), 2)
        self.assertTrue(all(isinstance(p, GovBrNoticiasPortal) for p in rfb))
```
- acrescente:
```python
class TestRegistroVazio(unittest.TestCase):
    def test_formato(self):
        r = Portal("F", "https://x")._registro_vazio()
        self.assertEqual(r, {"fonte": "F", "url": "https://x", "metodo": None,
                             "http_status": None, "erro": None, "erro_browser": None,
                             "total": 0, "itens": []})
```
(confira se `Portal` já está importado no topo do arquivo; se não, `from portais.base import Portal`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_portais_fontes tests.test_portais_base -v`
Expected: FAIL (`No module named 'portais.govbr'`, `_registro_vazio` inexistente)

- [ ] **Step 3: Write minimal implementation**

`scripts/portais/govbr.py`:
```python
#!/usr/bin/env python3
"""Noticias da RFB no gov.br.

A pagina de listagem traz, alem das noticias, menu, servicos
(gov.br/pt-br/servicos/...), paineis e links para outros sistemas (www8,
NFS-e). Esses links passavam no filtro global por terem "IBS", "Simples
Nacional" ou "NFS-e" no titulo e entravam como publicacao — sem ser
publicacao. Aqui so' entra noticia: caminho com /noticias/ e terminando
num slug (>= 3 hifens), nunca numa pagina de listagem (/noticias/2026,
/noticias/2026/setembro).
"""
import urllib.parse

from portais.base import Portal


class GovBrNoticiasPortal(Portal):
    precisa_js = False

    def filtro_relevancia(self, titulo, url):
        caminho = urllib.parse.urlparse(url).path.rstrip("/")
        if "/noticias/" not in caminho:
            return False
        if caminho.rsplit("/", 1)[-1].count("-") < 3:
            return False
        return super().filtro_relevancia(titulo, url)
```

Em `scripts/portais/base.py`:
- apague o método `extrai_texto` e, em `coletar`, o laço `for it in reg["itens"]: ... txt = self.extrai_texto(...)` inteiro;
- em `coletar`, troque a criação do dict `reg` por `reg = self._registro_vazio()`;
- acrescente o método:
```python
    def _registro_vazio(self):
        return {"fonte": self.nome, "url": self.url, "metodo": None,
                "http_status": None, "erro": None, "erro_browser": None,
                "total": 0, "itens": []}
```
- na docstring da classe, troque a menção a `extrai_texto()` por: "O texto integral nao e' extraido aqui: e' a raia de leitura (scripts/ler_textos.py), depois da coleta, que le cada item. Subclasses sobrescrevem filtro_relevancia() ou coletar() (fontes cujos itens nao sao links, ex.: portais/svrs.py)."
- confira com `grep -n "import" scripts/portais/base.py` se ainda há imports usados só pelo laço apagado (ex.: `sys` continua em uso por `via_*`? deixe o que estiver em uso).

`scripts/portais/registro.py`:
```python
from portais.base import Portal
from portais.govbr import GovBrNoticiasPortal

PORTAIS = [
    Portal("CGIBS - Noticias",            "https://www.cgibs.gov.br/noticias"),
    Portal("CGIBS - Resolucoes",          "https://www.cgibs.gov.br/resolucoes"),
    Portal("CGIBS - Atos Conjuntos",      "https://www.cgibs.gov.br/atos-conjuntos"),
    Portal("CGIBS - Atos Tecnicos Conj.", "https://www.cgibs.gov.br/atos-tecnicos-conjuntos"),
    Portal("CGIBS - Portarias",           "https://www.cgibs.gov.br/portarias"),
    GovBrNoticiasPortal("RFB - Noticias 2026",
           "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026"),
    GovBrNoticiasPortal("RFB - Reforma do Consumo",
           "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/reforma-tributaria-do-consumo/noticias"),
    Portal("Portal DF-e SVRS - Noticias",
           "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias",
           precisa_js=False),
    Portal("Portal NF-e - Informes/NTs",
           "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false",
           precisa_js=False),
    Portal("CGIBS - Regulamentos",        "https://www.cgibs.gov.br/regulamentos"),
    Portal("CGIBS - Leis",                "https://www.cgibs.gov.br/leis"),
    Portal("CGIBS - Relatorios",          "https://www.cgibs.gov.br/relatorios"),
]
```
(Atualize a docstring do módulo: "fonte com regra propria: uma subclasse pequena em outro modulo deste pacote + uma linha aqui". O exemplo do CGIBS sai.)

Apague `scripts/portais/cgibs.py` e `tests/test_portal_cgibs.py` com `git rm`. Os testes do extrator já vivem em `tests/test_leitura_paginas.py` (Task 2).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v && grep -rn "cgibs import\|CGIBSPortal\|extrai_texto" scripts tests`
Expected: suíte PASS. O grep não acha nada além de menções em comentários/docs (se achar código, corrija).

- [ ] **Step 5: Commit**

```bash
git rm scripts/portais/cgibs.py tests/test_portal_cgibs.py
git add scripts/portais/base.py scripts/portais/govbr.py scripts/portais/registro.py tests/test_portais_base.py tests/test_portais_fontes.py
git commit -m "refactor: coleta so' lista (texto vai para a raia de leitura); RFB so' com noticias"
```

---

### Task 8: SVRS e Portal NF-e coletando as publicações de verdade

**Files:**
- Create: `scripts/portais/svrs.py`, `scripts/portais/nfe.py`
- Modify: `scripts/portais/registro.py` (16 fontes)
- Modify: `tests/test_portais_base.py` (`test_doze_portais_na_ordem_das_fontes` → 16 nomes; `test_fontes_sem_js_sao_marcadas`)
- Test: `tests/test_portais_fontes.py` (classes `TestSVRS`, `TestNFeInformes`, `TestNFeLista`)

**Interfaces:**
- Consumes: `Portal._registro_vazio()` (Task 7), `baixar.Sessao`, `baixar.ErroDownload` (Task 4), `portais.base.monta_item`, `portais.base.RELEVANTE`, `portais.base.extrai_data`
- Produces:
  - `svrs.SVRSNoticiasPortal(nome, url)`, com `coletar(ctx, limite=None)` via HTTP: itens `{titulo, url: "<listagem>#<id>", data: ISO, texto_integral, ...monta_item}` só das `MAX_NOTICIAS = 30` primeiras, com filtro `RELEVANTE` em título **ou** corpo
  - `svrs.extrai_noticias(html) -> list[dict]` (`id`, `titulo`, `data`, `corpo`)
  - `nfe.NFeInformesPortal(nome, url)`: itens `{titulo, url: "<pagina>#<a name>", data, texto_integral}`
  - `nfe.extrai_informes(html) -> list[dict]` (`id`, `titulo`, `data`, `corpo`)
  - `nfe.NFeListaPortal(nome, url)`: itens `{titulo, url: <exibirArquivo absoluto>, ementa}`. O texto vem da raia de leitura (PDF).
  - `nfe.extrai_lista(html, base) -> list[dict]` (`titulo`, `url`, `ementa`)
  - As fontes SVRS e NF-e passam a ser lidas por HTTP com sessão. O `ctx` do navegador é ignorado.

- [ ] **Step 1: Write the failing test**

Acrescente a `tests/test_portais_fontes.py`:
```python
from unittest.mock import patch
from portais import svrs, nfe
from leitura import baixar

SVRS_HTML = """
<div class="artigo__texto"><section id="pagedlistItens">
<article class="conteudo-lista__item clearfix">
  <header><ul class="lista-categoria"><li><a class="label" href="#">Coordena&#231;&#227;o T&#233;cnica do ENCAT</a></li></ul>
  <time class="conteudo-lista__item__datahora" datetime="10/09/2026">10/09/2026</time>
  <h2 class="conteudo-lista__item__titulo"><a id="#3007" href="#">Publicada NT 2025.002 v1.30 com regras do IBS e CBS</a></h2></header>
  <p><p>A NT altera o leiaute da NF-e para o IBS.</p><p>Vigencia em 01/12/2026.</p></p>
</article>
<article class="conteudo-lista__item clearfix">
  <header><time class="conteudo-lista__item__datahora" datetime="09/09/2026">09/09/2026</time>
  <h2 class="conteudo-lista__item__titulo"><a id="#3006" href="#">Novidade: Link para o MOC Online</a></h2></header>
  <p>Agora ha um link para o MOC no menu superior.</p>
</article>
</section></div>
"""

NFE_INFORMES_HTML = """
<div id="conteudoDinamico"><div class="divTituloPrincipal">Avisos</div>
<div class="divInforme"><a name="1490"></a><p>04/09/2026 -
   Publicado Informe Tecnico 2025.002 sobre o IBS e a CBS </p>Foi publicado&nbsp;Informe Tecnico com regras do IBS.<br /><br />Assinado por: Coordenacao Tecnica do ENCAT</div>
<div class="divInforme"><a name="1489"></a><p>03/09/2026 - Atualizada a tabela de NCM</p>Tabela de NCM atualizada.</div>
</div>
"""

NFE_LISTA_HTML = """
<div class="indentacaoConteudo"><p><a target="_blank" href="exibirArquivo.aspx?conteudo=esD6zF5PwcE="><span class="tituloConteudo">Ato Conjunto RFB/CGIBS n&#186; 4, de 30 de julho de 2026</span></a><br />Estabelece as datas de inicio da obrigatoriedade dos documentos fiscais do IBS<br /></p>
<p><a target="_blank" href="exibirArquivo.aspx?conteudo=5FAxxHGS5Ic="><span class="tituloConteudo">Ato Conjunto RFB/CGIBS n&#186; 1, de 22 de dezembro de 2025</span></a><br />Dispoe sobre as obrigacoes acessorias do IBS e da CBS em 2026<br /></p></div>
"""

SVRS_URL = "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias"
NFE_URL = "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false"
LISTA_URL = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=ECxaPvwFHQE="


def _sessao_com(html):
    s = patch.object(baixar.Sessao, "baixa_html", return_value=(html, "u"))
    return s


class TestSVRS(unittest.TestCase):
    def test_extrai_noticias_inline(self):
        ns = svrs.extrai_noticias(SVRS_HTML)
        self.assertEqual([n["id"] for n in ns], ["3007", "3006"])
        self.assertEqual(ns[0]["data"], "2026-09-10")
        self.assertIn("Publicada NT 2025.002", ns[0]["titulo"])
        self.assertIn("Vigencia em 01/12/2026", ns[0]["corpo"])
        self.assertNotIn("ENCAT", ns[0]["titulo"])

    def test_coletar_filtra_e_traz_texto_integral(self):
        p = svrs.SVRSNoticiasPortal("Portal DF-e SVRS - Noticias", SVRS_URL)
        with _sessao_com(SVRS_HTML):
            reg = p.coletar(None)
        self.assertEqual(reg["metodo"], "http")
        self.assertEqual(reg["total"], 1)                       # MOC Online nao e' da reforma
        it = reg["itens"][0]
        self.assertEqual(it["url"], SVRS_URL + "#3007")
        self.assertEqual(it["data"], "2026-09-10")
        self.assertIn("leiaute da NF-e para o IBS", it["texto_integral"])

    def test_limite_de_noticias(self):
        bloco = SVRS_HTML.split("<article")[1].split("</article>")[0]
        muitas = "".join(f'<article{bloco.replace("#3007", "#" + str(i))}</article>' for i in range(50))
        self.assertEqual(len(svrs.extrai_noticias(muitas)), 50)
        p = svrs.SVRSNoticiasPortal("S", SVRS_URL)
        with _sessao_com(muitas):
            self.assertEqual(p.coletar(None)["total"], svrs.MAX_NOTICIAS)

    def test_falha_de_rede_vira_erro_sem_lancar(self):
        p = svrs.SVRSNoticiasPortal("S", SVRS_URL)
        with patch.object(baixar.Sessao, "baixa_html", side_effect=baixar.ErroDownload("HTTP 503")):
            reg = p.coletar(None)
        self.assertIsNone(reg["metodo"])
        self.assertIn("HTTP 503", reg["erro"])


class TestNFeInformes(unittest.TestCase):
    def test_extrai_informes(self):
        ns = nfe.extrai_informes(NFE_INFORMES_HTML)
        self.assertEqual([n["id"] for n in ns], ["1490", "1489"])
        self.assertEqual(ns[0]["data"], "2026-09-04")
        self.assertEqual(ns[0]["titulo"], "Publicado Informe Tecnico 2025.002 sobre o IBS e a CBS")
        self.assertIn("Assinado por", ns[0]["corpo"])

    def test_coletar(self):
        p = nfe.NFeInformesPortal("Portal NF-e - Informes/NTs", NFE_URL)
        with _sessao_com(NFE_INFORMES_HTML):
            reg = p.coletar(None)
        self.assertEqual(reg["total"], 1)                       # NCM nao e' da reforma
        it = reg["itens"][0]
        self.assertEqual(it["url"], NFE_URL + "#1490")
        self.assertIn("regras do IBS", it["texto_integral"])


class TestNFeLista(unittest.TestCase):
    def test_extrai_lista(self):
        ns = nfe.extrai_lista(NFE_LISTA_HTML, LISTA_URL)
        self.assertEqual(ns[0]["url"],
                         "https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=esD6zF5PwcE=")
        self.assertEqual(ns[0]["titulo"], "Ato Conjunto RFB/CGIBS nº 4, de 30 de julho de 2026")
        self.assertIn("datas de inicio", ns[0]["ementa"])

    def test_coletar_sem_texto_integral(self):
        p = nfe.NFeListaPortal("Portal NF-e - Atos RFB/CGIBS", LISTA_URL)
        with _sessao_com(NFE_LISTA_HTML):
            reg = p.coletar(None)
        self.assertEqual(reg["total"], 2)
        self.assertNotIn("texto_integral", reg["itens"][0])
        self.assertEqual(reg["itens"][0]["data"], "2026-07-30")
        self.assertIn("ementa", reg["itens"][0])
```

Em `tests/test_portais_base.py`, troque a lista esperada de `test_doze_portais_na_ordem_das_fontes` (renomeie para `test_portais_na_ordem`) por:
```python
            "CGIBS - Noticias",
            "CGIBS - Resolucoes",
            "CGIBS - Atos Conjuntos",
            "CGIBS - Atos Tecnicos Conj.",
            "CGIBS - Portarias",
            "RFB - Noticias 2026",
            "RFB - Reforma do Consumo",
            "Portal DF-e SVRS - Noticias",
            "Portal NF-e - Informes/NTs",
            "Portal NF-e - Atos RFB/CGIBS",
            "Portal NF-e - Atos Tecnicos RFB/CGIBS",
            "Portal NF-e - Notas Tecnicas",
            "Portal NF-e - Informes Tecnicos",
            "CGIBS - Regulamentos",
            "CGIBS - Leis",
            "CGIBS - Relatorios",
```
e ajuste `test_fontes_sem_js_sao_marcadas` para o conjunto esperado: as 2 RFB, a SVRS e as 5 do Portal NF-e.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_portais_fontes -v`
Expected: FAIL com `ImportError: cannot import name 'svrs'`

- [ ] **Step 3: Write minimal implementation**

`scripts/portais/svrs.py`:
```python
#!/usr/bin/env python3
"""Portal DF-e SVRS — noticias.

As noticias nao sao links: ficam inteiras na propria listagem, cada uma num
<article class="conteudo-lista__item"> com titulo <a href="#">. O coletor
generico de links pegava so' rotulos de categoria e URLs soltas no corpo;
as noticias em si nunca entravam. Aqui cada <article> vira um item, com o
corpo como texto_integral (grava_resultado o leva para dados/textos/).

A pagina traz o historico inteiro (paginacao no navegador); so' as
MAX_NOTICIAS primeiras (mais recentes) sao consideradas.
"""
import re
from html.parser import HTMLParser

from leitura.baixar import ErroDownload, Sessao
from portais.base import Portal, RELEVANTE, extrai_data, monta_item

MAX_NOTICIAS = 30


class _Noticias(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.noticias = []
        self._art = 0          # profundidade de <article>
        self._cab = False
        self._em = None        # "time" | "titulo" | None
        self._atual = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article":
            if self._art == 0 and "conteudo-lista__item" in (a.get("class") or ""):
                self._atual = {"id": "", "titulo": [], "data": [], "corpo": []}
            if self._atual is not None:
                self._art += 1
            return
        if self._atual is None:
            return
        if tag == "header":
            self._cab = True
        elif tag == "time":
            self._em = "data"
        elif tag == "a" and self._cab and a.get("id"):
            self._atual["id"] = a["id"].lstrip("#")
            self._em = "titulo"
        elif tag in ("p", "br", "li") and not self._cab:
            self._atual["corpo"].append("\n")

    def handle_endtag(self, tag):
        if self._atual is None:
            return
        if tag == "article":
            self._art -= 1
            if self._art == 0:
                n = self._atual
                self.noticias.append({
                    "id": n["id"],
                    "titulo": _limpa("".join(n["titulo"])),
                    "data": extrai_data("".join(n["data"])),
                    "corpo": _limpa_corpo("".join(n["corpo"]))})
                self._atual = None
        elif tag == "header":
            self._cab = False
        elif tag in ("time", "a"):
            self._em = None

    def handle_data(self, data):
        if self._atual is None:
            return
        if self._em in ("titulo", "data"):
            self._atual[self._em].append(data)
        elif not self._cab:
            self._atual["corpo"].append(data)


def _limpa(t):
    return re.sub(r"\s+", " ", t).strip()


def _limpa_corpo(t):
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    return re.sub(r"\n\s*\n\s*(\n\s*)*", "\n\n", t).strip()


def extrai_noticias(html):
    p = _Noticias()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return [n for n in p.noticias if n["titulo"]]


class SVRSNoticiasPortal(Portal):
    precisa_js = False

    def coletar(self, ctx, limite=None):
        reg = self._registro_vazio()
        try:
            html, _ = Sessao().baixa_html(self.url)
        except ErroDownload as e:
            reg["erro"] = f"http: {e}"
            return reg
        reg["metodo"], reg["http_status"] = "http", 200
        for n in extrai_noticias(html)[:MAX_NOTICIAS]:
            if not (RELEVANTE.search(n["titulo"]) or RELEVANTE.search(n["corpo"])):
                continue
            it = monta_item(n["titulo"], f"{self.url}#{n['id']}")
            it["data"] = n["data"] or it["data"]
            it["texto_integral"] = f"{n['titulo']}\n\n{n['corpo']}"
            reg["itens"].append(it)
        reg["total"] = len(reg["itens"])
        return reg
```

`scripts/portais/nfe.py`:
```python
#!/usr/bin/env python3
"""Portal Nacional da NF-e (nfe.fazenda.gov.br).

Duas formas de publicacao, nenhuma delas um link comum:
  * informe.aspx — os avisos ficam inline, cada um num <div class="divInforme">
    (<a name="N"> + <p>DD/MM/AAAA - titulo</p> + corpo). O coletor generico
    pegava o menu do site em vez deles.
  * listaConteudo.aspx?tipoConteudo=... — Atos RFB/CGIBS, Atos Tecnicos, NTs,
    Informes Tecnicos: <span class="tituloConteudo"> dentro de um link
    exibirArquivo.aspx (o PDF), seguido da ementa. O PDF e' lido pela raia
    de leitura (scripts/ler_textos.py).

O site exige cookie de sessao (sem ele, 302 em loop): tudo via
leitura.baixar.Sessao.
"""
import re
import urllib.parse
from html.parser import HTMLParser

from leitura.baixar import ErroDownload, Sessao
from portais.base import Portal, RELEVANTE, extrai_data, monta_item


def _limpa(t):
    return re.sub(r"\s+", " ", t or "").strip()


class _Informes(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.informes, self._atual, self._prof, self._no_p = [], None, 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            if self._atual is None and "divInforme" in (a.get("class") or "").split():
                self._atual, self._prof = {"id": "", "cab": [], "corpo": []}, 1
            elif self._atual is not None:
                self._prof += 1
        elif self._atual is not None:
            if tag == "a" and a.get("name") and not self._atual["id"]:
                self._atual["id"] = a["name"]
            elif tag == "p" and not self._atual["cab"]:
                self._no_p = True
            elif tag == "br":
                self._atual["corpo"].append("\n")

    def handle_endtag(self, tag):
        if self._atual is None:
            return
        if tag == "p":
            self._no_p = False
        elif tag == "div":
            self._prof -= 1
            if self._prof == 0:
                cab = _limpa("".join(self._atual["cab"]))
                m = re.match(r"(\d{2}/\d{2}/\d{4})\s*-\s*(.*)", cab)
                self.informes.append({
                    "id": self._atual["id"],
                    "data": extrai_data(m.group(1)) if m else None,
                    "titulo": m.group(2) if m else cab,
                    "corpo": re.sub(r"\n\s*\n\s*(\n\s*)*", "\n\n",
                                    re.sub(r"[ \t]+", " ", "".join(self._atual["corpo"]))).strip()})
                self._atual = None

    def handle_data(self, data):
        if self._atual is not None:
            self._atual["cab" if self._no_p else "corpo"].append(data)


def extrai_informes(html):
    p = _Informes()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return [i for i in p.informes if i["titulo"]]


class _Lista(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.itens = base, []
        self._href, self._tit, self._em_tit, self._em_p = None, [], False, False
        self._ementa = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "p":
            self._fecha()
            self._em_p = True
        elif tag == "a" and "exibirarquivo.aspx" in (a.get("href") or "").lower():
            self._fecha()
            self._href = urllib.parse.urljoin(self.base, a["href"])
        elif tag == "span" and "tituloConteudo" in (a.get("class") or ""):
            self._em_tit = True

    def handle_endtag(self, tag):
        if tag == "span":
            self._em_tit = False
        elif tag == "p":
            self._fecha()
            self._em_p = False

    def handle_data(self, data):
        if self._em_tit:
            self._tit.append(data)
        elif self._href:
            self._ementa.append(data)

    def _fecha(self):
        if self._href and _limpa("".join(self._tit)):
            self.itens.append({"titulo": _limpa("".join(self._tit)), "url": self._href,
                               "ementa": _limpa("".join(self._ementa))})
        self._href, self._tit, self._ementa = None, [], []

    def close(self):
        super().close()
        self._fecha()


def extrai_lista(html, base):
    p = _Lista(base)
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    return p.itens


class _NFePortal(Portal):
    precisa_js = False

    def _html(self, reg):
        try:
            html, _ = Sessao().baixa_html(self.url)
        except ErroDownload as e:
            reg["erro"] = f"http: {e}"
            return None
        reg["metodo"], reg["http_status"] = "http", 200
        return html


class NFeInformesPortal(_NFePortal):
    def coletar(self, ctx, limite=None):
        reg = self._registro_vazio()
        html = self._html(reg)
        if html is None:
            return reg
        for n in extrai_informes(html):
            if not (RELEVANTE.search(n["titulo"]) or RELEVANTE.search(n["corpo"])):
                continue
            it = monta_item(n["titulo"], f"{self.url}#{n['id']}")
            it["data"] = n["data"] or it["data"]
            it["texto_integral"] = f"{n['titulo']}\n\n{n['corpo']}"
            reg["itens"].append(it)
        reg["total"] = len(reg["itens"])
        return reg


class NFeListaPortal(_NFePortal):
    def coletar(self, ctx, limite=None):
        reg = self._registro_vazio()
        html = self._html(reg)
        if html is None:
            return reg
        for n in extrai_lista(html, self.url):
            if not (RELEVANTE.search(n["titulo"]) or RELEVANTE.search(n["ementa"])):
                continue
            it = monta_item(n["titulo"], n["url"])
            it["ementa"] = n["ementa"]
            reg["itens"].append(it)
        reg["total"] = len(reg["itens"])
        return reg
```

Atenção ao teste `test_coletar` de `TestNFeInformes`: o título "Atualizada a tabela de NCM" e o corpo "Tabela de NCM atualizada." não casam com `RELEVANTE`. Confirme isso rodando o regex. Se casar, ajuste o fixture, não o filtro.

`scripts/portais/registro.py`: troque as duas linhas de SVRS e NF-e e acrescente as 4 listas logo depois:
```python
from portais.nfe import NFeInformesPortal, NFeListaPortal
from portais.svrs import SVRSNoticiasPortal

LISTA_NFE = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo="
...
    SVRSNoticiasPortal("Portal DF-e SVRS - Noticias",
           "https://dfe-portal.svrs.rs.gov.br/Nfe/Noticias"),
    NFeInformesPortal("Portal NF-e - Informes/NTs",
           "https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false"),
    NFeListaPortal("Portal NF-e - Atos RFB/CGIBS",          LISTA_NFE + "ECxaPvwFHQE="),
    NFeListaPortal("Portal NF-e - Atos Tecnicos RFB/CGIBS", LISTA_NFE + "hXHrw4cadF8="),
    NFeListaPortal("Portal NF-e - Notas Tecnicas",          LISTA_NFE + "04BIflQt1aY="),
    NFeListaPortal("Portal NF-e - Informes Tecnicos",       LISTA_NFE + "hXzemuyNHW4="),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: Smoke test contra os sites reais (só leitura, nada gravado)**

```bash
.venv/bin/python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts")
from portais.registro import PORTAIS
for p in PORTAIS:
    if p.nome.startswith(("Portal", "RFB")) and not p.precisa_js:
        try:
            r = p.coletar(None) if "Portal" in p.nome else None
        except Exception as e:
            print(p.nome, "EXCECAO", e); continue
        if r:
            print(f"{p.nome:40} metodo={r['metodo']} itens={r['total']} erro={r['erro']}")
            for it in r["itens"][:3]:
                print("    ", it.get("data"), it["titulo"][:70], "|", it["url"][-40:],
                      "| texto" if it.get("texto_integral") else "")
EOF
```
Expected: SVRS com notícias reais (datas de set/2026, `#<id>`, "texto"); NF-e Informes com avisos datados e "texto"; as 4 listas com `exibirArquivo.aspx` e títulos de atos ou NTs. Se alguma vier com 0 itens, inspecione o HTML real (`baixar.Sessao().baixa_html(url)`) e ajuste o parser e o fixture do teste juntos.

- [ ] **Step 6: Commit**

```bash
git add scripts/portais/svrs.py scripts/portais/nfe.py scripts/portais/registro.py tests/test_portais_base.py tests/test_portais_fontes.py
git commit -m "feat: SVRS e Portal NF-e coletam as publicacoes de verdade (noticias/informes inline, atos e NTs)"
```

---

### Task 9: Semeadura das fontes novas

**Files:**
- Create: `scripts/semear_analisados.py`
- Test: `tests/test_semear_analisados.py`

**Interfaces:**
- Consumes: `dados/historico.json`, `dados/analisados.json` (`{"chaves": [...]}`, o formato que `fechar_analise.py` grava)
- Produces:
  - `semear_analisados.candidatas(raiz: Path, fontes: set[str], hoje: str, dias: int) -> list[str]`: chaves dessas fontes ainda não analisadas, com `data` anterior a `hoje - dias` ou sem data
  - CLI: `python3 scripts/semear_analisados.py --fonte F [--fonte F2 ...] [--dias 30] [--aplicar]`. Sem `--aplicar`, só lista (dry run).

- [ ] **Step 1: Write the failing test**

`tests/test_semear_analisados.py`:
```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import semear_analisados as s


class TestSemear(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        (self.raiz / "dados").mkdir()
        h = {
            "velha": {"fonte": "Portal NF-e - Notas Tecnicas", "data": "2019-05-01"},
            "sem_data": {"fonte": "Portal NF-e - Notas Tecnicas", "data": None},
            "recente": {"fonte": "Portal NF-e - Notas Tecnicas", "data": "2026-09-20"},
            "outra_fonte": {"fonte": "CGIBS - Noticias", "data": "2019-01-01"},
            "ja_feita": {"fonte": "Portal NF-e - Notas Tecnicas", "data": "2019-01-01"},
        }
        (self.raiz / "dados" / "historico.json").write_text(json.dumps(h))
        (self.raiz / "dados" / "analisados.json").write_text(json.dumps({"chaves": ["ja_feita"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_candidatas(self):
        c = s.candidatas(self.raiz, {"Portal NF-e - Notas Tecnicas"}, "2026-10-01", 30)
        self.assertEqual(sorted(c), ["sem_data", "velha"])

    def test_aplicar_acrescenta_sem_apagar(self):
        s.main(["--fonte", "Portal NF-e - Notas Tecnicas", "--aplicar"],
               raiz=self.raiz, hoje="2026-10-01")
        feitas = json.loads((self.raiz / "dados" / "analisados.json").read_text())["chaves"]
        self.assertEqual(feitas, sorted(["ja_feita", "sem_data", "velha"]))

    def test_sem_aplicar_nao_grava(self):
        s.main(["--fonte", "Portal NF-e - Notas Tecnicas"], raiz=self.raiz, hoje="2026-10-01")
        feitas = json.loads((self.raiz / "dados" / "analisados.json").read_text())["chaves"]
        self.assertEqual(feitas, ["ja_feita"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_semear_analisados -v`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`scripts/semear_analisados.py`:
```python
#!/usr/bin/env python3
"""Marca como analisados os itens antigos de fontes recem-incluidas.

Uma fonte nova (ex.: listas de NTs do Portal NF-e) traz anos de historico na
primeira coleta. Sem isto, tudo cairia de uma vez na proxima analise. Os
itens semeados continuam no historico e continuam sendo lidos pela raia de
leitura — so' nao vao para a analise. Itens com data nos ultimos --dias
ficam de fora da semeadura e sao analisados normalmente.

Uso (rode sem --aplicar primeiro e confira a lista):
  python3 scripts/semear_analisados.py --fonte "Portal NF-e - Notas Tecnicas" [--fonte ...] [--dias 30] [--aplicar]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _le(p, padrao):
    return json.loads(p.read_text("utf-8")) if p.exists() else padrao


def candidatas(raiz, fontes, hoje, dias):
    hist = _le(raiz / "dados" / "historico.json", {})
    feitas = set(_le(raiz / "dados" / "analisados.json", {}).get("chaves", []))
    corte = (datetime.date.fromisoformat(hoje) - datetime.timedelta(days=dias)).isoformat()
    return [k for k, it in hist.items()
            if it.get("fonte") in fontes and k not in feitas
            and (not it.get("data") or it["data"] < corte)]


def main(argv=None, raiz=RAIZ, hoje=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", action="append", required=True)
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args(argv)
    hoje = hoje or datetime.date.today().isoformat()
    ks = candidatas(raiz, set(a.fonte), hoje, a.dias)
    hist = _le(raiz / "dados" / "historico.json", {})
    for k in sorted(ks, key=lambda k: hist[k].get("data") or ""):
        print(f"{hist[k].get('data') or '----------'}  {hist[k].get('fonte')[:30]:30}  "
              f"{(hist[k].get('titulo') or '')[:80]}")
    print(f"{len(ks)} item(ns) {'marcados' if a.aplicar else 'seriam marcados (use --aplicar)'}",
          file=sys.stderr)
    if a.aplicar and ks:
        arq = raiz / "dados" / "analisados.json"
        feitas = set(_le(arq, {}).get("chaves", []))
        arq.write_text(json.dumps({"chaves": sorted(feitas | set(ks))}, ensure_ascii=False, indent=1),
                       "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
Confira em `scripts/fechar_analise.py:88-90` o formato exato de escrita (`_grava_json`: indent, ensure_ascii) e use o mesmo, para o diff de `analisados.json` não mudar de formato.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_semear_analisados -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/semear_analisados.py tests/test_semear_analisados.py
git commit -m "feat: semear_analisados.py evita enxurrada na primeira coleta de fonte nova"
```

---

### Task 10: Produção — dependências, ciclo, systemd, documentação

**Files:**
- Modify: `scripts/rodar_varredura.sh`
- Modify: `deploy/systemd/reforma-ciclo.service` (`TimeoutStartSec=14400`)
- Modify: `CLAUDE.md`, `docs/operacao-local.md`, `README.md` (seção "Decisões de projeto")

**Interfaces:**
- Consumes: `scripts/ler_textos.py` (Task 5), `scripts/semear_analisados.py` (Task 9)

- [ ] **Step 1: Instalar o OCR no lenovo-claude**

```bash
sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils
tesseract --list-langs | grep -x por && pdftotext -v 2>&1 | head -1
```
Expected: `por` listado e versão do pdftotext. Depois: `python3 -m unittest tests.test_leitura_pdf -v`, com `TestOCRReal` passando (não mais `skipped`).

- [ ] **Step 2: Ligar a leitura no ciclo**

`scripts/rodar_varredura.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# publicar.sh resolve sozinho conflito em docs/ (gerado); qualquer outro
# conflito aborta o rebase, deixando o checkout limpo e a falha no journal.
scripts/publicar.sh --sincronizar || exit 1
.venv/bin/python3 scripts/varredura.py
# Raia de leitura: texto integral (HTML, PDF, OCR) de tudo que ainda nao tem.
# Falha aqui nao segura a publicacao da varredura: o que nao foi lido fica
# como `falhou` em dados/leituras.json e e' tentado de novo no proximo ciclo.
.venv/bin/python3 scripts/ler_textos.py || echo "AVISO: ler_textos.py falhou (ver acima)" >&2
.venv/bin/python3 scripts/gerar_painel.py
scripts/publicar.sh "varredura $(date +%Y-%m-%d) ${TURNO:-}" dados docs
```
(`dados` já inclui `dados/textos/` e `dados/leituras.json`.)

- [ ] **Step 3: Prazo do ciclo**

Em `deploy/systemd/reforma-ciclo.service`, troque `TimeoutStartSec=7200` por `TimeoutStartSec=14400` e atualize o comentário ao lado: "4h: DOU (login até ~60 min no pior caso) + varredura (10 min) + leitura (45 min, OCR) + análise". Instale:
```bash
sudo cp deploy/systemd/reforma-ciclo.service /etc/systemd/system/ && sudo systemctl daemon-reload
systemctl show reforma-ciclo.service -p TimeoutStartUSec
```
Expected: `TimeoutStartUSec=4h`

- [ ] **Step 4: Documentação**

- `CLAUDE.md`, em "Architecture": acrescente a raia **Leitura** entre Fatos e Análise. `scripts/ler_textos.py` roda depois da varredura, só no notebook, escreve só `dados/textos/<chave>.txt` + `dados/leituras.json`, e usa poppler + tesseract do sistema. Em "Data flow", inclua o passo dela e o fato de que `lacuna_analise.py` espera a leitura por até 3 dias. Em "Os scrapers web", troque o parágrafo do `CGIBSPortal` por: as subclasses atuais (`GovBrNoticiasPortal`, `SVRSNoticiasPortal`, `NFeInformesPortal`, `NFeListaPortal`) e o fato de que nenhuma extrai texto (isso é da raia de leitura). Troque "12 fontes" por "16 fontes" onde aparecer. Em "Commands", acrescente `python3 scripts/ler_textos.py [--sem-limite] [--chave K]`, `python3 scripts/cobertura_textos.py` (Task 11) e `python3 scripts/semear_analisados.py --fonte F [--aplicar]`. Em "Gotchas", acrescente: "**Fonte cuja publicação não é link** (SVRS, informes do NF-e): o coletor genérico de links pega o menu e ninguém percebe, porque a fonte 'tem itens'. Confira se os itens são publicações, não só se a contagem é maior que zero."
- `docs/operacao-local.md`: na tabela "O quê roda onde", inclua a leitura dentro do ciclo; adicione a seção "Leitura integral (OCR)" com os pacotes apt, o orçamento de 45 min, `dados/leituras.json` para diagnóstico e `ler_textos.py --chave K` para reler um item; atualize "estoura 2h" para "4h".
- `README.md`, em "Decisões de projeto": um parágrafo curto sobre por que o texto fica em `dados/textos/` (sem corte, sem corrida) e por que a leitura é uma raia separada da coleta (o OCR é lento e não pode competir com o orçamento de 600 s da varredura).

- [ ] **Step 5: Verificar e commitar**

Run: `bash -n scripts/rodar_varredura.sh && python3 -m unittest discover -s tests -v`
Expected: sem erro de sintaxe; suíte PASS

```bash
git add scripts/rodar_varredura.sh deploy/systemd/reforma-ciclo.service CLAUDE.md docs/operacao-local.md README.md
git commit -m "ops: raia de leitura no ciclo, timeout de 4h, documentacao"
```

---

### Task 11: Backfill do acervo e medição de cobertura

**Files:**
- Create: `scripts/cobertura_textos.py`, `scripts/reler_dou.py`
- Test: `tests/test_cobertura_textos.py`

**Interfaces:**
- Consumes: `textos.*`, `dados/leituras.json`, `dou.coleta(dias: list[str], email, senha) -> (itens, diag)` (`scripts/dou.py`), `portais.base.chave`
- Produces:
  - `cobertura_textos.cobertura(raiz: Path) -> dict[str, collections.Counter]` (por fonte: `total`, `com_texto`, `ocr`, `falhou`, `desistiu`, `parcial`, `sem_tentativa`)
  - CLI `python3 scripts/cobertura_textos.py`: imprime uma tabela por fonte e a linha TOTAL
  - CLI `python3 scripts/reler_dou.py`: grava `dados/textos/<chave>.txt` para itens DOU sem texto ou `coleta_cortada` (precisa de `INLABS_EMAIL`/`INLABS_SENHA`)

- [ ] **Step 1: Write the failing test**

`tests/test_cobertura_textos.py`:
```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cobertura_textos
import textos


class TestCobertura(unittest.TestCase):
    def test_contagem_por_fonte(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            (raiz / "dados").mkdir()
            (raiz / "dados" / "historico.json").write_text(json.dumps({
                "a": {"fonte": "CGIBS - Portarias"}, "b": {"fonte": "CGIBS - Portarias"},
                "c": {"fonte": "CGIBS - Portarias"}, "d": {"fonte": "RFB - Noticias 2026"}}))
            (raiz / "dados" / "leituras.json").write_text(json.dumps({
                "a": {"status": "lido", "origem": "pdf+ocr"}, "b": {"status": "falhou"}}))
            textos.grava(raiz / "dados", "a", "x")
            c = cobertura_textos.cobertura(raiz)
        p = c["CGIBS - Portarias"]
        self.assertEqual((p["total"], p["com_texto"], p["ocr"], p["falhou"], p["sem_tentativa"]),
                         (3, 1, 1, 1, 1))
        self.assertEqual(c["RFB - Noticias 2026"]["sem_tentativa"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cobertura_textos -v`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`scripts/cobertura_textos.py`:
```python
#!/usr/bin/env python3
"""Cobertura de texto integral por fonte: quanto do historico a analise pode
ler literalmente. Uso: python3 scripts/cobertura_textos.py"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos

RAIZ = Path(__file__).resolve().parent.parent


def cobertura(raiz):
    dados = raiz / "dados"
    hist = json.loads((dados / "historico.json").read_text("utf-8"))
    p = dados / "leituras.json"
    leit = json.loads(p.read_text("utf-8")) if p.exists() else {}
    c = collections.defaultdict(collections.Counter)
    for k, it in hist.items():
        f = c[it.get("fonte") or "?"]
        f["total"] += 1
        meta = leit.get(k)
        if textos.existe(dados, k) or (it.get("texto") or "").strip():
            f["com_texto"] += 1
            if meta and "ocr" in (meta.get("origem") or ""):
                f["ocr"] += 1
            if meta and meta.get("status") == "parcial":
                f["parcial"] += 1
        elif meta is None:
            f["sem_tentativa"] += 1
        else:
            f[meta.get("status") or "?"] += 1
    return c


def main():
    c = cobertura(RAIZ)
    cols = ("total", "com_texto", "ocr", "parcial", "falhou", "desistiu", "sem_tentativa")
    print(f"{'fonte':40}" + "".join(f"{x:>14}" for x in cols))
    tot = collections.Counter()
    for f in sorted(c):
        tot.update(c[f])
        print(f"{f[:40]:40}" + "".join(f"{c[f][x]:>14}" for x in cols))
    print(f"{'TOTAL':40}" + "".join(f"{tot[x]:>14}" for x in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`scripts/reler_dou.py`:
```python
#!/usr/bin/env python3
"""Backfill: texto integral dos itens antigos do DOU, buscado de novo no INLABS.

Os itens de 17 a 24/08/2026 entraram antes da Parte A (sem texto), e os de
28/08 em diante guardaram `texto` cortado em 20.000 caracteres. Este script
baixa de novo as edicoes dessas datas, recalcula a chave de cada materia e,
quando ela bate com um item do historico, grava o texto integral em
dados/textos/<chave>.txt. Nao escreve dados/leituras.json (o unico escritor
e' ler_textos.py, que reconhece o arquivo novo na proxima execucao).

Materia que nao casa (o titulo foi montado diferente na epoca) e' listada no
fim, para conferencia manual. Uso: INLABS_EMAIL=... INLABS_SENHA=... python3 scripts/reler_dou.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dou
import textos
from portais.base import chave

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"


def alvos(dados):
    hist = json.loads((dados / "historico.json").read_text("utf-8"))
    p = dados / "leituras.json"
    leit = json.loads(p.read_text("utf-8")) if p.exists() else {}
    out = {}
    for k, it in hist.items():
        if not (it.get("fonte") or "").startswith("DOU"):
            continue
        if textos.existe(dados, k) and leit.get(k, {}).get("origem") != "coleta_cortada":
            continue
        out[k] = it
    return out


def main():
    email, senha = os.environ.get("INLABS_EMAIL"), os.environ.get("INLABS_SENHA")
    if not email or not senha:
        print("defina INLABS_EMAIL e INLABS_SENHA", file=sys.stderr)
        return 2
    pend = alvos(DADOS)
    dias = sorted({it.get("data") or it["primeira_vez"] for it in pend.values()})
    print(f"{len(pend)} item(ns) do DOU em {len(dias)} dia(s): {', '.join(dias)}", file=sys.stderr)
    itens, diag = dou.coleta(dias, email, senha)
    print(f"INLABS: {diag.get('lidas')} materias lidas; sem edicao: {diag.get('sem_edicao')}; "
          f"erros: {diag.get('erros')}", file=sys.stderr)
    achados = 0
    for it in itens:
        k = chave(it)
        integral = it.get("texto_integral") or ""
        if k in pend and integral.strip():
            textos.grava(DADOS, k, integral)
            pend.pop(k)
            achados += 1
    print(f"{achados} texto(s) gravado(s); {len(pend)} sem correspondencia:", file=sys.stderr)
    for k, it in pend.items():
        print(f"  {k} {it.get('data')} {(it.get('titulo') or '')[:90]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_cobertura_textos -v && python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: Commit do código**

```bash
git add scripts/cobertura_textos.py scripts/reler_dou.py tests/test_cobertura_textos.py
git commit -m "feat: cobertura_textos.py e reler_dou.py para o backfill"
```

- [ ] **Step 6: Executar o backfill no lenovo-claude**

Fora do horário do ciclo (05:00 e 17:00), com o checkout sincronizado:
```bash
scripts/publicar.sh --sincronizar
.venv/bin/python3 scripts/cobertura_textos.py | tee /tmp/claude-1000/cobertura-antes.txt
.venv/bin/python3 scripts/varredura.py                # coleta as fontes novas (SVRS, NF-e)
.venv/bin/python3 scripts/semear_analisados.py \
  --fonte "Portal DF-e SVRS - Noticias" --fonte "Portal NF-e - Informes/NTs" \
  --fonte "Portal NF-e - Atos RFB/CGIBS" --fonte "Portal NF-e - Atos Tecnicos RFB/CGIBS" \
  --fonte "Portal NF-e - Notas Tecnicas" --fonte "Portal NF-e - Informes Tecnicos"
```
Confira a lista (dry run). Ela deve conter só publicações antigas, e o que tiver data nos últimos 30 dias fica de fora e vai para a análise. Então:
```bash
.venv/bin/python3 scripts/semear_analisados.py <mesmas --fonte> --aplicar
set -a; . ./.env; set +a
.venv/bin/python3 scripts/reler_dou.py
.venv/bin/python3 scripts/ler_textos.py --sem-limite 2>&1 | tee /tmp/claude-1000/backfill.log
.venv/bin/python3 scripts/cobertura_textos.py | tee /tmp/claude-1000/cobertura-depois.txt
```
Expected: `com_texto` igual a `total` em todas as fontes, exceto os itens `desistiu` ou `falhou`, que precisam ser explicados um a um (`grep -E "falhou|desistiu" /tmp/claude-1000/backfill.log`). Os itens de menu antigos (ex.: "Conheça a NF-e", "SEFAZ VIRTUAL RS") podem ter texto genérico ou falhar. Isso é aceitável porque já foram analisados e não são publicações; anote-os no relatório.

- [ ] **Step 7: Verificação de qualidade por amostragem**

```bash
.venv/bin/python3 - <<'EOF'
import json; L = json.load(open("dados/leituras.json")); H = json.load(open("dados/historico.json"))
for k, m in L.items():
    if "ocr" in (m.get("origem") or "") or m.get("anexos"):
        print(m["origem"], m.get("paginas_ocr"), len(m.get("anexos", [])), H[k]["titulo"][:70], k)
EOF
```
Abra pelo menos 3 arquivos `dados/textos/<chave>.txt`: o **Ato Conjunto RFB/CGIBS de 29/05** (OCR: o texto do ato deve estar legível, com artigos e datas), a **notícia da RFB de 30/09** ("145.516 foram deferidas") e uma **Resolução CGIBS** (camada de texto). Compare trechos com o PDF original. Se o OCR estiver ruim (palavras quebradas em mais de 5% do texto), registre e avalie subir `DPI_OCR` para 400 antes de seguir.

- [ ] **Step 8: Teste da lacuna com texto**

```bash
.venv/bin/python3 scripts/lacuna_analise.py | .venv/bin/python3 -c "
import json,sys; l=json.load(sys.stdin)
print('itens', len(l['itens']), 'aguardando', len(l['aguardando_leitura']))
for i in l['itens'][:10]: print(i['texto_origem'], i['texto_chars'], i['texto_truncado'], i['titulo'][:60])"
```
Expected: os itens pendentes trazem `texto_origem` preenchido e `texto_chars > 0`. `aguardando_leitura` fica vazio depois do backfill.

- [ ] **Step 9: Publicar**

```bash
scripts/publicar.sh "leitura integral: backfill do acervo" dados docs
```
Expected: commit com `dados/textos/*.txt`, `dados/leituras.json` e `dados/analisados.json` (semeadura). Push ok.

- [ ] **Step 10: Acompanhar o primeiro ciclo real**

Depois do próximo ciclo (05:00 ou 17:00):
```bash
journalctl -u reforma-ciclo.service -n 200 | grep -E "leitura|AVISO|ciclo"
.venv/bin/python3 scripts/cobertura_textos.py | tail -1
grep -c "VERIFICADO LITERAL" analises/$(date +%F)-*.md; grep -c "\[PESQUISA\]" analises/$(date +%F)-*.md
```
Expected: o ciclo fecha bem antes das 4h; a análise do ciclo usa `[VERIFICADO LITERAL]` nos itens novos, e `[PESQUISA]` só aparece em item com `leitura.status = desistiu`.
