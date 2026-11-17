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

    def test_anexa_resumo_e_cria_edicao_so_com_resumo(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            escreve(d, "2026-11-17-matinal.md", "**Reforma: nada novo.**\n\nCorpo.")
            escreve(d, "2026-11-16-noturna.md", "**Sem resumo.**")
            escreve(d, "resumos/2026-11-17-matinal.json", RESUMO)
            escreve(d, "resumos/2026-11-17-noturna.json", dict(RESUMO, manchete="Só resumo"))
            por_id = {a["id"]: a for a in gp.lista_analises(d)}
            self.assertEqual(list(por_id), ["2026-11-17-noturna", "2026-11-17-matinal", "2026-11-16-noturna"])
            self.assertEqual(por_id["2026-11-17-matinal"]["resumo"], "Reforma: nada novo.")
            self.assertEqual(por_id["2026-11-17-matinal"]["resumo_estruturado"]["manchete"], "Manchete do dia")
            self.assertIsNone(por_id["2026-11-16-noturna"]["resumo_estruturado"])
            so = por_id["2026-11-17-noturna"]
            self.assertEqual((so["html"], so["resumo"], so["turno"]), ("", "Só resumo", "noturna"))


RESUMO = {
    "data": "2026-11-17", "turno": "matinal", "manchete": "Manchete do dia",
    "em_30_segundos": ["Selic mantida.", "", 3, "Conta de luz sobe."],
    "noticias": [
        {"chave": "k9", "tema": "pessoas", "titulo": "Luz mais cara", "fonte": "g1",
         "url": "https://g1.globo.com/x", "linha": "Bandeira amarela.", "trecho": "A Aneel...",
         "por_que_importa": "R$ 1,88 a cada 100 kWh.", "ideia_post": "Quanto pesa?", "origem": "rss"},
        {"tema": "empreendedor", "titulo": "Sem URL"},
        {"tema": "esporte", "titulo": "Tema fora", "url": "https://x.com"},
        {"tema": "reforma", "titulo": "URL perigosa", "url": "javascript:alert(1)"},
        "nao e dict",
        {"chave": None, "tema": "reforma", "titulo": "Portaria", "url": "https://in.gov.br/p",
         "ideia_post": 42, "origem": "oficial"},
    ],
    "lidas": 42,
}


class TestValidaResumo(unittest.TestCase):
    def test_limpa_noticias_e_bullets(self):
        r = gp.valida_resumo(RESUMO)
        self.assertEqual(r["em_30_segundos"], ["Selic mantida.", "Conta de luz sobe."])
        self.assertEqual([n["titulo"] for n in r["noticias"]], ["Luz mais cara", "Portaria"])
        self.assertEqual(r["noticias"][0]["trecho"], "A Aneel...")
        self.assertNotIn("ideia_post", r["noticias"][1])  # nao-string some
        self.assertNotIn("chave", r["noticias"][1])
        self.assertEqual(r["lidas"], 42)

    def test_invalidos(self):
        for ruim in (None, [], "x", {}, {"em_30_segundos": [], "noticias": "x"},
                     {"em_30_segundos": "x", "noticias": []}):
            self.assertIsNone(gp.valida_resumo(ruim), ruim)

    def test_lidas_invalida_vira_none(self):
        for v in ("42", -1, True, None):
            r = gp.valida_resumo({"em_30_segundos": [], "noticias": [], "lidas": v})
            self.assertIsNone(r["lidas"], v)

    def test_lista_resumos_pula_invalidos_sem_quebrar(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            escreve(d, "2026-11-17-matinal.json", RESUMO)
            escreve(d, "2026-11-17-noturna.json", "{ json quebrado")
            escreve(d, "2026-11-16-matinal.json", ["lista"])
            escreve(d, "README.json", RESUMO)
            self.assertEqual(list(gp.lista_resumos(d)), ["2026-11-17-matinal"])
        self.assertEqual(gp.lista_resumos(Path("/nao/existe")), {})


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
        for velho in ("historico", "analise_html", "analise_data", "linha_do_tempo", "pendencias"):
            self.assertNotIn(velho, p)
        self.assertEqual({h["chave"] for h in p["historico_recente"]}, {"k2", "k3", "k4"})
        self.assertEqual(p["historico_inicio"], "2026-09-25")
        self.assertEqual(p["fontes_historico"], ["CGIBS - Noticias", "DOU DO1"])
        self.assertEqual(p["analises"][0]["id"], "2026-09-29-matinal")
        self.assertNotIn("novidades", p)  # o painel nao usa; so' inchava o html

    def test_noticias_resumo_fontes_e_tipos(self):
        escreve(self.raiz, "estado.json", {"prazos_destaque": [{"rotulo": "P", "data": "2026-12-01"}],
                                           "pendencias": [{"item": "x"}], "linha_do_tempo": [{"titulo": "y"}]})
        escreve(self.raiz, "dados/novidades.json", {"data": "2026-11-17", "itens": []})
        escreve(self.raiz, "dados/2026-11-17.json", {"fontes": [{"fonte": "CGIBS", "url": "https://c", "total": 2}]})
        escreve(self.raiz, "dados/2026-11-17-dou.json", {"fontes": [{"fonte": "DOU", "url": "https://d", "erro": "x"}]})
        escreve(self.raiz, "dados/2026-11-17-noticias.json", {"fontes": [{"fonte": "g1 Economia", "url": "https://g", "total": 5}]})
        escreve(self.raiz, "dados/novidades_noticias.json", {"data": "2026-11-17", "itens": [
            {"primeira_vez": "2026-11-17", "fonte": "g1 Economia", "tipo": "noticia", "titulo": "N1", "url": "https://g/1"}]})
        escreve(self.raiz, "dados/historico.json", {
            "n1": {"primeira_vez": "2026-11-17", "fonte": "g1 Economia", "tipo": "noticia", "titulo": "N1", "url": "https://g/1"},
            "p1": {"primeira_vez": "2026-11-17", "fonte": "DOU", "titulo": "P1", "url": "https://d/1"}})
        escreve(self.raiz, "dados/estado_mudancas.json", [
            {"secao": "linha_do_tempo", "descricao": "fora"}, {"secao": "prazos_destaque", "descricao": "dentro"}])
        escreve(self.raiz, "analises/2026-11-17-matinal.md", "**Reforma.**")
        escreve(self.raiz, "analises/resumos/2026-11-17-matinal.json", RESUMO)
        escreve(self.raiz, "analises/resumos/2026-11-17-noturna.json", {"quebrado": True})
        gp.main()
        p = self._payload()
        self.assertNotIn("linha_do_tempo", p)
        self.assertNotIn("pendencias", p)
        self.assertEqual(len(p["prazos_destaque"]), 1)
        self.assertEqual([(f["fonte"], f["grupo"]) for f in p["fontes"]],
                         [("CGIBS", "web"), ("DOU", "dou"), ("g1 Economia", "noticias")])
        self.assertEqual(p["tipos_historico"], {"noticia": 1, "publicacao": 1})
        self.assertIn("g1 Economia", p["fontes_historico"])
        self.assertEqual([m["descricao"] for m in p["estado_mudancas"]], ["dentro"])
        self.assertEqual([a["id"] for a in p["analises"]], ["2026-11-17-matinal"])
        re_ = p["analises"][0]["resumo_estruturado"]
        self.assertEqual(re_["lidas"], 42)
        self.assertEqual(len(re_["noticias"]), 2)

    def test_sem_nada_nao_quebra(self):
        gp.main()
        p = self._payload()
        self.assertEqual(p["analises"], [])
        self.assertEqual(p["historico_recente"], [])
        self.assertIsNone(p["historico_inicio"])
        self.assertEqual(json.loads((self.raiz / "docs" / "historico.json").read_text("utf-8")), [])



class TestUltimasMudancas(unittest.TestCase):
    def test_corta_e_ignora_lixo(self):
        hist = [{"descricao": str(i)} for i in range(20)] + ["x", {"sem": "descricao"}]
        self.assertEqual(len(gp.ultimas_mudancas(hist)), 12)
        self.assertEqual(gp.ultimas_mudancas(hist)[0]["descricao"], "0")

    def test_arquivo_ausente_ou_invalido(self):
        self.assertEqual(gp.ultimas_mudancas({}), [])
        self.assertEqual(gp.ultimas_mudancas([]), [])
if __name__ == "__main__":
    unittest.main()
