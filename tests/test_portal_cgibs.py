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
        # nao levanta E recupera o texto parcial: uma tag mal fechada no
        # corpo (comum no Plone) nao pode descartar a noticia inteira.
        self.assertEqual(
            _extrai_do_html("<article><div class='artigo__texto'><p>oi"), "oi")


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
