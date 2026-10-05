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
            "k5": {"titulo": "LEI COMPLEMENTAR Nº 237, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-10-09", "url": "u5", "primeira_vez": "2026-10-09"},
            "k6": {"titulo": "LEI Nº 15.504, DE 10 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-10-10", "url": "u6", "primeira_vez": "2026-10-10"},
            "k7": {"titulo": "LEI COMPLEMENTAR Nº 227, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-10-09", "url": "u7", "primeira_vez": "2026-10-09"},
            "k8": {"titulo": "LEI COMPLEMENTAR Nº 214, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-10-09", "url": "u8", "primeira_vez": "2026-10-09"},
            "k9": {"titulo": "LEI COMPLEMENTAR Nº 214, DE 9 DE SETEMBRO DE 2026", "fonte": "DOU DO1",
                   "data": "2026-09-09", "url": "u9", "primeira_vez": "2026-09-09"},
            "k10": {"titulo": "RESOLUÇÃO CGSN Nº 194, DE 25 DE SETEMBRO DE 2026", "fonte": "DOU DO1E",
                    "data": "2026-09-28", "url": "u10", "primeira_vez": "2026-09-28"},
            "k11": {"titulo": "LEI Nº 15.999, DE 15 DE SETEMBRO DE 2026", "fonte": "DOU DO1E",
                    "data": "2026-09-15", "url": "u11", "primeira_vez": "2026-09-15"},
            "k12": {"titulo": "LEI COMPLEMENTAR Nº 237, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                    "data": "2026-10-09", "url": "u12", "primeira_vez": "2026-10-09"},
            "k13": {"titulo": "LEI COMPLEMENTAR Nº 227, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                    "data": "2026-10-09", "url": "u13", "primeira_vez": "2026-10-09"},
            "k14": {"titulo": "LEI COMPLEMENTAR Nº 227, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                    "data": "2026-10-09", "url": "u14", "primeira_vez": "2026-10-09"},
            "k15": {"titulo": "LEI COMPLEMENTAR Nº 227, DE 9 DE OUTUBRO DE 2026", "fonte": "DOU DO1",
                    "data": "2026-10-09", "url": "u15", "primeira_vez": "2026-10-09"},
        }
        (r / "dados" / "historico.json").write_text(json.dumps(hist), "utf-8")
        textos.grava(r / "dados", "k1", "Altera o art. 26 da Lei Complementar nº 214, de 2025, "
                                        "que passa a vigorar com nova redação sobre split payment.")
        textos.grava(r / "dados", "k2", "Dispõe sobre o split payment e a apuração assistida do IBS.")
        textos.grava(r / "dados", "k3", "Altera a LC 214 em diversos artigos, inclusive o art. 26.")
        # k5: LC 237 alters LC 229, mentions LC 214 only in quoted text (should be in mencoes only)
        textos.grava(r / "dados", "k5",
                     "Altera a Lei Complementar nº 229, de 2026. Parágrafo único: \"Esta lei respeita "
                     "o disposto na Lei Complementar nº 214, de forma que não há conflito com o regime "
                     "de que trata a Lei Complementar nº 214\".")
        # k6: Lei 15.504 alters Lei 11.196, mentions LC 214 only in background (should not appear)
        textos.grava(r / "dados", "k6",
                     "Altera a Lei nº 11.196, de 2005. Art. 1º Observado o disposto na Lei Complementar "
                     "nº 214, fica alterado o regime de tributação da Lei nº 11.196.")
        # k7: LC 227 title (in window), text explicitly alters LC 214 (Form A)
        textos.grava(r / "dados", "k7",
                     "Altera a Lei Complementar nº 214, de 16 de janeiro de 2025, em diversos artigos. "
                     "Art. 1º Fica alterado o art. 25 da Lei Complementar nº 214.")
        # k8: This is inside window, text just says it passes to work with changes (Form B)
        textos.grava(r / "dados", "k8",
                     "A Lei Complementar nº 214, de 16 de janeiro de 2025, passa a vigorar com as "
                     "seguintes alterações: Art. 1º O art. 28 passa a ter nova redação.")
        # k9: Outside 30-day window before 2026-10-10 download
        textos.grava(r / "dados", "k9",
                     "Altera o art. 26 da Lei Complementar nº 214, de 2025, que passa a vigorar com "
                     "nova redação.")
        # k10: Resolução CGSN - references LC 214 but "passa a vigorar" is for Resolução 186, not LC 214
        # Should NOT be an amendment (Resolução cannot amend Lei Complementar by hierarchy)
        textos.grava(r / "dados", "k10",
                     "Altera a Resolução CGSN nº 186, de 9 de abril de 2026. Art. 1º No art. 41, §3o "
                     "e §4o, da lei complementar no 214, de 16 de janeiro de 2025, resolve: art. 1o a "
                     "resolucao cgsn no 186, de 9 de abril de 2026, passa a vigorar com as seguintes "
                     "alteracoes.")
        # k11: Lei ordinária (Lei nº 15.999) says it alters LC 214 - but hierarchy check should reject it
        textos.grava(r / "dados", "k11",
                     "Altera a Lei Complementar nº 214, de 16 de janeiro de 2025. Esta Lei ordinária "
                     "não pode alterar Lei Complementar por questão de hierarquia normativa.")
        # k12: Typographic quotes - text mentions LC 214 inside curly quotes (U+201C/U+201D)
        # Should NOT be an amendment, should be in mencoes only
        textos.grava(r / "dados", "k12",
                     "A Lei Complementar nº 229, de 2026, passa a vigorar com a seguinte redação:\n"
                     "\u201cArt. 3º ... altera a Lei Complementar nº 214, de 2025.\u201d")
        # k13: Real amendment - LC 227 whose title act (Lei Complementar nº 227)
        # DOES appear in LC 214 compiled text ("Redação dada pela Lei Complementar nº 227, de 2026")
        # Should be incorporada=True
        textos.grava(r / "dados", "k13",
                     "Altera a Lei Complementar nº 214, de 16 de janeiro de 2025, em diversos artigos. "
                     "Art. 1º Fica alterado o art. 26 da Lei Complementar nº 214.")
        # k14: Article boundary test - contains "art. 26-A" but searching for "26" should NOT match
        textos.grava(r / "dados", "k14",
                     "Altera o art. 26 da Lei Complementar nº 214. Art. 26-A Novo artigo adicionado.")
        # k15: LC 214/2025 shorthand (no "nº") - should still detect as amendment
        textos.grava(r / "dados", "k15",
                     "Altera o art. 5º da LC 214/2025 que passa a vigorar com nova redação.")
        self.docs = buscar.carrega(r)

    def tearDown(self):
        self.tmp.cleanup()


class TestCarrega(Base):
    def test_normas_e_publicacoes_com_texto(self):
        tipos = sorted((d["tipo"], d["id"]) for d in self.docs)
        # k4 has no text, k5-k9 are added by new tests
        self.assertIn(("norma", "lc214"), tipos)
        self.assertIn(("publicacao", "k1"), tipos)
        self.assertIn(("publicacao", "k2"), tipos)
        self.assertIn(("publicacao", "k3"), tipos)
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
        ids = {x["id"] for x in r}
        self.assertIn("k1", ids)
        k1 = next(x for x in r if x["id"] == "k1")
        self.assertIs(k1["incorporada"], False)

    def test_fora_da_janela_excluida(self):
        r = buscar.alteracoes_de(self.docs, "lc214")
        k9_ids = {x["id"] for x in r}
        # k9 e' de setembro: fora da janela de 30 dias antes do download
        self.assertNotIn("k9", k9_ids)

    def test_citacao_entre_aspas_nao_e_alteracao(self):
        # k5: LC 237 alters LC 229, mentions LC 214 only in quoted text
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertNotIn("k5", {x["id"] for x in r})

    def test_mencao_em_contexto_nao_e_alteracao(self):
        # k6: Lei 15.504 alters Lei 11.196, mentions LC 214 only in background context
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertNotIn("k6", {x["id"] for x in r})

    def test_alteracao_com_verbo_direto(self):
        # k7: LC 227 explicitly alters LC 214 (Form A - has verb + norm ref in window)
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertIn("k7", {x["id"] for x in r})

    def test_alteracao_com_passa_a_vigorar(self):
        # k8: LC 214 "passa a vigorar com as seguintes alterações" (Form B)
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertIn("k8", {x["id"] for x in r})

    def test_filtra_por_artigo_com_lista(self):
        # Test that "arts. 25 e 26" matches artigo "26"
        r = buscar.alteracoes_de(self.docs, "lc214", artigo="26")
        ids = {x["id"] for x in r}
        self.assertIn("k1", ids)
        # k8 alters art. 28, not 26
        self.assertNotIn("k8", ids)

    def test_filtra_por_artigo_inexistente(self):
        r = buscar.alteracoes_de(self.docs, "lc214", artigo="99")
        self.assertEqual(r, [])

    def test_norma_desconhecida_cli_error(self):
        with self.assertRaises(KeyError):
            buscar.alteracoes_de(self.docs, "lc999")

    def test_alteracao_tem_trecho(self):
        r = buscar.alteracoes_de(self.docs, "lc214", artigo="26")
        k1 = next(x for x in r if x["id"] == "k1")
        self.assertIn("trecho", k1)
        self.assertTrue(k1["trecho"])  # non-empty

    def test_resolucao_nao_altera_lei_complementar(self):
        # k10: Resolução CGSN nº 194 - "passa a vigorar" is for Resolução 186, not LC 214
        # Hierarchy: Resolução cannot amend Lei Complementar, even if it mentions LC 214
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertNotIn("k10", {x["id"] for x in r})

    def test_lei_ordinaria_nao_altera_lei_complementar(self):
        # k11: Lei ordinária nº 15.999 - hierarchy rule: Lei ordinária cannot amend Lei Complementar
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertNotIn("k11", {x["id"] for x in r})


class TestMencoes(Base):
    def test_mencoes_de_lista_citacoes_nao_alteracoes(self):
        # k5 and k6 should be in mencoes, not in alteracoes
        r = buscar.mencoes_de(self.docs, "lc214")
        ids = {x["id"] for x in r}
        self.assertIn("k5", ids)
        self.assertIn("k6", ids)

    def test_alteracoes_nao_sao_mencoes(self):
        # k1, k7, k8 are alterations, should NOT be in mencoes
        r = buscar.mencoes_de(self.docs, "lc214")
        ids = {x["id"] for x in r}
        self.assertNotIn("k1", ids)
        self.assertNotIn("k7", ids)
        self.assertNotIn("k8", ids)

    def test_mencoes_sem_incorporada(self):
        r = buscar.mencoes_de(self.docs, "lc214")
        for m in r:
            self.assertNotIn("incorporada", m)

    def test_resolucao_aparece_em_mencoes(self):
        # k10: Resolução CGSN that mentions LC 214 but passes a vigorar for itself
        r = buscar.mencoes_de(self.docs, "lc214")
        self.assertIn("k10", {x["id"] for x in r})

    def test_lei_ordinaria_aparece_em_mencoes(self):
        # k11: Lei ordinária that mentions LC 214 (hierarchy prevents it from being amendment)
        r = buscar.mencoes_de(self.docs, "lc214")
        self.assertIn("k11", {x["id"] for x in r})


class TestTypographicQuotes(Base):
    def test_tipograficas_nao_e_alteracao(self):
        # k12: Typographic quotes (not ASCII quotes) contain text about LC 214
        # Should NOT be treated as amendment, should be in mencoes
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertNotIn("k12", {x["id"] for x in r})

    def test_tipograficas_aparece_em_mencoes(self):
        # k12 should appear in mencoes, not alteracoes
        r = buscar.mencoes_de(self.docs, "lc214")
        self.assertIn("k12", {x["id"] for x in r})


class TestIncorporada(Base):
    def test_incorporada_true_quando_ato_no_texto(self):
        # k13: LC 227 alters LC 214, and "Lei Complementar nº 227" appears in LC 214 compiled text
        # Should be incorporada=True
        r = buscar.alteracoes_de(self.docs, "lc214")
        k13 = next((x for x in r if x["id"] == "k13"), None)
        self.assertIsNotNone(k13)
        self.assertIs(k13["incorporada"], True)


class TestArticleWordBoundary(Base):
    def test_artigo_26_nao_match_26_a(self):
        # k14: Contains both "art. 26" and "art. 26-A"
        # Filtering by artigo="26" should NOT match "26-A"
        r = buscar.alteracoes_de(self.docs, "lc214", artigo="26")
        # k14 should be found (has art. 26)
        self.assertIn("k14", {x["id"] for x in r})


class TestLCShorthand(Base):
    def test_lc_214_2025_shorthand_detected(self):
        # k15: Uses "LC 214/2025" shorthand without "nº"
        # Should still be detected as amendment
        r = buscar.alteracoes_de(self.docs, "lc214")
        self.assertIn("k15", {x["id"] for x in r})


if __name__ == "__main__":
    unittest.main()
