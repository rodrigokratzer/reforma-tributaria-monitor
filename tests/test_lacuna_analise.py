import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lacuna_analise as la


def escreve(raiz, rel, conteudo):
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), "utf-8")
    else:
        caminho.write_text(conteudo, "utf-8")


def item(primeira_vez, titulo, fonte="Z"):
    return {"primeira_vez": primeira_vez, "fonte": fonte, "titulo": titulo,
            "url": "https://x/" + titulo, "data": None, "pasta_arquivo": None,
            "alerta": None}


class TestIdAnalise(unittest.TestCase):
    def test_stem_so_com_data_e_turno_unica(self):
        self.assertEqual(la.id_analise("2026-09-29"), ("2026-09-29", "unica"))

    def test_stem_com_turno(self):
        self.assertEqual(la.id_analise("2026-09-30-matinal"), ("2026-09-30", "matinal"))
        self.assertEqual(la.id_analise("2026-09-30-noturna"), ("2026-09-30", "noturna"))

    def test_stems_invalidos(self):
        self.assertIsNone(la.id_analise("README"))
        self.assertIsNone(la.id_analise("2026-09-30-tarde"))
        self.assertIsNone(la.id_analise("2026-09-30-unica"))


class TestTurnoAtual(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {})
        self._env.start()
        os.environ.pop("TURNO", None)

    def tearDown(self):
        self._env.stop()

    def test_madrugada_e_matinal(self):
        self.assertEqual(la.turno_atual(datetime.datetime(2026, 9, 30, 4, 0)), "matinal")

    def test_tarde_e_noturna(self):
        self.assertEqual(la.turno_atual(datetime.datetime(2026, 9, 30, 17, 0)), "noturna")
        self.assertEqual(la.turno_atual(datetime.datetime(2026, 9, 30, 12, 0)), "noturna")

    def test_env_turno_vence(self):
        os.environ["TURNO"] = "noturna"
        self.assertEqual(la.turno_atual(datetime.datetime(2026, 9, 30, 4, 0)), "noturna")

    def test_env_turno_invalido_e_ignorado(self):
        os.environ["TURNO"] = "tarde"
        self.assertEqual(la.turno_atual(datetime.datetime(2026, 9, 30, 4, 0)), "matinal")


class TestUltimaAnalise(unittest.TestCase):
    def test_ordem_data_depois_turno(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for stem in ("2026-09-29", "2026-09-30-noturna", "2026-09-30-matinal",
                         "2026-09-28-noturna", "README"):
                escreve(raiz, f"analises/{stem}.md", "x")
            self.assertEqual(la.ultima_analise(raiz), "2026-09-30-noturna")

    def test_matinal_vence_unica_do_mesmo_dia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-09-30.md", "x")
            escreve(raiz, "analises/2026-09-30-matinal.md", "x")
            self.assertEqual(la.ultima_analise(raiz), "2026-09-30-matinal")

    def test_sem_analises_devolve_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(la.ultima_analise(Path(tmp)))


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
            self.assertEqual(la.dados_disponiveis(Path(tmp)), [])


class TestLacuna(unittest.TestCase):
    def setUp(self):
        # o turno do ambiente nao pode vazar para o resultado dos testes
        self._env = patch.dict(os.environ, {"TURNO": "matinal"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_pendentes_sao_os_nao_analisados_com_chave(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/historico.json", {
                "a": item("2026-09-28", "ta"),
                "b": item("2026-09-29", "tb"),
                "c": item("2026-09-29", "tc", fonte="A"),
            })
            escreve(raiz, "dados/analisados.json", {"chaves": ["a"]})
            r = la.lacuna(raiz, hoje="2026-09-29")
            self.assertEqual([i["chave"] for i in r["itens"]], ["c", "b"])
            self.assertEqual(r["itens"][0]["titulo"], "tc")
            self.assertEqual(r["dias_com_dados_na_janela"], ["2026-09-29"])
            self.assertEqual(r["ate"], "2026-09-29")
            self.assertEqual(r["turno"], "matinal")

    def test_sem_analisados_todos_pendentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/historico.json", {
                "a": item("2026-09-28", "ta"),
                "b": item("2026-09-29", "tb"),
            })
            r = la.lacuna(raiz, hoje="2026-09-29")
            self.assertEqual([i["chave"] for i in r["itens"]], ["a", "b"])
            self.assertEqual(r["dias_com_dados_na_janela"], ["2026-09-28", "2026-09-29"])
            self.assertIsNone(r["ultima_analise"])

    def test_segundo_ciclo_do_dia_so_ve_o_novo(self):
        # item A foi visto e analisado no ciclo das 05h; B chegou depois, no
        # mesmo dia. Com lacuna por data, B ficaria de fora (ou A voltaria).
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-09-30-matinal.md", "x")
            escreve(raiz, "dados/historico.json", {
                "A": item("2026-09-30", "tA"),
                "B": item("2026-09-30", "tB"),
            })
            escreve(raiz, "dados/analisados.json", {"chaves": ["A"]})
            os.environ["TURNO"] = "noturna"
            r = la.lacuna(raiz, hoje="2026-09-30")
            self.assertEqual([i["chave"] for i in r["itens"]], ["B"])
            self.assertEqual(r["turno"], "noturna")
            self.assertEqual(r["ultima_analise"], "2026-09-30-matinal")

    def test_item_depois_de_hoje_fica_de_fora(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/historico.json", {
                "a": item("2026-09-29", "ta"),
                "b": item("2026-10-01", "tb"),
            })
            r = la.lacuna(raiz, hoje="2026-09-30")
            self.assertEqual([i["chave"] for i in r["itens"]], ["a"])

    def test_dados_de_hoje(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/2026-09-29.json", {})
            self.assertTrue(la.lacuna(raiz, hoje="2026-09-29")["dados_de_hoje_disponiveis"])
            self.assertFalse(la.lacuna(raiz, hoje="2026-09-30")["dados_de_hoje_disponiveis"])

    def test_sem_historico_lista_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = la.lacuna(Path(tmp), hoje="2026-09-30")
            self.assertEqual(r["itens"], [])
            self.assertEqual(r["dias_com_dados_na_janela"], [])


if __name__ == "__main__":
    unittest.main()
