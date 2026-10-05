# Consulta remota ao acervo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rodrigo consulta pelo app do Claude, a qualquer hora, um Claude Code com acesso total ao acervo (leis-base compiladas do Planalto + publicações coletadas + análises), recebendo respostas com fonte e marca de confiança.

**Architecture:** Um serviço systemd mantém `claude remote-control --spawn worktree` sempre ligado no lenovo-claude. Cada sessão aberta pelo app nasce numa worktree própria a partir do `main`. As leis-base entram no repositório em `normas/` via `scripts/baixar_normas.py` (Planalto, texto compilado, trechos riscados marcados), atualizadas semanalmente ou quando a varredura coleta uma alteração. `scripts/buscar.py` busca em `normas/` + `dados/textos/` e detecta alterações ainda não incorporadas à compilação. Uma skill de projeto (`.claude/skills/consulta-reforma/`) diz às sessões como consultar e citar.

**Tech Stack:** Python 3 stdlib (`html.parser`, `unicodedata`, `argparse`, `unittest`), `leitura.baixar.Sessao` existente, systemd, Claude Code 2.1.278 (`claude remote-control`).

**Spec:** `docs/superpowers/specs/2026-10-05-consulta-remota-design.md`

## Global Constraints

- **Nenhuma dependência pip nova.**
- **Código, comentários, docstrings e logs em português** (sem acentuação obrigatória nos comentários), padrão do repo. Scripts rodam como `python3 scripts/<nome>.py`; testes fazem `sys.path.insert(0, .../scripts)`.
- **Suíte:** `/home/rodrigo/projects/reforma-tributaria-monitor/.venv/bin/python3 -m unittest discover -s tests -v` — precisa passar ao fim de cada task (o python3 do sistema não tem `markdown`).
- **Um escritor por arquivo:** `normas/*` e `dados/normas_status.json` só por `scripts/baixar_normas.py`.
- **Falha de normas nunca derruba o ciclo:** `rodar_varredura.sh` chama `baixar_normas.py --se-necessario` com `|| echo AVISO`; normas anteriores ficam.
- **Texto riscado no Planalto nunca aparece como vigente:** sai como `[NÃO VIGENTE: …]`.
- **Constantes:** `DIAS_ATUALIZACAO = 7` (baixar_normas), `JANELA_ALTERACOES_DIAS = 30` (buscar), worktrees de consulta removidas após `DIAS_WORKTREE = 7` dias só se limpas e sem commit fora do `main`.
- **Serviço:** `claude remote-control --name "Reforma – consulta" --spawn worktree --no-create-session-in-dir --permission-mode bypassPermissions`, `Restart=always`, `OnFailure=reforma-falha@%n.service` (decisão explícita do Rodrigo: sem restrições de permissão).

## Review Focus

1. **Planalto mudou o HTML / devolveu página de erro com 200:** o esperado é falha da norma (contagem mínima de artigos), arquivo anterior intacto, erro em `dados/normas_status.json`. Teste na Task 1 (`test_estrutura_irreconhecivel_falha_e_preserva_anterior`).
2. **Alteração publicada no DOU antes do download, mas ainda não compilada pelo Planalto:** `--alteracoes-de` não pode excluí-la só por ser anterior ao `baixado_em` (usa janela de 30 dias e marca se o ato já aparece no texto compilado). Teste na Task 2 (`test_alteracao_anterior_ao_download_nao_compilada_aparece`).
3. **Busca com acento/sem acento e "nº"/"no":** "redação", "redacao", "LC 214", "Lei Complementar nº 214" precisam casar. Teste na Task 2 (`test_normalizacao_acentos_e_numero`).
4. **"Art. 124" existe no corpo da CF e no ADCT:** o recorte do ADCT tem de pegar o do ADCT. Teste na Task 1 (`test_recorte_adct_nao_pega_art_124_da_cf`).
5. **Worktree de sessão ativa ou com trabalho:** a limpeza nunca remove worktree suja, com commit fora do `main`, recente, protegida ou fora de `.claude/worktrees/`. Teste na Task 4 (`test_nunca_remove_*`).

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `scripts/baixar_normas.py` (novo) | Lista de normas, HTML do Planalto → texto com marcação de riscados, recortes da CF/ADCT, validação, `normas/<id>.txt` + `normas/indice.json`, decisão `--se-necessario`, `dados/normas_status.json`. |
| `normas/` (novo, versionado) | `ec132.txt`, `cf-reforma.txt`, `lc214.txt`, `lc227.txt`, `indice.json` — primeira carga commitada na Task 1. |
| `scripts/buscar.py` (novo) | Corpus (normas + publicações com texto), busca normalizada com ranking e dispositivo, `--alteracoes-de`. |
| `.claude/skills/consulta-reforma/SKILL.md` (novo, versionado) | Instruções das sessões de consulta. |
| `.gitignore` | `.claude/` → `.claude/*` + `!.claude/skills/`. |
| `scripts/rodar_varredura.sh` | Chama `baixar_normas.py --se-necessario` (não fatal) e publica `normas/`. |
| `scripts/limpar_worktrees.py` (novo) | Remove worktrees de consulta antigas e limpas; avisa as com trabalho pendente. |
| `scripts/notificar.py` | `--aviso "msg"` (prioridade normal, não urgente). |
| `deploy/systemd/reforma-consulta.service`, `reforma-limpeza.service`, `reforma-limpeza.timer` (novos) | Serviço do remote-control e limpeza semanal. |
| `CLAUDE.md`, `docs/operacao-local.md` | Documentação. |
| Testes novos | `tests/test_baixar_normas.py`, `tests/test_buscar.py`, `tests/test_limpar_worktrees.py`; `tests/test_notificar.py` ganha casos de `--aviso`. |

---

### Task 1: Leis-base do Planalto (`baixar_normas.py` + primeira carga de `normas/`)

**Files:**
- Create: `scripts/baixar_normas.py`, `tests/test_baixar_normas.py`
- Create (dados versionados, Step 6): `normas/ec132.txt`, `normas/cf-reforma.txt`, `normas/lc214.txt`, `normas/lc227.txt`, `normas/indice.json`

**Interfaces:**
- Consumes: `leitura.baixar.Sessao().baixa(url) -> Resposta(dados, tipo, charset, url)`, `ErroDownload`; `textos.le(dados_dir, chave)`; `portais.base.chave(item)`.
- Produces:
  - `baixar_normas.NORMAS: list[dict]` com `id, titulo, rotulo, url, minimo_artigos, recortes`
  - `baixar_normas.html_para_texto(html: str) -> str`
  - `baixar_normas.recorta(texto: str, recortes: list[tuple]) -> str`
  - `baixar_normas.valida(texto: str, minimo: int) -> None` (levanta `ErroNorma`)
  - `baixar_normas.precisa_atualizar(indice: dict, novidades: list[dict], hoje: datetime.date) -> tuple[bool, str]`
  - `baixar_normas.executa(raiz: Path, forcar: bool = False, sessao=None, hoje=None) -> int` (0 ok, 1 se alguma norma falhou)
  - `normas/indice.json`: `{id: {"titulo", "rotulo", "url", "baixado_em": "AAAA-MM-DDTHH:MM:SSZ", "sha256", "chars"}}`
  - `dados/normas_status.json`: `{"executado_em", "resultado": "atualizado"|"sem_necessidade"|"falha_parcial", "motivo", "erros": [str]}`

- [ ] **Step 1: Write the failing test**

`tests/test_baixar_normas.py`:
```python
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import baixar_normas as bn
from leitura import baixar

# Trecho no formato real do Planalto (lcp214.htm): paragrafos MsoNormal,
# ancora <a name="artN">, dispositivo riscado dentro de <strike>.
HTML_LC = """<html><head><meta charset="windows-1252"></head><body>
<p class="MsoNormal"><a name="art1"></a>Art. 1º Fica instituído o Imposto sobre Bens e Serviços (IBS).</p>
<p class="MsoNormal"><a name="art26"></a>Art. 26. Ficam reduzidas a zero as alíquotas.</p>
<p class="MsoNormal"><strike><a name="art26§1"></a>§ 1º Redação antiga que não vale mais.</strike></p>
<p class="MsoNormal">§ 1º Redação nova. <a href="x">(Redação dada pela Lei Complementar nº 227, de 2026)</a></p>
<p class="MsoNormal">Art. 27. Texto <strike>com trecho riscado</strike> no meio.</p>
<script>var x = 1;</script>
</body></html>"""

HTML_CF = """<html><body>
<p>Art. 124. À Justiça Militar compete processar e julgar os crimes militares.</p>
<p>Art. 145. A União, os Estados, o Distrito Federal e os Municípios poderão instituir tributos.</p>
<p>Art. 156-A. Lei complementar instituirá imposto sobre bens e serviços.</p>
<p>Art. 162. Os entes divulgarão os montantes.</p>
<p>Art. 163. Lei complementar disporá sobre finanças públicas.</p>
<p>Art. 195. A seguridade social será financiada.</p>
<p>Art. 196. A saúde é direito de todos.</p>
<p><a name="adct"></a>ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS</p>
<p>Art. 124. A transição entre a extinção e a instituição dos tributos observará este ADCT.</p>
<p>Art. 138. Disposição final da transição.</p>
<p>Art. 139. Outra coisa.</p>
</body></html>"""


class FakeSessao:
    def __init__(self, mapa):
        self.mapa = mapa

    def baixa(self, url):
        v = self.mapa.get(url)
        if v is None:
            raise baixar.ErroDownload("HTTP 503")
        return baixar.Resposta(v.encode("cp1252"), "text/html", None, url)


class TestHtmlParaTexto(unittest.TestCase):
    def test_paragrafos_e_artigos_em_linhas(self):
        t = bn.html_para_texto(HTML_LC)
        self.assertRegex(t, r"(?m)^Art\. 1º Fica instituído o Imposto")
        self.assertRegex(t, r"(?m)^Art\. 26\. Ficam reduzidas")
        self.assertNotIn("var x", t)

    def test_riscado_nunca_aparece_como_vigente(self):
        t = bn.html_para_texto(HTML_LC)
        self.assertIn("[NÃO VIGENTE: § 1º Redação antiga que não vale mais.]", t)
        self.assertIn("Texto [NÃO VIGENTE: com trecho riscado] no meio.", t)
        for linha in t.splitlines():
            if "Redação antiga" in linha:
                self.assertIn("[NÃO VIGENTE:", linha)

    def test_risco_atravessando_paragrafos_marca_cada_linha(self):
        t = bn.html_para_texto("<p><strike>Art. 9º Antigo.</p><p>§ 1º Também antigo.</strike></p>"
                               "<p>Art. 10. Vigente.</p>")
        self.assertIn("[NÃO VIGENTE: Art. 9º Antigo.]", t)
        self.assertIn("[NÃO VIGENTE: § 1º Também antigo.]", t)
        self.assertRegex(t, r"(?m)^Art\. 10\. Vigente\.")
        for linha in t.splitlines():
            if "antigo" in linha.lower():
                self.assertTrue(linha.startswith("[NÃO VIGENTE:"), linha)

    def test_anotacao_de_redacao_preservada(self):
        self.assertIn("(Redação dada pela Lei Complementar nº 227, de 2026)",
                      bn.html_para_texto(HTML_LC))


class TestRecorta(unittest.TestCase):
    def setUp(self):
        self.texto = bn.html_para_texto(HTML_CF)
        self.recortes = next(n for n in bn.NORMAS if n["id"] == "cf-reforma")["recortes"]

    def test_pega_145_a_162_e_195(self):
        r = bn.recorta(self.texto, self.recortes)
        self.assertIn("Art. 145. A União", r)
        self.assertIn("Art. 156-A.", r)
        self.assertIn("Art. 162.", r)
        self.assertIn("Art. 195. A seguridade", r)
        self.assertNotIn("Art. 163.", r)
        self.assertNotIn("Art. 196.", r)

    def test_recorte_adct_nao_pega_art_124_da_cf(self):
        r = bn.recorta(self.texto, self.recortes)
        self.assertIn("Art. 124. A transição", r)
        self.assertNotIn("Justiça Militar", r)
        self.assertIn("Art. 138.", r)
        self.assertNotIn("Art. 139.", r)

    def test_recorte_ausente_levanta(self):
        with self.assertRaises(bn.ErroNorma):
            bn.recorta("texto sem artigos", self.recortes)


class TestValida(unittest.TestCase):
    def test_poucos_artigos_levanta(self):
        with self.assertRaises(bn.ErroNorma):
            bn.valida("Art. 1º só um.", 2)

    def test_conta_artigos_inclusive_riscados(self):
        bn.valida("Art. 1º a\n[NÃO VIGENTE: Art. 2º b]\nArt. 3º c", 3)


class TestPrecisaAtualizar(unittest.TestCase):
    HOJE = datetime.date(2026, 10, 20)

    def indice(self, dias):
        d = (self.HOJE - datetime.timedelta(days=dias)).isoformat() + "T08:00:00Z"
        return {n["id"]: {"baixado_em": d} for n in bn.NORMAS}

    def test_sem_indice_precisa(self):
        self.assertTrue(bn.precisa_atualizar({}, [], self.HOJE)[0])

    def test_recente_sem_gatilho_nao_precisa(self):
        ok, motivo = bn.precisa_atualizar(self.indice(2), [], self.HOJE)
        self.assertFalse(ok)

    def test_sete_dias_precisa(self):
        self.assertTrue(bn.precisa_atualizar(self.indice(7), [], self.HOJE)[0])

    def test_gatilho_lei_complementar_nova(self):
        nov = [{"titulo": "LEI COMPLEMENTAR Nº 230, DE 19 DE OUTUBRO DE 2026", "texto": ""}]
        ok, motivo = bn.precisa_atualizar(self.indice(1), nov, self.HOJE)
        self.assertTrue(ok)
        self.assertIn("230", motivo)

    def test_gatilho_altera_lc214_no_texto(self):
        nov = [{"titulo": "Portaria qualquer", "texto": "Altera a Lei Complementar nº 214, de 2025"}]
        self.assertTrue(bn.precisa_atualizar(self.indice(1), nov, self.HOJE)[0])

    def test_publicacao_comum_nao_dispara(self):
        nov = [{"titulo": "Portaria RFB nº 600 sobre IBS", "texto": "dispõe sobre obrigações"}]
        self.assertFalse(bn.precisa_atualizar(self.indice(1), nov, self.HOJE)[0])


class TestExecuta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        (self.raiz / "dados").mkdir()
        (self.raiz / "dados" / "historico.json").write_text("{}", "utf-8")
        self.paginas = {}
        for n in bn.NORMAS:
            self.paginas[n["url"]] = HTML_CF if n["recortes"] else HTML_LC
        self.normas_min = {n["id"]: n["minimo_artigos"] for n in bn.NORMAS}
        for n in bn.NORMAS:          # fixtures sao pequenas
            n["minimo_artigos"] = 2

    def tearDown(self):
        for n in bn.NORMAS:
            n["minimo_artigos"] = self.normas_min[n["id"]]
        self.tmp.cleanup()

    def test_forcar_grava_arquivos_indice_e_status(self):
        rc = bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        self.assertEqual(rc, 0)
        idx = json.loads((self.raiz / "normas" / "indice.json").read_text("utf-8"))
        self.assertEqual(set(idx), {n["id"] for n in bn.NORMAS})
        lc = (self.raiz / "normas" / "lc214.txt").read_text("utf-8")
        self.assertTrue(lc.startswith("# "))
        self.assertIn("Texto compilado baixado em:", lc)
        self.assertIn("Art. 26. Ficam reduzidas", lc)
        st = json.loads((self.raiz / "dados" / "normas_status.json").read_text("utf-8"))
        self.assertEqual(st["resultado"], "atualizado")

    def test_estrutura_irreconhecivel_falha_e_preserva_anterior(self):
        bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        antes = (self.raiz / "normas" / "lc214.txt").read_text("utf-8")
        lc214 = next(n for n in bn.NORMAS if n["id"] == "lc214")
        quebrado = dict(self.paginas, **{lc214["url"]: "<html><body>Página em manutenção</body></html>"})
        rc = bn.executa(self.raiz, forcar=True, sessao=FakeSessao(quebrado))
        self.assertEqual(rc, 1)
        self.assertEqual((self.raiz / "normas" / "lc214.txt").read_text("utf-8"), antes)
        st = json.loads((self.raiz / "dados" / "normas_status.json").read_text("utf-8"))
        self.assertEqual(st["resultado"], "falha_parcial")
        self.assertTrue(any("lc214" in e for e in st["erros"]))

    def test_planalto_fora_do_ar_nao_lanca(self):
        rc = bn.executa(self.raiz, forcar=True, sessao=FakeSessao({}))
        self.assertEqual(rc, 1)

    def test_se_necessario_sem_necessidade_nao_baixa(self):
        bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        rc = bn.executa(self.raiz, forcar=False, sessao=FakeSessao({}))
        self.assertEqual(rc, 0)
        st = json.loads((self.raiz / "dados" / "normas_status.json").read_text("utf-8"))
        self.assertEqual(st["resultado"], "sem_necessidade")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m unittest tests.test_baixar_normas -v` (use the absolute venv path from Global Constraints)
Expected: FAIL com `ModuleNotFoundError: No module named 'baixar_normas'`

- [ ] **Step 3: Write minimal implementation**

`scripts/baixar_normas.py`:
```python
#!/usr/bin/env python3
"""Leis-base da reforma em texto compilado do Planalto -> normas/.

Fonte primaria das sessoes de consulta (skill consulta-reforma) e da
analise. Texto compilado = ja' com as alteracoes posteriores; o que o
Planalto mostra riscado (revogado ou redacao anterior) sai como
[NÃO VIGENTE: ...] e nunca como texto vigente.

Grava (unico escritor):
  normas/<id>.txt          texto, com cabecalho de fonte e data
  normas/indice.json       {id: {titulo, rotulo, url, baixado_em, sha256, chars}}
  dados/normas_status.json resultado da ultima execucao

Uso:
  python3 scripts/baixar_normas.py --se-necessario   # ciclo: >= 7 dias ou gatilho
  python3 scripts/baixar_normas.py --forcar          # sob demanda
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos
from leitura.baixar import ErroDownload, Sessao
from portais.base import chave

RAIZ = Path(__file__).resolve().parent.parent
BASE = "https://www.planalto.gov.br/ccivil_03/"
DIAS_ATUALIZACAO = 7

# (rotulo, regex do inicio, regex do fim, regex que precisa vir ANTES do inicio ou None)
_ART = r"(?m)^(?:\[NÃO VIGENTE: )?Art\. {}\b"
NORMAS = [
    {"id": "ec132", "rotulo": "EC 132",
     "titulo": "Emenda Constitucional nº 132, de 20 de dezembro de 2023",
     "url": BASE + "constituicao/emendas/emc/emc132.htm", "minimo_artigos": 5, "recortes": None},
    {"id": "cf-reforma", "rotulo": "CF/ADCT",
     "titulo": "Constituição Federal — arts. 145 a 162 e 195; ADCT arts. 124 a 138 (texto compilado)",
     "url": BASE + "constituicao/constituicao.htm", "minimo_artigos": 20,
     "recortes": [
         ("CONSTITUIÇÃO FEDERAL — arts. 145 a 162", _ART.format(145), _ART.format(163), None),
         ("CONSTITUIÇÃO FEDERAL — art. 195", _ART.format(195), _ART.format(196), None),
         ("ADCT — arts. 124 a 138", _ART.format(124), _ART.format(139),
          r"ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"),
     ]},
    {"id": "lc214", "rotulo": "LC 214",
     "titulo": "Lei Complementar nº 214, de 16 de janeiro de 2025 (texto compilado)",
     "url": BASE + "leis/lcp/lcp214.htm", "minimo_artigos": 400, "recortes": None},
    {"id": "lc227", "rotulo": "LC 227",
     "titulo": "Lei Complementar nº 227, de 13 de janeiro de 2026 (texto compilado)",
     "url": BASE + "leis/lcp/lcp227.htm", "minimo_artigos": 50, "recortes": None},
]

# Novidade que provavelmente altera uma norma-base: antecipa o download.
GATILHO = re.compile(
    r"lei complementar n[º°o.]*\s*\d|emenda constitucional n[º°o.]*\s*\d"
    r"|altera a lei complementar n[º°o.]*\s*(214|227)", re.I)


class ErroNorma(Exception):
    pass


class _Texto(HTMLParser):
    IGNORA = {"script", "style", "head", "title"}
    BLOCO = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote"}
    RISCO = {"strike", "s", "del"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buf, self._ign, self._risco = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORA:
            self._ign += 1
        elif tag in self.BLOCO:
            self.buf.append(self._quebra())
        elif tag in self.RISCO:
            if self._risco == 0:
                self.buf.append("[NÃO VIGENTE: ")
            self._risco += 1

    def handle_endtag(self, tag):
        if tag in self.IGNORA and self._ign:
            self._ign -= 1
        elif tag in self.RISCO and self._risco:
            self._risco -= 1
            if self._risco == 0:
                self.buf.append("]")
        elif tag in self.BLOCO:
            self.buf.append(self._quebra())

    def _quebra(self):
        # risco que atravessa paragrafos: fecha e reabre a marca em cada linha,
        # para nenhuma linha do meio parecer vigente
        return "]\n[NÃO VIGENTE: " if self._risco else "\n"

    def handle_data(self, data):
        if not self._ign:
            self.buf.append(data)


def html_para_texto(html):
    p = _Texto()
    p.feed(html)
    p.close()
    t = "".join(p.buf).replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\[NÃO VIGENTE:\s*\]", "", t)          # marcas vazias
    # colchete de risco aberto no fim de um paragrafo e fechado no seguinte
    t = re.sub(r"\[NÃO VIGENTE: \n+", "\n[NÃO VIGENTE: ", t)
    t = re.sub(r"\n+\]", "]", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


def recorta(texto, recortes):
    partes = []
    for rotulo, ini, fim, depois_de in recortes:
        base = 0
        if depois_de:
            m = re.search(depois_de, texto)
            if not m:
                raise ErroNorma(f"recorte '{rotulo}': marco '{depois_de}' nao encontrado")
            base = m.end()
        mi = re.compile(ini).search(texto, base)
        if not mi:
            raise ErroNorma(f"recorte '{rotulo}': inicio nao encontrado")
        mf = re.compile(fim).search(texto, mi.end())
        trecho = texto[mi.start():mf.start() if mf else len(texto)]
        partes.append(f"===== {rotulo} =====\n\n{trecho.strip()}\n")
    return "\n".join(partes)


def valida(texto, minimo):
    n = len(re.findall(r"(?m)^(?:\[NÃO VIGENTE: )?Art\. \d", texto))
    if n < minimo:
        raise ErroNorma(f"so' {n} artigo(s) reconhecido(s) (minimo {minimo}): "
                        "estrutura da pagina mudou ou pagina de erro")


def _decodifica(resp):
    for cs in filter(None, [resp.charset, "cp1252"]):
        try:
            return resp.dados.decode(cs)
        except (LookupError, UnicodeDecodeError):
            continue
    return resp.dados.decode("cp1252", "replace")


def _agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _le_json(p, padrao):
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else padrao
    except ValueError:
        return padrao


def _grava_atomico(p, conteudo):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(conteudo, "utf-8")
    tmp.replace(p)


def precisa_atualizar(indice, novidades, hoje):
    datas = []
    for n in NORMAS:
        meta = indice.get(n["id"])
        if not meta:
            return True, f"{n['id']} ainda nao baixada"
        datas.append(datetime.date.fromisoformat(meta["baixado_em"][:10]))
    idade = (hoje - min(datas)).days
    if idade >= DIAS_ATUALIZACAO:
        return True, f"compilacao com {idade} dia(s)"
    for it in novidades:
        alvo = f"{it.get('titulo', '')}\n{(it.get('texto') or '')[:3000]}"
        m = GATILHO.search(alvo)
        if m:
            return True, f"gatilho '{m.group(0)}' em: {it.get('titulo', '')[:120]}"
    return False, f"compilacao com {idade} dia(s), sem gatilho"


def _novidades(raiz):
    """Itens novos do ultimo ciclo (web + DOU), com o texto integral quando houver."""
    out = []
    for nome in ("novidades.json", "novidades_dou.json"):
        for it in _le_json(raiz / "dados" / nome, {}).get("itens", []):
            t = textos.le(raiz / "dados", chave(it)) or it.get("texto") or ""
            out.append({"titulo": it.get("titulo", ""), "texto": t})
    return out


def baixa_norma(sessao, norma):
    texto = html_para_texto(_decodifica(sessao.baixa(norma["url"])))
    if norma["recortes"]:
        texto = recorta(texto, norma["recortes"])
    valida(texto, norma["minimo_artigos"])
    return texto


def executa(raiz, forcar=False, sessao=None, hoje=None):
    raiz = Path(raiz)
    hoje = hoje or datetime.date.today()
    arq_idx = raiz / "normas" / "indice.json"
    indice = _le_json(arq_idx, {})
    status = {"executado_em": _agora(), "erros": []}
    if forcar:
        motivo = "forcado"
    else:
        precisa, motivo = precisa_atualizar(indice, _novidades(raiz), hoje)
        if not precisa:
            status.update(resultado="sem_necessidade", motivo=motivo)
            _grava_atomico(raiz / "dados" / "normas_status.json",
                           json.dumps(status, ensure_ascii=False, indent=1))
            print(f"normas: {motivo}", file=sys.stderr)
            return 0
    sessao = sessao or Sessao()
    for n in NORMAS:
        try:
            texto = baixa_norma(sessao, n)
        except (ErroDownload, ErroNorma) as e:
            status["erros"].append(f"{n['id']}: {type(e).__name__}: {e}")
            print(f"normas: {n['id']} FALHOU ({e}); arquivo anterior mantido", file=sys.stderr)
            continue
        quando = _agora()
        cab = (f"# {n['titulo']}\n# Fonte: {n['url']}\n# Texto compilado baixado em: {quando}\n"
               "# Trechos riscados no Planalto (revogados ou com redação anterior) aparecem "
               "como [NÃO VIGENTE: ...] e não estão em vigor.\n\n")
        _grava_atomico(raiz / "normas" / f"{n['id']}.txt", cab + texto)
        indice[n["id"]] = {"titulo": n["titulo"], "rotulo": n["rotulo"], "url": n["url"],
                           "baixado_em": quando,
                           "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                           "chars": len(texto)}
        print(f"normas: {n['id']} ok ({len(texto)} chars)", file=sys.stderr)
    _grava_atomico(arq_idx, json.dumps(indice, ensure_ascii=False, indent=1, sort_keys=True))
    status.update(resultado="falha_parcial" if status["erros"] else "atualizado", motivo=motivo)
    _grava_atomico(raiz / "dados" / "normas_status.json",
                   json.dumps(status, ensure_ascii=False, indent=1))
    return 1 if status["erros"] else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Leis-base do Planalto -> normas/")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--se-necessario", action="store_true")
    g.add_argument("--forcar", action="store_true")
    a = ap.parse_args(argv)
    return executa(RAIZ, forcar=a.forcar)


if __name__ == "__main__":
    sys.exit(main())
```

Notes for the implementer: `test_recorte_adct_nao_pega_art_124_da_cf` depends on the 4th tuple element (search only after the ADCT heading). `test_conta_artigos_inclusive_riscados` depends on `valida` accepting the `[NÃO VIGENTE: ` prefix. If a test reveals a real bug in the code above, fix the code, not the test, and note it in the report.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m unittest tests.test_baixar_normas -v` then the full suite.
Expected: PASS

- [ ] **Step 5: Smoke against the real Planalto (read-only, in the worktree)**

```bash
.venv/bin/python3 scripts/baixar_normas.py --forcar
cat dados/normas_status.json; .venv/bin/python3 -m json.tool normas/indice.json
for f in normas/*.txt; do echo "== $f $(wc -c <$f) bytes, $(grep -cE '^(\[NÃO VIGENTE: )?Art\. ' $f) artigos, $(grep -c 'NÃO VIGENTE' $f) riscados"; done
grep -n -m3 "NÃO VIGENTE" normas/lc214.txt; grep -n -m2 "^Art\. 26\." normas/lc214.txt
grep -n "=====" normas/cf-reforma.txt; grep -n -m1 "^Art\. 156-A" normas/cf-reforma.txt
```
Expected: `resultado: atualizado`; lc214 with hundreds of articles (the real law has ~544) and some `NÃO VIGENTE` lines; cf-reforma with the three `=====` sections, `Art. 156-A` present and **no** "Justiça Militar". Check the real encoding renders accents correctly (e.g. "Serviços"). If any norma fails, inspect the real HTML and adjust parser/recorte (and add a test reproducing the real case). Paste the outputs in the report.

- [ ] **Step 6: Commit (code + first load of normas/)**

```bash
git add scripts/baixar_normas.py tests/test_baixar_normas.py normas/
git commit -m "feat: baixar_normas.py traz as leis-base compiladas do Planalto para normas/"
```
(Do **not** commit `dados/normas_status.json` — it is regenerated by every run; leave it unstaged.)

---

### Task 2: Busca no acervo (`buscar.py`)

**Files:**
- Create: `scripts/buscar.py`, `tests/test_buscar.py`

**Interfaces:**
- Consumes: `normas/indice.json` + `normas/<id>.txt` (Task 1 schema); `dados/historico.json`; `textos.le(dados_dir, chave)`.
- Produces:
  - `buscar.normaliza(s: str) -> str` (sem acento, minúsculo, `º`→`o`)
  - `buscar.carrega(raiz: Path) -> list[dict]` docs `{tipo: "norma"|"publicacao", id, rotulo, titulo, data, fonte, url, caminho, texto}`
  - `buscar.busca(docs, consulta: str, fonte=None, desde=None, tipo=None, limite=20) -> list[dict]` com `{tipo, id, rotulo, data, fonte, url, caminho, trecho, dispositivo, score}`
  - `buscar.alteracoes_de(docs, norma_id: str, artigo: str|None = None) -> list[dict]` com `{id, titulo, data, fonte, url, caminho, atos, incorporada: True|False|None}`
  - CLI `buscar.py TERMOS [--fonte F] [--desde AAAA-MM-DD] [--tipo norma|publicacao] [--limite N]` e `buscar.py --alteracoes-de lc214 [--artigo 26]`

- [ ] **Step 1: Write the failing test**

`tests/test_buscar.py`:
```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import buscar
import textos

LC214 = """# Lei Complementar nº 214 (texto compilado)

Art. 25. Disposição anterior sobre o IBS.
Art. 26. Ficam reduzidas a zero as alíquotas do IBS e da CBS sobre cesta básica.
§ 1º Redação nova. (Redação dada pela Lei Complementar nº 227, de 2026)
[NÃO VIGENTE: § 1º Redação antiga.]
Art. 27. Split payment será obrigatório.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.raiz = Path(self.tmp.name)
        (r / "normas").mkdir()
        (r / "dados").mkdir()
        (r / "normas" / "lc214.txt").write_text(LC214, "utf-8")
        (r / "normas" / "indice.json").write_text(json.dumps({"lc214": {
            "titulo": "Lei Complementar nº 214", "rotulo": "LC 214",
            "url": "https://planalto/lcp214.htm", "baixado_em": "2026-10-10T08:00:00Z"}}), "utf-8")
        hist = {
            "k1": {"titulo": "LEI COMPLEMENTAR Nº 230, DE 8 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-10-08", "url": "u1", "primeira_vez": "2026-10-08"},
            "k2": {"titulo": "Ato Conjunto RFB/CGIBS nº 8", "fonte": "CGIBS - Atos Conjuntos",
                   "data": "2026-10-01", "url": "u2", "primeira_vez": "2026-10-01"},
            "k3": {"titulo": "LEI COMPLEMENTAR Nº 227, DE 13 DE JANEIRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-01-13", "url": "u3", "primeira_vez": "2026-01-13"},
            "k4": {"titulo": "Sem texto", "fonte": "RFB", "data": "2026-10-02", "url": "u4",
                   "primeira_vez": "2026-10-02"},
        }
        (r / "dados" / "historico.json").write_text(json.dumps(hist), "utf-8")
        textos.grava(r / "dados", "k1", "Altera o art. 26 da Lei Complementar nº 214, de 2025, "
                                        "que passa a vigorar com nova redação sobre split payment.")
        textos.grava(r / "dados", "k2", "Dispõe sobre o split payment e a apuração assistida do IBS.")
        textos.grava(r / "dados", "k3", "Altera a LC 214 em diversos artigos, inclusive o art. 26.")
        self.docs = buscar.carrega(r)

    def tearDown(self):
        self.tmp.cleanup()


class TestCarrega(Base):
    def test_normas_e_publicacoes_com_texto(self):
        tipos = sorted((d["tipo"], d["id"]) for d in self.docs)
        self.assertEqual(tipos, [("norma", "lc214"), ("publicacao", "k1"),
                                 ("publicacao", "k2"), ("publicacao", "k3")])
        k1 = next(d for d in self.docs if d["id"] == "k1")
        self.assertEqual(k1["caminho"], "dados/textos/k1.txt")


class TestBusca(Base):
    def test_todos_os_termos_e_ranking(self):
        r = buscar.busca(self.docs, "split payment")
        self.assertEqual({x["id"] for x in r}, {"lc214", "k1", "k2"})

    def test_dispositivo_da_norma(self):
        r = buscar.busca(self.docs, "cesta basica")
        self.assertEqual(r[0]["id"], "lc214")
        self.assertEqual(r[0]["dispositivo"], "LC 214, art. 26")

    def test_normalizacao_acentos_e_numero(self):
        self.assertTrue(buscar.busca(self.docs, "redação dada"))
        self.assertTrue(buscar.busca(self.docs, "redacao dada"))
        self.assertTrue(buscar.busca(self.docs, '"lei complementar no 214"'))
        self.assertTrue(buscar.busca(self.docs, '"Lei Complementar nº 214"'))

    def test_filtros(self):
        self.assertEqual([x["id"] for x in buscar.busca(self.docs, "split", tipo="norma")], ["lc214"])
        self.assertEqual({x["id"] for x in buscar.busca(self.docs, "split", fonte="CGIBS")}, {"k2"})
        self.assertEqual({x["id"] for x in buscar.busca(self.docs, "split", desde="2026-10-05",
                                                        tipo="publicacao")}, {"k1"})

    def test_trecho_contem_o_termo(self):
        r = buscar.busca(self.docs, "apuração assistida")
        self.assertIn("apuração assistida", r[0]["trecho"])

    def test_nada_encontrado(self):
        self.assertEqual(buscar.busca(self.docs, "termoquenaoexiste"), [])


class TestAlteracoes(Base):
    def test_alteracao_anterior_ao_download_nao_compilada_aparece(self):
        # k1 (08/10) e' anterior ao download (10/10), mas a LC 230 nao aparece no
        # texto compilado: tem de aparecer como nao incorporada.
        r = buscar.alteracoes_de(self.docs, "lc214", artigo="26")
        k1 = next(x for x in r if x["id"] == "k1")
        self.assertIs(k1["incorporada"], False)
        self.assertIn("lei complementar no 230", k1["atos"])

    def test_alteracao_ja_compilada_marcada(self):
        r = buscar.alteracoes_de(self.docs, "lc214")
        k3 = next((x for x in r if x["id"] == "k3"), None)
        # k3 e' de janeiro: fora da janela de 30 dias antes do download
        self.assertIsNone(k3)

    def test_filtra_por_artigo(self):
        r = buscar.alteracoes_de(self.docs, "lc214", artigo="99")
        self.assertEqual(r, [])

    def test_norma_desconhecida(self):
        with self.assertRaises(KeyError):
            buscar.alteracoes_de(self.docs, "lc999")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m unittest tests.test_buscar -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'buscar'`

- [ ] **Step 3: Write minimal implementation**

`scripts/buscar.py`:
```python
#!/usr/bin/env python3
"""Busca no acervo: leis-base (normas/) + publicacoes com texto integral (dados/textos/).

Usado pelas sessoes de consulta (skill consulta-reforma). Sem indice: o
acervo (~500 textos, ~10 MB) cabe em busca linear por segundos.

Uso:
  python3 scripts/buscar.py split payment [--fonte CGIBS] [--desde 2026-09-01]
                            [--tipo norma|publicacao] [--limite 20]
  python3 scripts/buscar.py '"lei complementar nº 214"' art. 26     # aspas = frase
  python3 scripts/buscar.py --alteracoes-de lc214 [--artigo 26]

--alteracoes-de lista as publicacoes dos ultimos JANELA_ALTERACOES_DIAS dias
antes do download da compilacao (e qualquer uma depois) que mencionam a
norma; para cada uma diz se o ato que ela traz (ex.: "Lei Complementar nº
230") ja' aparece no texto compilado -- incorporada False = o Planalto
ainda nao atualizou a compilacao, leia a redacao nova na publicacao.
"""
import argparse
import datetime
import json
import re
import shlex
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textos

RAIZ = Path(__file__).resolve().parent.parent
JANELA_ALTERACOES_DIAS = 30
PESO_TITULO = 5
CONTEXTO = 180

# padroes ja' normalizados (sem acento, minusculo, "nº" -> "no")
PADRAO_NORMA = {
    "lc214": r"lei complementar n[o.]*\s*214\b|\blc\s*(n[o.]*\s*)?214\b",
    "lc227": r"lei complementar n[o.]*\s*227\b|\blc\s*(n[o.]*\s*)?227\b",
    "ec132": r"emenda constitucional n[o.]*\s*132\b|\bec\s*(n[o.]*\s*)?132\b",
    "cf-reforma": r"constituicao federal|\bart\.?\s*(156-a|156-b|195)\b",
}
ATO = re.compile(r"(lei complementar|emenda constitucional|medida provisoria|lei|decreto)"
                 r" n[o.]*\s*([\d.]+)")
ART = re.compile(r"(?m)^(?:\[NÃO VIGENTE: )?Art\. (\d+(?:-[A-Z])?)")


def normaliza(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _le_json(p, padrao):
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else padrao
    except ValueError:
        return padrao


def carrega(raiz):
    raiz = Path(raiz)
    docs = []
    for nid, m in _le_json(raiz / "normas" / "indice.json", {}).items():
        p = raiz / "normas" / f"{nid}.txt"
        if p.exists():
            docs.append({"tipo": "norma", "id": nid, "rotulo": m.get("rotulo", nid),
                         "titulo": m.get("titulo", nid), "data": (m.get("baixado_em") or "")[:10],
                         "fonte": "Planalto", "url": m.get("url", ""),
                         "caminho": f"normas/{nid}.txt", "texto": p.read_text("utf-8")})
    for k, it in _le_json(raiz / "dados" / "historico.json", {}).items():
        t = textos.le(raiz / "dados", k)
        if not t:
            continue
        docs.append({"tipo": "publicacao", "id": k, "rotulo": it.get("titulo", ""),
                     "titulo": it.get("titulo", ""), "data": it.get("data") or it.get("primeira_vez") or "",
                     "fonte": it.get("fonte", ""), "url": it.get("url", ""),
                     "caminho": f"dados/textos/{k}.txt", "texto": t})
    for d in docs:
        d["_n"], d["_nt"] = normaliza(d["texto"]), normaliza(d["titulo"])
    return docs


def _termos(consulta):
    try:
        partes = shlex.split(consulta)
    except ValueError:
        partes = consulta.split()
    return [normaliza(p) for p in partes if p.strip()]


def _dispositivo(doc, pos):
    ultimo = None
    for m in ART.finditer(doc["texto"], 0, pos + 1):
        ultimo = m.group(1)
    return f"{doc['rotulo']}, art. {ultimo}" if ultimo else doc["rotulo"]


def busca(docs, consulta, fonte=None, desde=None, tipo=None, limite=20):
    termos = _termos(consulta)
    if not termos:
        return []
    fonte_n = normaliza(fonte) if fonte else None
    out = []
    for d in docs:
        if tipo and d["tipo"] != tipo:
            continue
        if fonte_n and fonte_n not in normaliza(d["fonte"]):
            continue
        if desde and (d["data"] or "") < desde:
            continue
        if not all(t in d["_n"] or t in d["_nt"] for t in termos):
            continue
        score = sum(d["_n"].count(t) + PESO_TITULO * d["_nt"].count(t) for t in termos)
        pos = d["_n"].find(termos[0])
        pos = pos if pos >= 0 else 0
        a, b = max(0, pos - CONTEXTO), min(len(d["texto"]), pos + CONTEXTO)
        trecho = " ".join(d["texto"][a:b].split())
        out.append({"tipo": d["tipo"], "id": d["id"], "rotulo": d["rotulo"], "data": d["data"],
                    "fonte": d["fonte"], "url": d["url"], "caminho": d["caminho"],
                    "trecho": trecho,
                    "dispositivo": _dispositivo(d, pos) if d["tipo"] == "norma" else None,
                    "score": score})
    out.sort(key=lambda x: (x["tipo"] != "norma", -x["score"], x["data"] or ""), reverse=False)
    return out[:limite]


def alteracoes_de(docs, norma_id, artigo=None):
    padrao = re.compile(PADRAO_NORMA[norma_id])
    norma = next((d for d in docs if d["tipo"] == "norma" and d["id"] == norma_id), None)
    if norma is None:
        raise KeyError(f"norma {norma_id} nao carregada (rode baixar_normas.py)")
    base = datetime.date.fromisoformat(norma["data"]) - datetime.timedelta(days=JANELA_ALTERACOES_DIAS)
    art = re.compile(rf"\bart(igo)?s?\.?\s*{re.escape(artigo)}\b") if artigo else None
    out = []
    for d in docs:
        if d["tipo"] != "publicacao" or (d["data"] or "") < base.isoformat():
            continue
        if not padrao.search(d["_n"]) and not padrao.search(d["_nt"]):
            continue
        if art and not art.search(d["_n"]):
            continue
        atos = sorted({f"{m.group(1)} no {m.group(2).rstrip('.')}" for m in ATO.finditer(d["_nt"])})
        atos = [a for a in atos if not padrao.search(a)]      # a propria norma nao conta
        incorporada = None
        if atos:
            incorporada = all(re.search(re.escape(a).replace("no\\ ", r"n[o.]*\s*"), norma["_n"])
                              for a in atos)
        out.append({"id": d["id"], "titulo": d["titulo"], "data": d["data"], "fonte": d["fonte"],
                    "url": d["url"], "caminho": d["caminho"], "atos": atos,
                    "incorporada": incorporada})
    out.sort(key=lambda x: x["data"], reverse=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Busca em normas/ + dados/textos/")
    ap.add_argument("termos", nargs="*")
    ap.add_argument("--fonte")
    ap.add_argument("--desde")
    ap.add_argument("--tipo", choices=["norma", "publicacao"])
    ap.add_argument("--limite", type=int, default=20)
    ap.add_argument("--alteracoes-de")
    ap.add_argument("--artigo")
    a = ap.parse_args(argv)
    docs = carrega(RAIZ)
    if a.alteracoes_de:
        res = alteracoes_de(docs, a.alteracoes_de, a.artigo)
        norma = next(d for d in docs if d["tipo"] == "norma" and d["id"] == a.alteracoes_de)
        print(f"Compilacao de {norma['rotulo']} baixada em {norma['data']}. "
              f"{len(res)} publicacao(oes) que a mencionam:")
        for r in res:
            inc = {True: "ja' incorporada", False: "NAO INCORPORADA a compilacao", None: "sem ato identificado"}
            print(f"- {r['data']} [{r['fonte']}] {r['titulo'][:110]}\n  {inc[r['incorporada']]}"
                  f"{' (' + ', '.join(r['atos']) + ')' if r['atos'] else ''} -> {r['caminho']}")
        return 0
    res = busca(docs, " ".join(a.termos), a.fonte, a.desde, a.tipo, a.limite)
    if not res:
        print("Nada encontrado.")
    for r in res:
        cab = r["dispositivo"] if r["tipo"] == "norma" else f"{r['data']} [{r['fonte']}] {r['rotulo'][:100]}"
        print(f"- {cab}  (score {r['score']})\n  {r['caminho']}  {r['url']}\n  ...{r['trecho']}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: the `incorporada` check turns an ato like `lei complementar no 230` into a regex tolerant to `nº`/`no` in the normalized compiled text. If a test shows the replace pattern doesn't match, fix the code (keep the semantics) and note it in the report.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m unittest tests.test_buscar -v` then the full suite.
Expected: PASS

- [ ] **Step 5: Smoke against the real acervo (read-only)**

```bash
time .venv/bin/python3 scripts/buscar.py split payment --limite 5
.venv/bin/python3 scripts/buscar.py '"cesta basica"' --tipo norma --limite 3
.venv/bin/python3 scripts/buscar.py ato conjunto 8 --desde 2026-09-25 --limite 5
.venv/bin/python3 scripts/buscar.py --alteracoes-de lc214 | head -15
```
Expected: results in a few seconds; norma hits show `LC 214, art. N`; the Ato Conjunto nº 8 informe (01/10) appears. Paste outputs in the report.

- [ ] **Step 6: Commit**

```bash
git add scripts/buscar.py tests/test_buscar.py
git commit -m "feat: buscar.py busca em normas/ + acervo e detecta alteracoes nao compiladas"
```

---

### Task 3: Skill de consulta, `.gitignore`, ligação no ciclo e documentação

**Files:**
- Create: `.claude/skills/consulta-reforma/SKILL.md`
- Modify: `.gitignore`, `scripts/rodar_varredura.sh`, `CLAUDE.md`

**Interfaces:**
- Consumes: `scripts/buscar.py` CLI (Task 2), `scripts/baixar_normas.py --se-necessario` (Task 1), `normas/indice.json`.

- [ ] **Step 1: `.gitignore`**

Replace the line `.claude/` with:
```
.claude/*
!.claude/skills/
```
Verify: `git check-ignore -q .claude/worktrees/x && echo ignorado` prints `ignorado`; `git check-ignore -q .claude/skills/consulta-reforma/SKILL.md || echo versionado` prints `versionado`.

- [ ] **Step 2: Skill**

`.claude/skills/consulta-reforma/SKILL.md`:
```markdown
---
name: consulta-reforma
description: Consultor da reforma tributária do consumo (EC 132/2023, LC 214/2025, LC 227/2026 — IBS, CBS, Imposto Seletivo, split payment, regimes, transição, CGIBS, DeRE, NF-e/NFS-e, Simples) usando o acervo deste repositório (leis-base compiladas em normas/, publicações oficiais com texto integral em dados/textos/, análises diárias). Use sempre que Rodrigo perguntar sobre a reforma, sobre uma publicação, norma, artigo, prazo ou "o que mudou", ou pedir uma resposta para a Carolina.
---

# Consulta ao acervo da reforma tributária

Rodrigo é consultor da Carolina (palestrante e criadora de conteúdo sobre a reforma,
formada em ciências contábeis). Ele pergunta aqui, pelo app do Claude, e repassa a
resposta. Sua tarefa é responder **certo e com fonte** — não de memória.

## 1. Fontes, nesta ordem

1. `normas/` — leis-base em texto compilado do Planalto (`normas/indice.json` diz
   a data de cada compilação): `ec132.txt`, `cf-reforma.txt` (CF arts. 145–162 e 195;
   ADCT 124–138), `lc214.txt`, `lc227.txt`. Trecho `[NÃO VIGENTE: …]` está riscado no
   Planalto (revogado ou redação anterior): **nunca cite como vigente**.
2. `dados/textos/<chave>.txt` — texto integral das publicações coletadas duas vezes por
   dia (DOU, CGIBS, RFB, Portal NF-e, SVRS). Metadados em `dados/historico.json`;
   origem da leitura (html, pdf, pdf+ocr, inlabs…) em `dados/leituras.json`.
3. `analises/AAAA-MM-DD-<turno>.md` — análises diárias já feitas (contexto, não fonte primária).
4. `estado.json` — prazos, pendências e linha do tempo curados.
5. Web — só em último caso, e marcando `[PESQUISA]`.

Para achar: `python3 scripts/buscar.py <termos> [--tipo norma|publicacao] [--fonte X] [--desde AAAA-MM-DD]`
(aspas para frase: `'"split payment"'`). Depois **leia o arquivo** indicado (Read, com
offset/limit para os grandes — a LC 214 tem centenas de milhares de caracteres).

## 2. Atualidade — obrigatório ao citar normas/

Antes de afirmar a redação de um dispositivo de `normas/`, rode
`python3 scripts/buscar.py --alteracoes-de <ec132|lc214|lc227|cf-reforma> --artigo <N>`.
Se aparecer publicação **não incorporada à compilação**, a compilação está atrasada:
leia a publicação em `dados/textos/` e responda com a redação nova, dizendo
"compilação do Planalto de DD/MM; alterada por <ato> de DD/MM (ainda não compilada)".
Se precisar do mais recente que o último ciclo, você pode atualizar na hora:
`python3 scripts/baixar_normas.py --forcar` (ou rodar a coleta).

## 3. Marcas de confiança

- `[VERIFICADO LITERAL]` — você leu o texto integral (normas/ ou dados/textos/).
- `[VERIFICADO LITERAL (OCR)]` — idem, mas o texto veio de OCR (`origem` contém `ocr`
  em dados/leituras.json); confira números no contexto.
- `[PESQUISA]` — não veio do texto oficial (web, inferência); diga isso em uma frase.
- Nenhum número, prazo, alíquota ou artigo de memória. Se o acervo não cobre, diga que não cobre.

## 4. Tom

Direto, sem bajulação, sem "ótima pergunta". Se a premissa da pergunta está errada,
diga. Se a lei é lacunosa, contraditória ou mal escrita, diga sem rodeio. Separe o que
é texto da lei do que é interpretação.

## 5. Formato

- Resposta de trabalho para o Rodrigo: conclusão primeiro, depois o fundamento com
  citação (`LC 214, art. 26, § 1º` / publicação com data e link), marca de confiança
  e caminho do arquivo lido.
- Quando ele pedir "para a Carolina": texto técnico de contadora, pronto para enviar,
  sem caminhos de arquivo, com as fontes (dispositivo/publicação + link) no fim.

## 6. Você está numa worktree

Esta sessão roda numa worktree isolada criada a partir do `main`. Pode ler, rodar
scripts e alterar o projeto à vontade; para publicar uma mudança, faça commit e
integre ao `main` do checkout de produção com `scripts/publicar.sh` (ver CLAUDE.md).
O ciclo automático (05h/17h) é dono do checkout de produção — não edite arquivos lá.
```

- [ ] **Step 3: Ligação no ciclo**

In `scripts/rodar_varredura.sh`, between `.venv/bin/python3 scripts/ler_textos.py || rc_leitura=$?` and the following `.venv/bin/python3 scripts/gerar_painel.py`, insert:
```bash
# Leis-base (normas/): baixa de novo se a compilacao tem >= 7 dias ou se o
# ciclo coletou lei complementar / emenda / "altera a LC 214". Nao fatal:
# as normas anteriores ficam e o erro vai para dados/normas_status.json.
.venv/bin/python3 scripts/baixar_normas.py --se-necessario \
  || echo "AVISO: baixar_normas.py falhou (normas anteriores mantidas)" >&2
```
and change the second publish line to include `normas`:
```bash
scripts/publicar.sh "leitura $(date +%Y-%m-%d) ${TURNO:-}" dados docs normas
```
Run `bash -n scripts/rodar_varredura.sh`.

- [ ] **Step 4: CLAUDE.md**

Add a short section after "Os scrapers web" titled `### Consulta pelo app (normas/ + buscar.py)` stating: `normas/` holds the base laws compiled from Planalto (`scripts/baixar_normas.py`, single writer, weekly or triggered by the cycle, riscado → `[NÃO VIGENTE: …]`); `scripts/buscar.py` searches normas + dados/textos and `--alteracoes-de` flags non-compiled amendments; the project skill `.claude/skills/consulta-reforma/` (versioned via the `.gitignore` exception) is used by sessions opened from the Claude app through `reforma-consulta.service` (see docs/operacao-local.md). Add to "Commands": `python3 scripts/baixar_normas.py --se-necessario|--forcar` and `python3 scripts/buscar.py <termos> | --alteracoes-de lc214 [--artigo N]`.

- [ ] **Step 5: Verify and commit**

Run the full suite; `bash -n scripts/rodar_varredura.sh`.
```bash
git add .gitignore .claude/skills/consulta-reforma/SKILL.md scripts/rodar_varredura.sh CLAUDE.md
git commit -m "feat: skill consulta-reforma, normas no ciclo e documentacao"
```

---

### Task 4: Serviço do remote-control, limpeza de worktrees e aviso

**Files:**
- Create: `deploy/systemd/reforma-consulta.service`, `deploy/systemd/reforma-limpeza.service`, `deploy/systemd/reforma-limpeza.timer`, `scripts/limpar_worktrees.py`, `tests/test_limpar_worktrees.py`
- Modify: `scripts/notificar.py` (`--aviso`), `tests/test_notificar.py`, `docs/operacao-local.md`

**Interfaces:**
- Consumes: `notificar.monta_falha` pattern; `git worktree list --porcelain`.
- Produces:
  - `notificar.monta_aviso(mensagem: str, painel_url: str) -> dict` (same keys as `monta_falha`, `prioridade` `"default"`, `tags` `["broom"]`, título `TITULO_AVISO = "Monitor da Reforma: aviso"`); CLI `notificar.py --aviso "msg"`.
  - `limpar_worktrees.candidatas(raiz: Path, agora: float) -> tuple[list[dict], list[dict]]` → (removíveis, pendentes), each `{caminho, branch, motivo}`
  - `limpar_worktrees.main(argv=None) -> int` com `--aplicar` (sem ele, só lista)
  - Constantes `DIR_WORKTREES = ".claude/worktrees"`, `DIAS_WORKTREE = 7`, `PROTEGIDAS = {"migracao-notebook-local"}`

- [ ] **Step 1: Write the failing tests**

`tests/test_limpar_worktrees.py` (real git repos in a temp dir — no mocks):
```python
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import limpar_worktrees as lw


def git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


class TestCandidatas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name) / "repo"
        self.raiz.mkdir()
        git("init", "-q", "-b", "main", cwd=self.raiz)
        git("config", "user.email", "t@t", cwd=self.raiz)
        git("config", "user.name", "t", cwd=self.raiz)
        (self.raiz / "a.txt").write_text("a")
        git("add", ".", cwd=self.raiz)
        git("commit", "-qm", "a", cwd=self.raiz)
        self.agora = time.time() + 30 * 86400   # "daqui a 30 dias": tudo e' antigo

    def tearDown(self):
        self.tmp.cleanup()

    def wt(self, nome, base=None):
        caminho = (base or self.raiz / ".claude" / "worktrees") / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "-q", "-b", nome, str(caminho), cwd=self.raiz)
        return caminho

    def nomes(self, lista):
        return sorted(Path(x["caminho"]).name for x in lista)

    def test_remove_limpa_antiga_e_integrada(self):
        self.wt("sessao-a")
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(self.nomes(rem), ["sessao-a"])
        self.assertEqual(pend, [])

    def test_nunca_remove_com_mudanca_pendente(self):
        c = self.wt("sessao-suja")
        (c / "novo.txt").write_text("x")
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(rem, [])
        self.assertEqual(self.nomes(pend), ["sessao-suja"])

    def test_nunca_remove_com_commit_fora_do_main(self):
        c = self.wt("sessao-commit")
        (c / "b.txt").write_text("b")
        git("add", ".", cwd=c)
        git("commit", "-qm", "b", cwd=c)
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(rem, [])
        self.assertEqual(self.nomes(pend), ["sessao-commit"])

    def test_nunca_remove_recente(self):
        self.wt("sessao-nova")
        rem, pend = lw.candidatas(self.raiz, time.time())
        self.assertEqual(rem, [])

    def test_nunca_remove_protegida_nem_fora_do_diretorio(self):
        self.wt("migracao-notebook-local")
        self.wt("outra", base=Path(self.tmp.name) / "fora")
        rem, pend = lw.candidatas(self.raiz, self.agora)
        self.assertEqual(rem, [])

    def test_aplicar_remove_de_fato(self):
        c = self.wt("sessao-a")
        os.environ["LIMPAR_AGORA"] = str(self.agora)
        try:
            rc = lw.main(["--aplicar"], raiz=self.raiz, notificar=lambda m: None)
        finally:
            del os.environ["LIMPAR_AGORA"]
        self.assertEqual(rc, 0)
        self.assertFalse(c.exists())


if __name__ == "__main__":
    unittest.main()
```

Add to `tests/test_notificar.py` (inside the class that tests `monta_falha`, and next to the CLI test):
```python
    def test_aviso_prioridade_normal(self):
        msg = nt.monta_aviso("2 worktrees com trabalho pendente", PAINEL)
        self.assertEqual(msg["prioridade"], "default")
        self.assertEqual(msg["titulo"], "Monitor da Reforma: aviso")
        self.assertIn("2 worktrees", msg["corpo"])
```
and a CLI test mirroring `test_falha_cli_urgente_e_servidor_customizado` that calls `nt.main(["--aviso", "texto"], ...)` and asserts the ntfy payload priority is not `"urgent"` (read how the existing test inspects the request body and do the same).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python3 -m unittest tests.test_limpar_worktrees tests.test_notificar -v`
Expected: FAIL (`No module named 'limpar_worktrees'`, `monta_aviso` missing)

- [ ] **Step 3: Implement**

`scripts/notificar.py`: next to `TITULO_FALHA` add `TITULO_AVISO = "Monitor da Reforma: aviso"`; add
```python
def monta_aviso(mensagem, painel_url):
    corpo = _corta(mensagem or "aviso sem detalhe", LIMITE_CORPO - len(painel_url) - 2)
    return {
        "titulo": TITULO_AVISO,
        "assunto": TITULO_AVISO,
        "corpo": corpo + "\n\n" + painel_url,
        "prioridade": "default",
        "click": painel_url,
        "tags": ["broom"],
        "md": None,
    }
```
and in `main`, after the `--falha` branch: `elif argv and argv[0] == "--aviso": msg = monta_aviso(" ".join(argv[1:]), painel)`. Update the module docstring usage lines.

`scripts/limpar_worktrees.py`:
```python
#!/usr/bin/env python3
"""Limpeza semanal das worktrees das sessoes de consulta (reforma-consulta.service).

Cada sessao aberta pelo app nasce numa worktree em .claude/worktrees/. Remove
so' as que estao ao mesmo tempo: dentro de DIR_WORKTREES, fora de PROTEGIDAS,
sem mudanca pendente, sem commit fora do main e sem atividade ha'
DIAS_WORKTREE dias. Nunca usa --force. As com trabalho pendente ficam e
geram um aviso (notificar.py --aviso).

Uso: python3 scripts/limpar_worktrees.py [--aplicar]   (sem --aplicar: so' lista)
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_WORKTREES = ".claude/worktrees"
DIAS_WORKTREE = 7
PROTEGIDAS = {"migracao-notebook-local"}


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _worktrees(raiz):
    out, atual = [], {}
    for linha in _git("worktree", "list", "--porcelain", cwd=raiz).splitlines() + [""]:
        if not linha:
            if atual:
                out.append(atual)
            atual = {}
        elif linha.startswith("worktree "):
            atual["caminho"] = linha[9:]
        elif linha.startswith("branch "):
            atual["branch"] = linha[7:].removeprefix("refs/heads/")
    return out


def _ultima_atividade(caminho):
    alvos = [Path(caminho)]
    try:
        alvos.append(Path(_git("rev-parse", "--git-path", "index", cwd=caminho).strip()))
        alvos.append(Path(_git("rev-parse", "--git-path", "HEAD", cwd=caminho).strip()))
    except subprocess.CalledProcessError:
        pass
    ts = []
    for p in alvos:
        p = p if p.is_absolute() else Path(caminho) / p
        if p.exists():
            ts.append(p.stat().st_mtime)
    return max(ts) if ts else 0


def candidatas(raiz, agora):
    raiz = Path(raiz).resolve()
    base = (raiz / DIR_WORKTREES).resolve()
    remover, pendentes = [], []
    for w in _worktrees(raiz):
        c = Path(w["caminho"]).resolve()
        if c == raiz or base not in c.parents or c.name in PROTEGIDAS:
            continue
        if (agora - _ultima_atividade(c)) < DIAS_WORKTREE * 86400:
            continue
        sujo = _git("status", "--porcelain", cwd=c).strip()
        fora = _git("rev-list", "--count", f"main..{w.get('branch', 'HEAD')}", cwd=raiz).strip() \
            if w.get("branch") else "0"
        item = {"caminho": str(c), "branch": w.get("branch")}
        if sujo or fora != "0":
            item["motivo"] = "mudanca pendente" if sujo else f"{fora} commit(s) fora do main"
            pendentes.append(item)
        else:
            item["motivo"] = "limpa e integrada"
            remover.append(item)
    return remover, pendentes


def _notifica(msg):
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "notificar.py"), "--aviso", msg],
                   check=False)


def main(argv=None, raiz=RAIZ, notificar=_notifica):
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args(argv)
    agora = float(os.environ.get("LIMPAR_AGORA") or time.time())
    remover, pendentes = candidatas(raiz, agora)
    for w in remover:
        print(f"{'removendo' if a.aplicar else 'removeria'}: {w['caminho']} ({w['motivo']})")
        if a.aplicar:
            _git("worktree", "remove", w["caminho"], cwd=raiz)
            if w.get("branch"):
                _git("branch", "-d", w["branch"], cwd=raiz)
    for w in pendentes:
        print(f"mantida: {w['caminho']} ({w['motivo']})")
    if a.aplicar:
        _git("worktree", "prune", cwd=raiz)
        if pendentes:
            notificar(f"{len(pendentes)} worktree(s) de consulta com trabalho pendente: "
                      + "; ".join(f"{Path(w['caminho']).name} ({w['motivo']})" for w in pendentes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`deploy/systemd/reforma-consulta.service`:
```ini
[Unit]
Description=Reforma Tributaria - consulta pelo app do Claude (remote-control, sessoes em worktree)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=5
# Nao subiu (ex.: login do Claude expirou) -> push no celular.
OnFailure=reforma-falha@%n.service

[Service]
Type=simple
User=rodrigo
Group=rodrigo
Environment=HOME=/home/rodrigo
Environment=PATH=/home/rodrigo/.local/bin:/usr/local/bin:/usr/bin:/bin
WorkingDirectory=/home/rodrigo/projects/reforma-tributaria-monitor
# Decisao explicita do Rodrigo: sessoes sem restricao de permissao (ver
# docs/superpowers/specs/2026-10-05-consulta-remota-design.md, "Riscos").
ExecStart=/usr/local/bin/claude remote-control --name "Reforma – consulta" --spawn worktree --no-create-session-in-dir --permission-mode bypassPermissions
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`deploy/systemd/reforma-limpeza.service`:
```ini
[Unit]
Description=Reforma Tributaria - limpeza semanal das worktrees de consulta
OnFailure=reforma-falha@%n.service

[Service]
Type=oneshot
User=rodrigo
Group=rodrigo
Environment=HOME=/home/rodrigo
WorkingDirectory=/home/rodrigo/projects/reforma-tributaria-monitor
EnvironmentFile=-/home/rodrigo/projects/reforma-tributaria-monitor/.env
ExecStart=/home/rodrigo/projects/reforma-tributaria-monitor/.venv/bin/python3 scripts/limpar_worktrees.py --aplicar
```

`deploy/systemd/reforma-limpeza.timer`:
```ini
[Unit]
Description=Limpeza semanal das worktrees de consulta (domingo 03:00)

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

`docs/operacao-local.md`: add a section "Consulta pelo app do Claude" — what `reforma-consulta.service` is, how to open a session (app → Code → environment "Reforma – consulta" → new session), that each session is a worktree, the weekly cleanup, `journalctl -u reforma-consulta.service`, how to restart, the explicit `bypassPermissions` risk, and the install commands:
```bash
sudo cp deploy/systemd/reforma-consulta.service deploy/systemd/reforma-limpeza.service deploy/systemd/reforma-limpeza.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reforma-consulta.service reforma-limpeza.timer
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m unittest tests.test_limpar_worktrees tests.test_notificar -v`, then full suite. Also `systemd-analyze verify deploy/systemd/reforma-consulta.service deploy/systemd/reforma-limpeza.service deploy/systemd/reforma-limpeza.timer` (warnings about the `reforma-falha@` reference not installed in this path are acceptable; syntax errors are not). Dry-run on the real repo: `.venv/bin/python3 scripts/limpar_worktrees.py` (no `--aplicar`) and paste the output.
Expected: PASS; dry-run lists nothing destructive for `migracao-notebook-local`.

- [ ] **Step 5: Commit**

```bash
git add scripts/limpar_worktrees.py tests/test_limpar_worktrees.py scripts/notificar.py tests/test_notificar.py deploy/systemd/reforma-consulta.service deploy/systemd/reforma-limpeza.service deploy/systemd/reforma-limpeza.timer docs/operacao-local.md
git commit -m "ops: servico reforma-consulta (remote-control), limpeza semanal de worktrees e aviso"
```

---

## Rollout (controller, after merge — not a subagent task)

1. Merge into `main` (production checkout) and push via `scripts/publicar.sh --sincronizar`.
2. Stop the transient spike unit (`sudo systemctl stop rc-spike`), install units (Task 4 commands), `systemctl status reforma-consulta.service`, confirm the environment "Reforma – consulta" registers in the journal.
3. Confirm `normas/` is in `main`; run `.venv/bin/python3 scripts/buscar.py --alteracoes-de lc214 | head`.
4. Acceptance on the phone with Rodrigo (spec "Testes e aceitação", items 1–5).
