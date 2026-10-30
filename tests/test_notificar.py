import json
import sys
import tempfile
import unittest
from email import message_from_string
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import notificar as nt

PAINEL = "https://exemplo.github.io/painel/"

MD = """**16 itens novos; dois exigem acao — prazo do Simples prorrogado.**

### Ação requerida

**Prazo de opção pelo Simples prorrogado** — CGSN, Resolução nº 194/2026. `[VERIFICADO LITERAL]`

- **Fonte:** [Resolução](http://exemplo/res)

### No radar

- **2 dias** — 01/10: 2ª onda de DF-e
"""

STATUS_ACAO = {"data": "2026-09-30", "turno": "matinal", "situacao": "publicada",
               "resumo_curto": "16 novidades, 2 exigem ação", "acoes": 2}

ENV_NTFY = {"NTFY_TOPICO": "topico-secreto"}
ENV_SMTP = {"SMTP_HOST": "smtp.exemplo", "SMTP_PORTA": "587",
            "SMTP_USUARIO": "eu@exemplo", "SMTP_SENHA": "s3nha",
            "EMAIL_PARA": "a@exemplo, b@exemplo"}


def escreve(raiz, rel, conteudo):
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        conteudo = json.dumps(conteudo, ensure_ascii=False)
    caminho.write_text(conteudo, "utf-8")


class TestMontaMensagem(unittest.TestCase):
    def test_monta_mensagem_com_acao_prioridade_alta(self):
        msg = nt.monta_mensagem(STATUS_ACAO, MD, PAINEL)
        self.assertEqual(msg["prioridade"], "high")
        self.assertEqual(msg["click"], PAINEL + "#analise=2026-09-30-matinal")
        self.assertIn("30/09 matinal", msg["titulo"])
        self.assertIn("2 exigem ação", msg["titulo"])
        self.assertTrue(msg["assunto"].startswith("⚠ [Reforma Tributária] 30/09 matinal"))
        self.assertIn("16 novidades, 2 exigem ação", msg["corpo"])
        # trecho da secao "Acao requerida", sem markdown
        self.assertIn("Prazo de opção pelo Simples prorrogado", msg["corpo"])
        self.assertNotIn("**", msg["corpo"])
        self.assertNotIn("No radar", msg["corpo"])
        self.assertTrue(msg["corpo"].rstrip().endswith(msg["click"]))
        self.assertEqual(msg["md"], MD)

    def test_sem_novidade_prioridade_baixa(self):
        status = {"data": "2026-09-30", "turno": "noturna", "situacao": "sem_novidade",
                  "acoes": 0}
        msg = nt.monta_mensagem(status, "Sem publicações novas desde a última análise.", PAINEL)
        self.assertEqual(msg["prioridade"], "low")
        self.assertFalse(msg["assunto"].startswith("⚠"))

    def test_publicada_sem_acao_prioridade_default(self):
        status = dict(STATUS_ACAO, acoes=0)
        self.assertEqual(nt.monta_mensagem(status, MD, PAINEL)["prioridade"], "default")

    def test_status_legado_sem_acoes_nem_turno(self):
        status = {"data": "2026-09-29", "situacao": "publicada", "resumo_curto": "x"}
        msg = nt.monta_mensagem(status, None, PAINEL)
        self.assertEqual(msg["prioridade"], "default")
        self.assertEqual(msg["click"], PAINEL + "#analise=2026-09-29")
        self.assertIn("29/09", msg["titulo"])
        self.assertIn("x", msg["corpo"])

    def test_acoes_invalido_vira_zero(self):
        status = dict(STATUS_ACAO, acoes="duas")
        self.assertEqual(nt.monta_mensagem(status, MD, PAINEL)["prioridade"], "default")

    def test_corpo_limitado(self):
        md = "### Ação requerida\n\n" + ("palavra " * 2000)
        status = dict(STATUS_ACAO, resumo_curto="r" * 5000)
        msg = nt.monta_mensagem(status, md, PAINEL)
        self.assertLess(len(msg["corpo"]), 4000)
        self.assertTrue(msg["corpo"].rstrip().endswith(msg["click"]))

    def test_falha_monta_prioridade_urgente(self):
        msg = nt.monta_falha("dou falhou", PAINEL)
        self.assertEqual(msg["prioridade"], "urgent")
        self.assertEqual(msg["titulo"], "Monitor da Reforma: falha no ciclo")
        self.assertEqual(msg["tags"], ["warning"])
        self.assertIn("dou falhou", msg["corpo"])


class TestEnviaNtfy(unittest.TestCase):
    def test_envia_json(self):
        msg = nt.monta_mensagem(STATUS_ACAO, MD, PAINEL)
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            self.assertTrue(nt.envia_ntfy(msg, "topico-secreto"))
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://ntfy.sh")
        self.assertEqual(req.get_method(), "POST")
        corpo = json.loads(req.data.decode("utf-8"))
        self.assertEqual(corpo["topic"], "topico-secreto")
        self.assertEqual(corpo["priority"], 4)
        self.assertEqual(corpo["title"], msg["titulo"])
        self.assertEqual(corpo["click"], msg["click"])
        self.assertEqual(corpo["message"], msg["corpo"])

    def test_erro_de_rede_nao_levanta(self):
        msg = nt.monta_falha("x", PAINEL)
        with mock.patch("urllib.request.urlopen", side_effect=OSError("sem rede")):
            self.assertFalse(nt.envia_ntfy(msg, "t", "https://ntfy.exemplo/"))


class TestEnviaEmail(unittest.TestCase):
    def test_email_monta_html(self):
        msg = nt.monta_mensagem(STATUS_ACAO, MD, PAINEL)
        cfg = nt.config_email(ENV_SMTP)
        with mock.patch("smtplib.SMTP") as SMTP:
            self.assertTrue(nt.envia_email(msg, cfg))
        SMTP.assert_called_once_with("smtp.exemplo", 587, timeout=mock.ANY)
        smtp = SMTP.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("eu@exemplo", "s3nha")
        args, kwargs = smtp.sendmail.call_args
        self.assertEqual(args[0], "eu@exemplo")
        self.assertEqual(args[1], ["a@exemplo", "b@exemplo"])
        email = message_from_string(args[2])
        self.assertEqual(email.get_content_type(), "multipart/alternative")
        tipos = {p.get_content_type(): p for p in email.get_payload()}
        self.assertIn("text/plain", tipos)
        self.assertIn("text/html", tipos)
        html = tipos["text/html"].get_payload(decode=True).decode("utf-8")
        self.assertIn("<strong>", html)
        self.assertIn(msg["click"], html)

    def test_email_erro_nao_levanta(self):
        msg = nt.monta_falha("x", PAINEL)
        with mock.patch("smtplib.SMTP", side_effect=OSError("recusado")):
            self.assertFalse(nt.envia_email(msg, nt.config_email(ENV_SMTP)))

    def test_config_incompleta_e_none(self):
        self.assertIsNone(nt.config_email({"SMTP_HOST": "h"}))
        self.assertIsNone(nt.config_email({}))

    def test_porta_invalida_usa_587(self):
        self.assertEqual(nt.config_email(dict(ENV_SMTP, SMTP_PORTA="x"))["porta"], 587)
        self.assertEqual(nt.config_email(dict(ENV_SMTP, SMTP_PORTA=""))["porta"], 587)


class TestMain(unittest.TestCase):
    def test_sem_config_nao_envia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/analise_status.json", STATUS_ACAO)
            with mock.patch("urllib.request.urlopen") as urlopen, \
                    mock.patch("smtplib.SMTP") as SMTP:
                self.assertEqual(nt.main([], raiz=raiz, env={}), 0)
            urlopen.assert_not_called()
            SMTP.assert_not_called()

    def test_ciclo_envia_nos_dois_canais(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/analise_status.json", STATUS_ACAO)
            escreve(raiz, "analises/2026-09-30-matinal.md", MD)
            with mock.patch("urllib.request.urlopen") as urlopen, \
                    mock.patch("smtplib.SMTP") as SMTP:
                urlopen.return_value.__enter__.return_value.status = 200
                rc = nt.main([], raiz=raiz, env=dict(ENV_NTFY, **ENV_SMTP))
            self.assertEqual(rc, 0)
            corpo = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
            self.assertIn("Prazo de opção", corpo["message"])
            SMTP.return_value.__enter__.return_value.sendmail.assert_called_once()

    def test_sem_status_nao_levanta(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("urllib.request.urlopen") as urlopen:
                self.assertEqual(nt.main([], raiz=Path(tmp), env=ENV_NTFY), 0)
            urlopen.assert_not_called()

    def test_status_malformado_nao_levanta(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/analise_status.json", "{nao e json")
            with mock.patch("urllib.request.urlopen") as urlopen:
                self.assertEqual(nt.main([], raiz=raiz, env=ENV_NTFY), 0)
            urlopen.assert_not_called()

    def test_md_legado_sem_turno(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/analise_status.json",
                    {"data": "2026-09-29", "situacao": "publicada", "resumo_curto": "r"})
            escreve(raiz, "analises/2026-09-29.md", MD)
            with mock.patch("urllib.request.urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.status = 200
                nt.main([], raiz=raiz, env=ENV_NTFY)
            corpo = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
            self.assertIn("Prazo de opção", corpo["message"])

    def test_falha_cli_urgente_e_servidor_customizado(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(ENV_NTFY, NTFY_SERVIDOR="https://ntfy.exemplo")
            with mock.patch("urllib.request.urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.status = 200
                rc = nt.main(["--falha", "unidade x falhou"], raiz=Path(tmp), env=env)
            self.assertEqual(rc, 0)
            req = urlopen.call_args[0][0]
            self.assertEqual(req.full_url, "https://ntfy.exemplo")
            corpo = json.loads(req.data.decode("utf-8"))
            self.assertEqual(corpo["priority"], 5)
            self.assertEqual(corpo["tags"], ["warning"])
            self.assertIn("unidade x falhou", corpo["message"])


if __name__ == "__main__":
    unittest.main()


class TestPainelAtualizadoNoAlerta(unittest.TestCase):
    def test_mudancas_do_painel_entram_no_corpo(self):
        st = {"data": "2026-09-30", "turno": "matinal", "situacao": "sem_novidade", "acoes": 0,
              "resumo_curto": "x", "painel_atualizado": ["Opção pelo Simples prorrogada para 15/10"]}
        msg = nt.monta_mensagem(st, "**x**", "https://p/")
        self.assertIn("Painel atualizado", msg["corpo"])
        self.assertIn("15/10", msg["corpo"])
        # sem novidade mas com painel mudado nao e' mais prioridade baixa
        self.assertEqual(msg["prioridade"], "default")
        self.assertIn("15/10", msg["md"])

    def test_sem_mudanca_nada_muda(self):
        st = {"data": "2026-09-30", "turno": "matinal", "situacao": "sem_novidade", "acoes": 0}
        msg = nt.monta_mensagem(st, "**x**", "https://p/")
        self.assertNotIn("Painel atualizado", msg["corpo"])
        self.assertEqual(msg["prioridade"], "low")



DOU_FALHOU = {"data": "2026-09-30", "fontes": [{
    "fonte": "DOU (INLABS)", "metodo": None, "total": 0,
    "erro": "RuntimeError: login do INLABS falhou apos 30 tentativas: HTTP 404 vindo do "
            "proprio INLABS — nao e credencial, o servidor caiu antes de olhar o que foi enviado"}]}
DOU_OK = {"data": "2026-09-30", "fontes": [{"fonte": "DOU (INLABS)", "metodo": "inlabs",
                                            "erro": None, "total": 3}]}
WEB_OK = {"data": "2026-09-30", "fontes": [{"fonte": "Receita", "metodo": "browser",
                                            "erro": None, "total": 5}]}


def raiz_com(tmp, web=WEB_OK, dou=DOU_OK):
    raiz = Path(tmp)
    if web is not None:
        escreve(raiz, "dados/2026-09-30.json", web)
    if dou is not None:
        escreve(raiz, "dados/2026-09-30-dou.json", dou)
    return raiz


class TestFalhasDoCiclo(unittest.TestCase):
    def test_sem_falhas_lista_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(nt.falhas_do_ciclo(raiz_com(tmp), "2026-09-30"), [])

    def test_dou_sem_metodo_resume_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            falhas = nt.falhas_do_ciclo(raiz_com(tmp, dou=DOU_FALHOU), "2026-09-30")
        self.assertEqual(len(falhas), 1)
        self.assertTrue(falhas[0].startswith("DOU (INLABS): "))
        self.assertIn("HTTP 404", falhas[0])
        self.assertLessEqual(len(falhas[0]) - len("DOU (INLABS): "), 120)

    def test_aviso_do_plano_b(self):
        dou = {"data": "2026-09-30", "fontes": [{
            "fonte": "DOU (INLABS)", "metodo": "leiturajornal", "erro": None,
            "aviso": "INLABS fora; usado Leitura do Jornal — 2 consulta(s) falharam: x, y"}]}
        with tempfile.TemporaryDirectory() as tmp:
            falhas = nt.falhas_do_ciclo(raiz_com(tmp, dou=dou), "2026-09-30")
        self.assertEqual(falhas, ["DOU (INLABS): INLABS fora; usado Leitura do Jornal — "
                                  "2 consulta(s) falharam: x, y"])

    def test_plano_b_completo_nao_entra_no_push(self):
        dou = {"data": "2026-09-30", "fontes": [{
            "fonte": "DOU (INLABS)", "metodo": "leiturajornal", "erro": None,
            "aviso": "INLABS indisponivel (INLABS em manutencao programada); "
                     "coletado pela Leitura do Jornal (in.gov.br)"}]}
        with tempfile.TemporaryDirectory() as tmp:
            falhas = nt.falhas_do_ciclo(raiz_com(tmp, dou=dou), "2026-09-30")
        self.assertEqual(falhas, [])

    def test_portal_nao_tentada(self):
        web = {"data": "2026-09-30", "fontes": [{
            "fonte": "CGIBS", "metodo": None,
            "erro": "nao tentada: orcamento de tempo esgotado"}]}
        with tempfile.TemporaryDirectory() as tmp:
            falhas = nt.falhas_do_ciclo(raiz_com(tmp, web=web), "2026-09-30")
        self.assertEqual(falhas, ["CGIBS: nao consultada (tempo esgotado)"])

    def test_arquivo_ausente(self):
        with tempfile.TemporaryDirectory() as tmp:
            falhas = nt.falhas_do_ciclo(raiz_com(tmp, dou=None), "2026-09-30")
            self.assertEqual(falhas, ["DOU: sem registro da coleta de 2026-09-30"])
        with tempfile.TemporaryDirectory() as tmp:
            falhas = nt.falhas_do_ciclo(raiz_com(tmp, web=None, dou=None), "2026-09-30")
            self.assertEqual(len(falhas), 2)
            self.assertIn("Portais web: sem registro da coleta de 2026-09-30", falhas)

    def test_arquivo_ilegivel_conta_como_sem_registro(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = raiz_com(tmp)
            escreve(raiz, "dados/2026-09-30-dou.json", "{torto")
            self.assertEqual(nt.falhas_do_ciclo(raiz, "2026-09-30"),
                             ["DOU: sem registro da coleta de 2026-09-30"])


class TestGravidadeFalhas(unittest.TestCase):
    def grav(self, web=WEB_OK, dou=DOU_OK):
        with tempfile.TemporaryDirectory() as tmp:
            return nt.gravidade_falhas(raiz_com(tmp, web=web, dou=dou), "2026-09-30")

    def test_sem_falhas(self):
        self.assertIsNone(self.grav())

    def test_erro_e_alta(self):
        self.assertEqual(self.grav(dou=DOU_FALHOU), "alta")

    def test_sem_registro_e_alta(self):
        self.assertEqual(self.grav(dou=None), "alta")

    def test_plano_b_completo_nao_e_falha(self):
        # Rodou no plano B e coletou tudo: para o Rodrigo, esta' ok.
        dou = {"fontes": [{"fonte": "DOU (INLABS)", "metodo": "leiturajornal",
                           "erro": None, "aviso": "INLABS fora"}]}
        self.assertIsNone(self.grav(dou=dou))

    def test_plano_b_parcial_e_aviso(self):
        dou = {"fontes": [{"fonte": "DOU (INLABS)", "metodo": "leiturajornal", "erro": None,
                           "aviso": "INLABS fora — 1 consulta(s) da Leitura do Jornal "
                                    "falharam: 2026-10-22 DO3E: timeout"}]}
        self.assertEqual(self.grav(dou=dou), "aviso")

    def test_nao_consultada_e_aviso(self):
        web = {"fontes": [{"fonte": "CGIBS", "metodo": None,
                           "erro": "nao tentada: orcamento"}]}
        self.assertEqual(self.grav(web=web), "aviso")

    def test_erro_e_aviso_juntos_e_alta(self):
        web = {"fontes": [{"fonte": "CGIBS", "metodo": None, "erro": "nao tentada: x"}]}
        self.assertEqual(self.grav(web=web, dou=DOU_FALHOU), "alta")


class TestAlertaComFalhas(unittest.TestCase):
    FALHAS = ["DOU (INLABS): login falhou", "CGIBS: nao consultada (tempo esgotado)"]

    def test_sem_falhas_mensagem_identica(self):
        base = nt.monta_mensagem(STATUS_ACAO, MD, PAINEL)
        self.assertEqual(nt.monta_mensagem(STATUS_ACAO, MD, PAINEL, falhas=[]), base)
        self.assertEqual(nt.monta_mensagem(STATUS_ACAO, MD, PAINEL, falhas=None), base)

    def test_falhas_sobem_prioridade_e_entram_no_corpo(self):
        st = dict(STATUS_ACAO, acoes=0, situacao="sem_novidade")
        msg = nt.monta_mensagem(st, MD, PAINEL, falhas=self.FALHAS, gravidade="alta")
        self.assertEqual(msg["prioridade"], "high")
        self.assertIn("warning", msg["tags"])
        self.assertIn("⚠ Consultas com falha:", msg["corpo"])
        self.assertIn("- DOU (INLABS): login falhou", msg["corpo"])
        self.assertTrue(msg["corpo"].rstrip().endswith(msg["click"]))

    def test_so_aviso_nao_sobe_prioridade_mas_marca(self):
        st = dict(STATUS_ACAO, acoes=0, situacao="sem_novidade")
        msg = nt.monta_mensagem(st, MD, PAINEL, falhas=self.FALHAS, gravidade="aviso")
        self.assertEqual(msg["prioridade"], "low")
        self.assertIn("warning", msg["tags"])
        self.assertIn("Consultas com falha", msg["corpo"])

    def test_aviso_nao_rebaixa_analise_urgente(self):
        msg = nt.monta_mensagem(STATUS_ACAO, MD, PAINEL, falhas=self.FALHAS, gravidade="aviso")
        self.assertEqual(msg["prioridade"], nt.monta_mensagem(STATUS_ACAO, MD, PAINEL)["prioridade"])

    def test_email_recebe_a_mesma_secao(self):
        msg = nt.monta_mensagem(STATUS_ACAO, MD, PAINEL, falhas=self.FALHAS, gravidade="alta")
        self.assertIn("Consultas com falha", msg["md"])
        self.assertIn("CGIBS", msg["md"])
        # sem .md da analise, o e-mail usa o corpo, que ja tem a secao
        sem_md = nt.monta_mensagem(STATUS_ACAO, None, PAINEL, falhas=self.FALHAS, gravidade="alta")
        self.assertIn("Consultas com falha", sem_md["md"] or sem_md["corpo"])

    def test_corpo_longo_continua_no_limite(self):
        md = "### Ação requerida\n\n" + ("palavra " * 2000)
        st = dict(STATUS_ACAO, resumo_curto="r" * 5000)
        falhas = ["F%d: %s" % (i, "e" * 150) for i in range(30)]
        msg = nt.monta_mensagem(st, md, PAINEL, falhas=falhas)
        self.assertLessEqual(len(msg["corpo"]), nt.LIMITE_CORPO)
        self.assertIn("Consultas com falha", msg["corpo"])
        self.assertTrue(msg["corpo"].rstrip().endswith(msg["click"]))

    def test_main_ciclo_inclui_falha_do_dou(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = raiz_com(tmp, dou=DOU_FALHOU)
            escreve(raiz, "dados/analise_status.json", dict(STATUS_ACAO, acoes=0))
            with mock.patch("urllib.request.urlopen") as urlopen:
                urlopen.return_value.__enter__.return_value.status = 200
                nt.main([], raiz=raiz, env=ENV_NTFY)
            corpo = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
            self.assertEqual(corpo["priority"], 4)
            self.assertIn("warning", corpo["tags"])
            self.assertIn("DOU (INLABS)", corpo["message"])
