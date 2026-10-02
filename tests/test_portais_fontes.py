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
