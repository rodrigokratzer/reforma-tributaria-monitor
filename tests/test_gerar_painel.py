import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gerar_painel as gp


def escreve(raiz, rel, conteudo):
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), "utf-8")
    else:
        caminho.write_text(conteudo, "utf-8")


class TestIdAnalise(unittest.TestCase):
    def test_stems_validos(self):
        self.assertEqual(gp.id_analise("2026-09-29"), ("2026-09-29", "unica"))
        self.assertEqual(gp.id_analise("2026-09-30-matinal"), ("2026-09-30", "matinal"))
        self.assertEqual(gp.id_analise("2026-09-30-noturna"), ("2026-09-30", "noturna"))

    def test_stems_invalidos(self):
        for s in ("README", "2026-09-30-tarde", "2026-9-30", "2026-13-40", "x2026-09-30"):
            self.assertIsNone(gp.id_analise(s), s)


class TestListaAnalises(unittest.TestCase):
    def test_ordem_rotulo_resumo_e_ignora_outros(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            escreve(d, "2026-09-29.md", "**Resumo antigo.**\n\nCorpo.")
            escreve(d, "2026-09-30-matinal.md", "**Manha: 3 itens.**\n\n### Seção\n\nTexto.")
            escreve(d, "2026-09-30-noturna.md", "Sem negrito na primeira linha.")
            escreve(d, "README.md", "**nao e analise**")
            escreve(d, "2026-09-28-tarde.md", "**turno invalido**")
            lista = gp.lista_analises(d)
            self.assertEqual([a["id"] for a in lista],
                             ["2026-09-30-noturna", "2026-09-30-matinal", "2026-09-29"])
            por_id = {a["id"]: a for a in lista}
            self.assertEqual(por_id["2026-09-30-matinal"]["rotulo"], "30/09/2026 · matinal")
            self.assertEqual(por_id["2026-09-29"]["rotulo"], "29/09/2026")
            self.assertEqual(por_id["2026-09-29"]["turno"], "unica")
            self.assertEqual(por_id["2026-09-30-matinal"]["data"], "2026-09-30")
            self.assertEqual(por_id["2026-09-30-matinal"]["resumo"], "Manha: 3 itens.")
            self.assertEqual(por_id["2026-09-30-noturna"]["resumo"], "")
            self.assertIn("<h3>", por_id["2026-09-30-matinal"]["html"])

    def test_pasta_inexistente(self):
        self.assertEqual(gp.lista_analises(Path("/nao/existe/mesmo")), [])


class TestAnexaTriagem(unittest.TestCase):
    def test_poe_triagem_chave_e_tira_texto(self):
        itens = {
            "aaa": {"titulo": "A", "texto": "longo", "primeira_vez": "2026-09-29"},
            "bbb": {"titulo": "B", "primeira_vez": "2026-09-28"},
        }
        triagem = {"aaa": {"veredito": "ruido", "motivo": "fora do tema", "em": "2026-09-29-matinal"}}
        out = gp.anexa_triagem(itens, triagem)
        por = {i["chave"]: i for i in out}
        self.assertEqual(por["aaa"]["triagem"]["veredito"], "ruido")
        self.assertIsNone(por["bbb"]["triagem"])
        self.assertNotIn("texto", por["aaa"])
        self.assertIn("texto", itens["aaa"])  # nao muta a entrada


class TestUltimosDias(unittest.TestCase):
    def test_tres_datas_mais_recentes(self):
        itens = [{"primeira_vez": d, "titulo": d} for d in
                 ("2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29", "2026-09-29")]
        out = gp.ultimos_dias(itens)
        self.assertEqual(sorted({i["primeira_vez"] for i in out}),
                         ["2026-09-27", "2026-09-28", "2026-09-29"])
        self.assertEqual(len(out), 4)

    def test_vazio(self):
        self.assertEqual(gp.ultimos_dias([]), [])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.orig = (gp.RAIZ, gp.DADOS, gp.ANALISES, gp.DOCS)
        gp.RAIZ, gp.DADOS, gp.ANALISES, gp.DOCS = raiz, raiz / "dados", raiz / "analises", raiz / "docs"
        self.raiz = raiz

    def tearDown(self):
        gp.RAIZ, gp.DADOS, gp.ANALISES, gp.DOCS = self.orig
        self.tmp.cleanup()

    def _payload(self):
        html = (self.raiz / "docs" / "index.html").read_text("utf-8")
        self.assertNotIn("/*__DADOS__*/null", html)
        ini = html.index("window.DADOS = ") + len("window.DADOS = ")
        fim = html.index(";\n", ini)
        return json.loads(html[ini:fim])

    def test_gera_index_e_historico(self):
        historico = {
            "k1": {"primeira_vez": "2026-09-25", "fonte": "DOU DO1", "titulo": "Velho",
                   "url": "u1", "texto": "corpo"},
            "k2": {"primeira_vez": "2026-09-27", "fonte": "CGIBS - Noticias", "titulo": "T2", "url": "u2"},
            "k3": {"primeira_vez": "2026-09-28", "fonte": "DOU DO1", "titulo": "T3", "url": "u3"},
            "k4": {"primeira_vez": "2026-09-29", "fonte": "DOU DO1", "titulo": "T4", "url": "u4",
                   "texto": "x"},
        }
        escreve(self.raiz, "dados/historico.json", historico)
        escreve(self.raiz, "dados/novidades.json", {"data": "2026-09-29", "itens": []})
        escreve(self.raiz, "dados/novidades_dou.json", {"data": "2026-09-29", "itens": [
            {"primeira_vez": "2026-09-29", "fonte": "DOU DO1", "titulo": "T4", "url": "u4",
             "texto": "x", "balde": "revisar"}]})
        escreve(self.raiz, "dados/triagem.json",
                {"k4": {"veredito": "ruido", "motivo": "m", "em": "2026-09-29-matinal"}})
        escreve(self.raiz, "analises/2026-09-29-matinal.md", "**Resumo.**\n\nTexto.")
        gp.main()

        hist = json.loads((self.raiz / "docs" / "historico.json").read_text("utf-8"))
        self.assertEqual([h["chave"] for h in hist], ["k4", "k3", "k2", "k1"])
        self.assertTrue(all("texto" not in h for h in hist))
        self.assertEqual(hist[0]["triagem"]["veredito"], "ruido")

        p = self._payload()
        for velho in ("historico", "analise_html", "analise_data"):
            self.assertNotIn(velho, p)
        self.assertEqual({h["chave"] for h in p["historico_recente"]}, {"k2", "k3", "k4"})
        self.assertEqual(p["historico_inicio"], "2026-09-25")
        self.assertEqual(p["fontes_historico"], ["CGIBS - Noticias", "DOU DO1"])
        self.assertEqual(p["analises"][0]["id"], "2026-09-29-matinal")
        nv = p["novidades"][0]
        self.assertEqual(nv["chave"], "k4")  # casada pelo historico
        self.assertEqual(nv["triagem"]["veredito"], "ruido")
        self.assertNotIn("texto", nv)

    def test_sem_nada_nao_quebra(self):
        gp.main()
        p = self._payload()
        self.assertEqual(p["analises"], [])
        self.assertEqual(p["historico_recente"], [])
        self.assertIsNone(p["historico_inicio"])
        self.assertEqual(json.loads((self.raiz / "docs" / "historico.json").read_text("utf-8")), [])


if __name__ == "__main__":
    unittest.main()
