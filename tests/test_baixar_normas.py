import datetime
import json
import sys
import tempfile
import unittest
from unittest import mock
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

    def test_quebra_de_linha_no_fonte_html_nao_parte_o_artigo(self):
        # caso real (lcp214.htm): o fonte quebra linhas no meio do paragrafo
        t = bn.html_para_texto("<p>Art. 26.\nNão são contribuintes do IBS,\nressalvado o disposto.</p>"
                               "<p><strike>§ 9º\nAplica-se o disposto\nno § 8º. </strike></p>")
        self.assertIn("Art. 26. Não são contribuintes do IBS, ressalvado o disposto.", t)
        self.assertIn("[NÃO VIGENTE: § 9º Aplica-se o disposto no § 8º.]", t)

    def test_riscado_por_css_line_through(self):
        # caso real (lcp214.htm): revogado marcado por estilo, nao por <strike>
        t = bn.html_para_texto(
            '<p><span style="font-family: Arial,sans-serif; text-decoration:line-through">'
            '<font size="2">§ 4º O IBS e a CBS incidem sobre qualquer operação…</font></span></p>'
            '<p>§ 4º Novo texto vigente.</p>')
        self.assertIn("[NÃO VIGENTE: § 4º O IBS e a CBS incidem sobre qualquer operação…]", t)
        self.assertRegex(t, r"(?m)^§ 4º Novo texto vigente\.$")

    def test_css_aninhado_equilibra_e_nao_vaza(self):
        t = bn.html_para_texto(
            '<p><span style="TEXT-DECORATION: Line-Through"><font><b>x</b></font></span> depois</p>'
            '<p>proximo paragrafo</p><p><span><b>y</b></span> neutro</p>')
        self.assertIn("[NÃO VIGENTE: x] depois", t)
        self.assertRegex(t, r"(?m)^proximo paragrafo$")
        self.assertRegex(t, r"(?m)^y neutro$")

    def test_css_em_celula_de_tabela_e_span_interno_comum(self):
        t = bn.html_para_texto(
            '<table><tr><td style="text-decoration:line-through"><span>a</span> b<br>c</td>'
            '<td>vigente</td></tr></table>')
        self.assertIn("[NÃO VIGENTE: a b]", t)
        self.assertIn("[NÃO VIGENTE: c]", t)
        self.assertRegex(t, r"(?m)^vigente$")

    def test_salvaguarda_levanta_se_ha_riscado_e_nenhuma_marca(self):
        # simula marcacao nao reconhecida: parser que ignora <strike>
        class FakeSessao1:
            def baixa(self, url):
                return baixar.Resposta(b"<p>Art. 1\xba a</p><p><strike>Art. 2\xba b</strike></p>",
                                       "text/html", None, url)
        norma = dict(bn.NORMAS[0], minimo_artigos=1)
        with mock.patch.object(bn._Texto, "RISCO", set()):
            with self.assertRaises(bn.ErroNorma):
                bn.baixa_norma(FakeSessao1(), norma)
        texto, raw, marcas = bn.baixa_norma(FakeSessao1(), norma)   # sem o patch passa
        self.assertEqual((raw, marcas), (1, 1))

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

    def test_corpo_citando_lc214_nao_dispara(self):
        nov = [{"titulo": "Portaria qualquer",
                "texto": "Altera a Lei Complementar nº 214, de 2025; Lei Complementar nº 227"}]
        self.assertFalse(bn.precisa_atualizar(self.indice(1), nov, self.HOJE)[0])

    def test_gatilho_so_pelo_inicio_do_titulo(self):
        nov = [{"titulo": "Regulamenta a Lei Complementar nº 214", "texto": ""}]
        self.assertFalse(bn.precisa_atualizar(self.indice(1), nov, self.HOJE)[0])
        nov = [{"titulo": "LEI COMPLEMENTAR Nº 240, DE 1º DE OUTUBRO DE 2026", "texto": ""}]
        self.assertTrue(bn.precisa_atualizar(self.indice(1), nov, self.HOJE)[0])
        nov = [{"titulo": "Emenda Constitucional nº 140, de 2026", "texto": ""}]
        self.assertTrue(bn.precisa_atualizar(self.indice(1), nov, self.HOJE)[0])

    def test_idade_usa_verificado_em(self):
        ver = {n["id"]: {"verificado_em": "2026-10-19T08:00:00Z"} for n in bn.NORMAS}
        self.assertFalse(bn.precisa_atualizar(self.indice(30), [], self.HOJE, ver)[0])
        ver["lc214"] = {"verificado_em": "2026-10-10T08:00:00Z"}
        self.assertTrue(bn.precisa_atualizar(self.indice(30), [], self.HOJE, ver)[0])
        # sem verificado_em cai no baixado_em
        self.assertTrue(bn.precisa_atualizar(self.indice(30), [], self.HOJE, {})[0])

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

    def _le(self, rel):
        return (self.raiz / rel).read_bytes()

    def test_conteudo_igual_nao_reescreve_arquivo_nem_indice(self):
        bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        txt, idx = self._le("normas/lc214.txt"), self._le("normas/indice.json")
        st1 = json.loads(self._le("dados/normas_status.json"))
        with mock.patch.object(bn, "_agora", return_value="2030-01-01T00:00:00Z"):
            bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        self.assertEqual(self._le("normas/lc214.txt"), txt)
        self.assertEqual(self._le("normas/indice.json"), idx)
        st = json.loads(self._le("dados/normas_status.json"))
        self.assertEqual(st["normas"]["lc214"]["verificado_em"], "2030-01-01T00:00:00Z")
        self.assertNotEqual(st["normas"]["lc214"]["verificado_em"],
                            st1["normas"]["lc214"]["verificado_em"])

    def test_conteudo_diferente_reescreve_e_atualiza_baixado_em(self):
        bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        lc = next(n for n in bn.NORMAS if n["id"] == "lc214")
        novo = dict(self.paginas, **{lc["url"]: HTML_LC.replace("Redação nova", "Redação novíssima")})
        with mock.patch.object(bn, "_agora", return_value="2030-01-01T00:00:00Z"):
            bn.executa(self.raiz, forcar=True, sessao=FakeSessao(novo))
        idx = json.loads(self._le("normas/indice.json"))
        self.assertEqual(idx["lc214"]["baixado_em"], "2030-01-01T00:00:00Z")
        self.assertIn("novíssima", self._le("normas/lc214.txt").decode("utf-8"))

    def test_sem_necessidade_preserva_verificado_em(self):
        with mock.patch.object(bn, "_agora", return_value="2026-10-20T00:00:00Z"):
            bn.executa(self.raiz, forcar=True, sessao=FakeSessao(self.paginas))
        bn.executa(self.raiz, forcar=False, sessao=FakeSessao({}), hoje=datetime.date(2026, 10, 21))
        st = json.loads(self._le("dados/normas_status.json"))
        self.assertEqual(st["resultado"], "sem_necessidade")
        self.assertEqual(st["normas"]["lc214"]["verificado_em"], "2026-10-20T00:00:00Z")

    def test_falha_nao_marca_verificado(self):
        lc = next(n for n in bn.NORMAS if n["id"] == "lc214")
        quebrado = dict(self.paginas, **{lc["url"]: "<html><body>manutenção</body></html>"})
        bn.executa(self.raiz, forcar=True, sessao=FakeSessao(quebrado))
        st = json.loads(self._le("dados/normas_status.json"))
        self.assertNotIn("lc214", st["normas"])
        self.assertIn("lc227", st["normas"])


if __name__ == "__main__":
    unittest.main()
