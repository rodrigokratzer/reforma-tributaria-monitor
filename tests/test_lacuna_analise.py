import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lacuna_analise as la


def escreve(raiz, rel, conteudo):
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), "utf-8")
    else:
        caminho.write_text(conteudo, "utf-8")


class TestDataUltimaAnalise(unittest.TestCase):
    def test_sem_analises_devolve_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "analises").mkdir()
            self.assertIsNone(la.data_ultima_analise(raiz))

    def test_pasta_inexistente_devolve_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self.assertIsNone(la.data_ultima_analise(raiz))

    def test_pega_a_mais_recente(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-17.md", "x")
            escreve(raiz, "analises/2026-08-20.md", "x")
            escreve(raiz, "analises/2026-08-05.md", "x")
            self.assertEqual(la.data_ultima_analise(raiz), "2026-08-20")

    def test_ignora_arquivo_sem_nome_de_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-17.md", "x")
            escreve(raiz, "analises/README.md", "x")
            self.assertEqual(la.data_ultima_analise(raiz), "2026-08-17")


class TestDadosDisponiveis(unittest.TestCase):
    def test_lista_apenas_arquivos_com_nome_de_data_ordenados(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/2026-08-20.json", {})
            escreve(raiz, "dados/2026-08-18.json", {})
            escreve(raiz, "dados/historico.json", {})
            escreve(raiz, "dados/novidades.json", {})
            self.assertEqual(la.dados_disponiveis(raiz),
                              ["2026-08-18", "2026-08-20"])

    def test_pasta_inexistente_devolve_lista_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self.assertEqual(la.dados_disponiveis(raiz), [])


class TestItensDaLacuna(unittest.TestCase):
    def _historico(self, raiz):
        escreve(raiz, "dados/historico.json", {
            "a": {"primeira_vez": "2026-08-18", "fonte": "Z", "titulo": "item 18",
                  "url": "https://x/18", "data": None, "pasta_arquivo": None, "alerta": None},
            "b": {"primeira_vez": "2026-08-19", "fonte": "A", "titulo": "item 19",
                  "url": "https://x/19", "data": None, "pasta_arquivo": None, "alerta": None},
            "c": {"primeira_vez": "2026-08-20", "fonte": "M", "titulo": "item 20",
                  "url": "https://x/20", "data": None, "pasta_arquivo": None, "alerta": None},
            "d": {"primeira_vez": "2026-08-17", "fonte": "M", "titulo": "item 17 (antigo)",
                  "url": "https://x/17", "data": None, "pasta_arquivo": None, "alerta": None},
        })

    def test_filtra_janela_desde_exclusivo_ate_inclusivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._historico(raiz)
            itens = la.itens_da_lacuna(raiz, desde="2026-08-17", ate="2026-08-19")
            titulos = [i["titulo"] for i in itens]
            self.assertEqual(titulos, ["item 18", "item 19"])

    def test_sem_desde_pega_tudo_ate_a_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._historico(raiz)
            itens = la.itens_da_lacuna(raiz, desde=None, ate="2026-08-19")
            titulos = [i["titulo"] for i in itens]
            self.assertEqual(titulos, ["item 17 (antigo)", "item 18", "item 19"])

    def test_sem_historico_devolve_lista_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "dados").mkdir()
            self.assertEqual(la.itens_da_lacuna(raiz, desde=None, ate="2026-08-19"), [])


class TestLacuna(unittest.TestCase):
    def test_dados_de_hoje_ausentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-20.md", "x")
            escreve(raiz, "dados/2026-08-21.json", {})
            escreve(raiz, "dados/historico.json", {})
            resultado = la.lacuna(raiz, hoje="2026-08-25")
            self.assertFalse(resultado["dados_de_hoje_disponiveis"])
            self.assertEqual(resultado["desde"], "2026-08-20")

    def test_lacuna_de_varios_dias_pulados(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-20.md", "x")
            for dia in ("2026-08-21", "2026-08-24", "2026-08-25"):
                escreve(raiz, f"dados/{dia}.json", {})
            escreve(raiz, "dados/historico.json", {
                "a": {"primeira_vez": "2026-08-21", "fonte": "Z", "titulo": "t21",
                      "url": "u", "data": None, "pasta_arquivo": None, "alerta": None},
                "b": {"primeira_vez": "2026-08-25", "fonte": "Z", "titulo": "t25",
                      "url": "u", "data": None, "pasta_arquivo": None, "alerta": None},
            })
            resultado = la.lacuna(raiz, hoje="2026-08-25")
            self.assertTrue(resultado["dados_de_hoje_disponiveis"])
            self.assertEqual(resultado["dias_com_dados_na_janela"],
                              ["2026-08-21", "2026-08-24", "2026-08-25"])
            self.assertEqual([i["titulo"] for i in resultado["itens"]], ["t21", "t25"])


if __name__ == "__main__":
    unittest.main()
