import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import fechar_analise as fa


def escreve(raiz, rel, conteudo):
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), "utf-8")
    else:
        caminho.write_text(conteudo, "utf-8")


def le(raiz, rel):
    return json.loads((raiz / rel).read_text("utf-8"))


def prepara(raiz, md=True, status_turno="noturna"):
    escreve(raiz, "dados/historico.json", {
        "a": {"primeira_vez": "2026-09-30", "titulo": "ta"},
        "b": {"primeira_vez": "2026-09-30", "titulo": "tb"},
        "c": {"primeira_vez": "2026-09-30", "titulo": "tc"},
    })
    escreve(raiz, "dados/analisados.json", {"chaves": ["z"]})
    escreve(raiz, "dados/analise_status.json",
            {"data": "2026-09-30", "turno": status_turno, "situacao": "publicada"})
    if md:
        escreve(raiz, "analises/2026-09-30-noturna.md", "# Analise\n\ntexto\n")


class TestFechar(unittest.TestCase):
    def test_fechar_sem_arquivo_falha_e_nao_marca(self):
        # analise que nao produziu arquivo (limite de uso, recusa): os itens
        # tem que continuar pendentes para o proximo ciclo
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz, md=False)
            escreve(raiz, "dados/triagem_pendente.json",
                    [{"chave": "a", "veredito": "ruido", "motivo": "m"}])
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a", "b"])
            self.assertFalse(r["ok"])
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["z"]})
            self.assertFalse((raiz / "dados/triagem.json").exists())
            self.assertTrue((raiz / "dados/triagem_pendente.json").exists())

    def test_fechar_arquivo_vazio_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz, md=False)
            escreve(raiz, "analises/2026-09-30-noturna.md", "  \n")
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertFalse(r["ok"])
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["z"]})

    def test_fechar_status_de_outro_turno_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz, status_turno="matinal")
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertFalse(r["ok"])
            self.assertIn("turno", r["motivo"])
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["z"]})

    def test_fechar_sem_status_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            (raiz / "dados/analise_status.json").unlink()
            self.assertFalse(fa.fechar(raiz, "2026-09-30", "noturna", ["a"])["ok"])

    def test_fechar_ok_marca_chaves_e_triagem(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "dados/triagem.json",
                    {"c": {"veredito": "contexto", "motivo": "velho", "em": "2026-09-30-matinal"}})
            escreve(raiz, "dados/triagem_pendente.json", [
                {"chave": "a", "veredito": "relevante", "motivo": "cita LC 214"},
                {"chave": "b", "veredito": "ruido", "motivo": "nomeacao"},
            ])
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["b", "a", "a"])
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["triados"], 2)
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["a", "b", "z"]})
            self.assertEqual(le(raiz, "dados/triagem.json"), {
                "a": {"veredito": "relevante", "motivo": "cita LC 214", "em": "2026-09-30-noturna"},
                "b": {"veredito": "ruido", "motivo": "nomeacao", "em": "2026-09-30-noturna"},
                "c": {"veredito": "contexto", "motivo": "velho", "em": "2026-09-30-matinal"},
            })
            self.assertFalse((raiz / "dados/triagem_pendente.json").exists())

    def test_triagem_ignora_linhas_invalidas(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "dados/triagem_pendente.json", [
                {"chave": "a", "veredito": "talvez", "motivo": "x"},
                {"chave": "inexistente", "veredito": "ruido", "motivo": "x"},
                "nem e' objeto",
                {"veredito": "ruido"},
                {"chave": "b", "veredito": "contexto", "motivo": "ok"},
                {"chave": "c", "veredito": "ruido"},
            ])
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a", "b", "c"])
            self.assertTrue(r["ok"])
            self.assertEqual(r["triados"], 2)
            triagem = le(raiz, "dados/triagem.json")
            self.assertEqual(sorted(triagem), ["b", "c"])
            self.assertEqual(triagem["c"]["motivo"], "")

    def test_triagem_pendente_que_nao_e_lista_e_ignorada(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "dados/triagem_pendente.json", {"a": "relevante"})
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertTrue(r["ok"])
            self.assertEqual(r["triados"], 0)
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["a", "z"]})

    def test_triagem_pendente_json_quebrado_e_ignorado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "dados/triagem_pendente.json", "[{quebrado")
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertTrue(r["ok"])
            self.assertEqual(r["triados"], 0)

    def test_sem_triagem_pendente_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            (raiz / "dados/analisados.json").unlink()
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["c"])
            self.assertTrue(r["ok"])
            self.assertEqual(r["triados"], 0)
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["c"]})
            self.assertEqual(le(raiz, "dados/triagem.json"), {})


class TestCli(unittest.TestCase):
    def _roda(self, raiz, *args):
        with patch.object(fa, "RAIZ", raiz), \
                contextlib.redirect_stdout(io.StringIO()):
            return fa.main(list(args))

    def test_cli_le_chaves_do_arquivo_da_lacuna(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            lac = raiz / "lacuna.json"
            lac.write_text(json.dumps({"itens": [{"chave": "a"}, {"chave": "b"}]}), "utf-8")
            self.assertEqual(self._roda(raiz, "2026-09-30", "noturna", str(lac)), 0)
            self.assertEqual(le(raiz, "dados/analisados.json"), {"chaves": ["a", "b", "z"]})

    def test_cli_sai_1_quando_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz, md=False)
            lac = raiz / "lacuna.json"
            lac.write_text(json.dumps({"itens": [{"chave": "a"}]}), "utf-8")
            self.assertEqual(self._roda(raiz, "2026-09-30", "noturna", str(lac)), 1)

if __name__ == "__main__":
    unittest.main()


class TestFecharAtualizaPainel(unittest.TestCase):
    def _estado(self):
        return {"prazos_destaque": [{"rotulo": "P", "data": "2026-09-30", "status": "critical"}],
                "pendencias": [], "linha_do_tempo": [{"data": "2026-01-01", "titulo": "M"}]}

    def test_fechar_aplica_proposta_e_anota_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "estado.json", self._estado())
            novo = self._estado(); novo["prazos_destaque"][0]["data"] = "2026-10-15"
            escreve(raiz, "dados/estado_proposta.json", {"estado": novo, "mudancas": [
                {"secao": "prazos_destaque", "tipo": "alterado",
                 "descricao": "Prazo P prorrogado para 15/10", "fonte": "u"}]})
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertTrue(r["ok"])
            self.assertTrue(r["painel"]["aplicado"])
            self.assertEqual(le(raiz, "estado.json")["prazos_destaque"][0]["data"], "2026-10-15")
            self.assertEqual(le(raiz, "dados/analise_status.json")["painel_atualizado"],
                             ["Prazo P prorrogado para 15/10"])

    def test_analise_invalida_nao_aplica_proposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz, md=False)
            escreve(raiz, "estado.json", self._estado())
            escreve(raiz, "dados/estado_proposta.json", {"estado": {}, "mudancas": []})
            fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertEqual(le(raiz, "estado.json"), self._estado())

    def test_proposta_invalida_nao_derruba_fechamento(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "estado.json", self._estado())
            escreve(raiz, "dados/estado_proposta.json", "{quebrado")
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
            self.assertTrue(r["ok"])
            self.assertFalse(r["painel"]["aplicado"])
            self.assertIn("a", le(raiz, "dados/analisados.json")["chaves"])
            self.assertNotIn("painel_atualizado", le(raiz, "dados/analise_status.json"))


def resumo_valido(**extra):
    r = {"data": "2026-09-30", "turno": "noturna", "manchete": "M",
         "em_30_segundos": ["um", "dois", "tres"],
         "noticias": [{"chave": None, "tema": "pessoas", "titulo": "T",
                       "url": "https://x", "linha": "L", "origem": "busca"}],
         "lidas": 5}
    r.update(extra)
    return r


class TestNoticiasSemVeredito(unittest.TestCase):
    def _prepara(self, raiz):
        prepara(raiz)
        hist = le(raiz, "dados/historico.json")
        hist["n1"] = {"primeira_vez": "2026-09-30", "tipo": "noticia", "titulo": "n1"}
        hist["n2"] = {"primeira_vez": "2026-09-30", "tipo": "noticia", "titulo": "n2"}
        hist["n3"] = {"primeira_vez": "2026-09-30", "tipo": "noticia", "titulo": "n3"}
        escreve(raiz, "dados/historico.json", hist)

    def test_noticia_sem_veredito_vira_ruido(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._prepara(raiz)
            escreve(raiz, "dados/triagem_pendente.json", [
                {"chave": "n1", "veredito": "relevante", "motivo": "entrou no resumo"},
                {"chave": "a", "veredito": "ruido", "motivo": "x"}])
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a", "b", "n1", "n2"])
            self.assertTrue(r["ok"])
            self.assertEqual(r["noticias_ruido"], 1)
            t = le(raiz, "dados/triagem.json")
            self.assertEqual(t["n1"]["veredito"], "relevante")
            self.assertEqual(t["n2"], {"veredito": "ruido", "em": "2026-09-30-noturna",
                                       "motivo": "não selecionada para o resumo"})
            # publicacao oficial sem veredito continua sem (exige leitura)
            self.assertNotIn("b", t)
            # noticia fora da lacuna nao e' tocada
            self.assertNotIn("n3", t)

    def test_tipo_vindo_da_lacuna_tambem_conta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a", "c"], noticias=["c"])
            self.assertEqual(r["noticias_ruido"], 1)
            self.assertEqual(sorted(le(raiz, "dados/triagem.json")), ["c"])

    def test_cli_passa_noticias_da_lacuna(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            lac = raiz / "lacuna.json"
            lac.write_text(json.dumps({"itens": [{"chave": "a"},
                                                 {"chave": "b", "tipo": "noticia"}]}), "utf-8")
            with patch.object(fa, "RAIZ", raiz), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(fa.main(["2026-09-30", "noturna", str(lac)]), 0)
            self.assertEqual(le(raiz, "dados/triagem.json")["b"]["veredito"], "ruido")

    def test_analise_recusada_nao_fecha_noticia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._prepara(raiz)
            (raiz / "analises/2026-09-30-noturna.md").unlink()
            fa.fechar(raiz, "2026-09-30", "noturna", ["n1"])
            self.assertFalse((raiz / "dados/triagem.json").exists())


class TestValidaResumo(unittest.TestCase):
    def test_resumo_valido(self):
        self.assertEqual(fa.valida_resumo(resumo_valido(), "2026-09-30", "noturna"), [])

    def test_sem_data_turno_nao_confere(self):
        self.assertEqual(fa.valida_resumo(resumo_valido(data="x", turno="y")), [])

    def test_erros(self):
        casos = [
            ("nao e' objeto", []),
            ("data", resumo_valido(data="2026-09-29")),
            ("turno", resumo_valido(turno="matinal")),
            ("manchete", resumo_valido(manchete=" ")),
            ("em_30_segundos", resumo_valido(em_30_segundos="texto")),
            ("em_30_segundos", resumo_valido(em_30_segundos=[])),
            ("em_30_segundos", resumo_valido(em_30_segundos=["ok", 3])),
            ("noticias precisa", resumo_valido(noticias={})),
            ("noticias[0] nao", resumo_valido(noticias=["x"])),
            ("tema", resumo_valido(noticias=[dict(resumo_valido()["noticias"][0], tema="esporte")])),
            ("url", resumo_valido(noticias=[dict(resumo_valido()["noticias"][0], url="")])),
            ("linha", resumo_valido(noticias=[{"tema": "reforma", "titulo": "t", "url": "u"}])),
            ("origem", resumo_valido(noticias=[dict(resumo_valido()["noticias"][0], origem="twitter")])),
            ("lidas", resumo_valido(lidas="5")),
        ]
        for esperado, resumo in casos:
            with self.subTest(esperado):
                erros = fa.valida_resumo(resumo, "2026-09-30", "noturna")
                self.assertTrue(any(esperado in e for e in erros), erros)

    def test_noticias_vazia_e_valida(self):
        self.assertEqual(fa.valida_resumo(resumo_valido(noticias=[])), [])


class TestFecharComResumo(unittest.TestCase):
    def _fecha(self, raiz):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            r = fa.fechar(raiz, "2026-09-30", "noturna", ["a"])
        return r, err.getvalue()

    def test_resumo_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "analises/resumos/2026-09-30-noturna.json", resumo_valido())
            r, err = self._fecha(raiz)
            self.assertTrue(r["ok"])
            self.assertEqual(r["resumo"], "ok")
            self.assertNotIn("resumo", err)

    def test_resumo_invalido_avisa_e_nao_derruba(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "analises/resumos/2026-09-30-noturna.json", resumo_valido(turno="matinal"))
            r, err = self._fecha(raiz)
            self.assertTrue(r["ok"])
            self.assertEqual(r["resumo"], "invalido")
            self.assertIn("turno", err)
            self.assertIn("a", le(raiz, "dados/analisados.json")["chaves"])
            # o arquivo fica: o painel e' que pula o resumo invalido
            self.assertTrue((raiz / "analises/resumos/2026-09-30-noturna.json").exists())

    def test_resumo_quebrado_avisa(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            escreve(raiz, "analises/resumos/2026-09-30-noturna.json", "{quebrado")
            r, err = self._fecha(raiz)
            self.assertTrue(r["ok"])
            self.assertEqual(r["resumo"], "invalido")
            self.assertIn("ilegivel", err)

    def test_resumo_ausente_avisa(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            prepara(raiz)
            r, err = self._fecha(raiz)
            self.assertTrue(r["ok"])
            self.assertEqual(r["resumo"], "ausente")
            self.assertIn("ausente", err)
