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
