import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import atualizar_estado as ae


def estado_base():
    return {
        "_leia_me": "camada curada",
        "atualizado_em": "2026-08-17",
        "prazos_destaque": [
            {"rotulo": "Prazo A", "data": "2026-10-03", "status": "critical", "nota": "n"}],
        "pendencias": [
            {"item": "Pendencia A", "situacao": "s", "prazo": None, "status": "serious"}],
        "linha_do_tempo": [
            {"data": "2026-01-01", "titulo": "Marco A", "detalhe": "d"}],
    }


def escreve(raiz, rel, conteudo):
    p = raiz / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False), "utf-8")


def le(raiz, rel):
    return json.loads((raiz / rel).read_text("utf-8"))


def proposta(estado, mudancas):
    return {"estado": estado, "mudancas": mudancas}


MUD = [{"secao": "prazos_destaque", "tipo": "alterado",
        "descricao": "Prazo A adiado", "fonte": "https://x"}]


class TestValida(unittest.TestCase):
    def test_estado_valido_passa(self):
        self.assertEqual(ae.valida(proposta(estado_base(), MUD), estado_base()), [])

    def test_data_invalida(self):
        e = estado_base(); e["prazos_destaque"][0]["data"] = "03/10/2026"
        self.assertTrue(ae.valida(proposta(e, MUD), estado_base()))

    def test_status_fora_da_lista(self):
        e = estado_base(); e["pendencias"][0]["status"] = "urgente"
        self.assertTrue(ae.valida(proposta(e, MUD), estado_base()))

    def test_campo_obrigatorio_faltando(self):
        e = estado_base(); del e["linha_do_tempo"][0]["titulo"]
        self.assertTrue(ae.valida(proposta(e, MUD), estado_base()))

    def test_sem_mudancas_declaradas_rejeita(self):
        self.assertTrue(ae.valida(proposta(estado_base(), []), estado_base()))

    def test_mudanca_com_tipo_invalido_rejeita(self):
        m = [dict(MUD[0], tipo="mexido")]
        self.assertTrue(ae.valida(proposta(estado_base(), m), estado_base()))

    def test_remocao_sem_mudanca_de_remocao_rejeita(self):
        # sumir com prazo/pendencia/marco sem declarar e' o erro mais caro:
        # o leitor perde a informacao sem saber
        e = estado_base(); e["pendencias"] = []
        self.assertTrue(ae.valida(proposta(e, MUD), estado_base()))

    def test_remocao_declarada_passa(self):
        e = estado_base(); e["pendencias"] = []
        m = [{"secao": "pendencias", "tipo": "removido",
              "descricao": "Pendencia A resolvida", "fonte": "https://y"}]
        self.assertEqual(ae.valida(proposta(e, m), estado_base()), [])

    def test_secao_faltando_rejeita(self):
        e = estado_base(); del e["linha_do_tempo"]
        self.assertTrue(ae.valida(proposta(e, MUD), estado_base()))

    def test_nao_e_dict_rejeita(self):
        self.assertTrue(ae.valida([], estado_base()))


class TestAplica(unittest.TestCase):
    def test_sem_proposta_nao_faz_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp); escreve(raiz, "estado.json", estado_base())
            r = ae.aplica(raiz, "2026-09-30", "matinal")
            self.assertEqual(r, {"aplicado": False, "motivo": "sem proposta", "mudancas": []})
            self.assertEqual(le(raiz, "estado.json"), estado_base())

    def test_proposta_valida_aplica_e_registra(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp); escreve(raiz, "estado.json", estado_base())
            e = estado_base(); e["prazos_destaque"][0]["data"] = "2026-10-15"
            e["_leia_me"] = "o claude mexeu aqui"
            escreve(raiz, "dados/estado_proposta.json", proposta(e, MUD))
            r = ae.aplica(raiz, "2026-09-30", "matinal")
            self.assertTrue(r["aplicado"])
            novo = le(raiz, "estado.json")
            self.assertEqual(novo["prazos_destaque"][0]["data"], "2026-10-15")
            self.assertEqual(novo["atualizado_em"], "2026-09-30")
            self.assertEqual(novo["_leia_me"], "camada curada")  # preservado
            hist = le(raiz, "dados/estado_mudancas.json")
            self.assertEqual(hist[0]["descricao"], "Prazo A adiado")
            self.assertEqual(hist[0]["em"], "2026-09-30-matinal")
            self.assertFalse((raiz / "dados/estado_proposta.json").exists())

    def test_historico_acumula_mais_recente_primeiro(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp); escreve(raiz, "estado.json", estado_base())
            escreve(raiz, "dados/estado_mudancas.json",
                    [{"descricao": "antiga", "em": "2026-09-29-noturna"}])
            escreve(raiz, "dados/estado_proposta.json", proposta(estado_base(), MUD))
            ae.aplica(raiz, "2026-09-30", "matinal")
            hist = le(raiz, "dados/estado_mudancas.json")
            descs = [h["descricao"] for h in hist]
            self.assertEqual(descs[0], "Prazo A adiado")
            self.assertEqual(descs[-1], "antiga")

    def test_proposta_invalida_preserva_estado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp); escreve(raiz, "estado.json", estado_base())
            e = estado_base(); e["pendencias"][0]["status"] = "urgente"
            escreve(raiz, "dados/estado_proposta.json", proposta(e, MUD))
            r = ae.aplica(raiz, "2026-09-30", "matinal")
            self.assertFalse(r["aplicado"])
            self.assertIn("status", r["motivo"])
            self.assertEqual(le(raiz, "estado.json"), estado_base())
            self.assertFalse((raiz / "dados/estado_proposta.json").exists())

    def test_proposta_json_quebrado(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp); escreve(raiz, "estado.json", estado_base())
            escreve(raiz, "dados/estado_proposta.json", "{nao e json")
            r = ae.aplica(raiz, "2026-09-30", "matinal")
            self.assertFalse(r["aplicado"])
            self.assertEqual(le(raiz, "estado.json"), estado_base())


if __name__ == "__main__":
    unittest.main()


class TestPrazoNaLinhaDoTempo(unittest.TestCase):
    def test_prazo_sem_marco_ganha_marco(self):
        e = estado_base()
        e["prazos_destaque"].append({"rotulo": "Opcao pelo Simples", "data": "2026-10-15",
                                     "status": "critical", "nota": "Res. CGSN 194"})
        novo, extras = ae.completa_linha_do_tempo(e)
        datas = [m["data"] for m in novo["linha_do_tempo"]]
        self.assertIn("2026-10-15", datas)
        self.assertIn("2026-10-03", datas)  # o Prazo A da base tambem nao tinha marco
        self.assertEqual(datas, sorted(datas))
        marco = [m for m in novo["linha_do_tempo"] if m["data"] == "2026-10-15"][0]
        self.assertEqual(marco["titulo"], "Opcao pelo Simples")
        self.assertEqual(marco["detalhe"], "Res. CGSN 194")
        self.assertEqual(len(extras), 2)
        self.assertEqual(extras[0]["secao"], "linha_do_tempo")

    def test_prazo_com_marco_na_mesma_data_nao_duplica(self):
        e = estado_base()
        e["linha_do_tempo"].append({"data": "2026-10-03", "titulo": "Outro nome", "detalhe": ""})
        novo, extras = ae.completa_linha_do_tempo(e)
        self.assertEqual(sum(1 for m in novo["linha_do_tempo"] if m["data"] == "2026-10-03"), 1)
        self.assertEqual(extras, [])

    def test_aplica_completa_e_registra(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp); escreve(raiz, "estado.json", estado_base())
            escreve(raiz, "dados/estado_proposta.json", proposta(estado_base(), MUD))
            r = ae.aplica(raiz, "2026-09-30", "matinal")
            self.assertTrue(r["aplicado"])
            self.assertIn("2026-10-03", [m["data"] for m in le(raiz, "estado.json")["linha_do_tempo"]])
            self.assertEqual(len(r["mudancas"]), 2)
