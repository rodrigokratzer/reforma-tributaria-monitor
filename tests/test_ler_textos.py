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
