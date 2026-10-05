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
