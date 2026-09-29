# Evolução do painel — histórico, triagem, 2 ciclos/dia e alertas

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guardar e navegar todas as análises (por dia e turno), consultar/filtrar o histórico de publicações, substituir o "revisar" do DOU por uma triagem feita pela IA, rodar o ciclo completo às 05h e às 17h, e mandar alerta por push (ntfy) e e-mail.

**Architecture:** Mantém as duas camadas (fatos sem IA / análise com IA). O que muda: (1) a "lacuna" da análise passa a ser por *chave de item* (`dados/analisados.json`), não por data — necessário com dois ciclos no mesmo dia; (2) cada execução da análise grava um arquivo `analises/AAAA-MM-DD-<turno>.md` (sempre, mesmo sem novidade) e um veredito por item em `dados/triagem_pendente.json`, que um script determinístico (`fechar_analise.py`) incorpora em `dados/triagem.json`; (3) um único timer systemd (05:00 e 17:00) roda `rodar_ciclo.sh` = DOU → portais → análise → painel → alerta; (4) o painel embute só os últimos 3 dias e lê o histórico completo de `docs/historico.json` sob demanda.

**Tech Stack:** Python 3 stdlib (+ `markdown`, já em requirements), unittest, HTML/JS puro no template, systemd, GitHub Actions, ntfy.sh (push), SMTP (Gmail com senha de app).

**Spec:** pedido do usuário de 29/09/2026 (resumido na seção "Decisões" abaixo).

## Decisões (tomadas por mim, revisáveis — ver `docs/revisao-pendente.md`)

- **Turnos com nome:** `matinal` (ciclo das 05h) e `noturna` (ciclo das 17h). Um arquivo por execução — não junto os dois textos, porque o de 17h só fala do que apareceu depois das 05h; juntar duplicaria ou exigiria reescrita. No painel, o seletor mostra "30/09 · matinal".
- **Turno = hora local da execução:** `< 12h` → matinal, senão noturna (catch-up do `Persistent=true` cai no turno certo). Variável `TURNO` sobrescreve.
- **Análises antigas** (`analises/AAAA-MM-DD.md`) continuam válidas e aparecem no seletor como turno "única".
- **"revisar":** o acesso ao DOU é completo (XML integral do INLABS). 219 de 234 itens "revisar" vêm da regra 5 do classificador (órgão do Ministério da Fazenda + tipo normativo, **zero** menção a IBS/CBS/LC 214 no texto) — é filtro largo de propósito (recall). O filtro não muda; quem decide é a IA, que passa a gravar um veredito por item (`relevante` / `contexto` / `ruido` + motivo). O painel mostra o veredito no lugar de "revisar" e permite ocultar ruído.
- **Correção pequena no classificador:** classificar pelo texto integral; hoje `_texto` é cortado em 20.000 caracteres *antes* de classificar (11 itens atingiram o teto), então menção depois do corte se perde. Guarda-se truncado, classifica-se inteiro.
- **Alertas:** ntfy.sh (push no celular, sem conta, tópico aleatório secreto no `.env`) ativo já; e-mail via SMTP pronto no código, liga quando o `.env` tiver `SMTP_*`. Falha do ciclo também alerta.
- **Claude não faz git.** Hoje o `claude -p` commita e empurra sozinho; passa a só escrever arquivos, e o wrapper valida, fecha e commita. Menos coisa não determinística.

## Global Constraints

- Somente stdlib Python + `markdown` (já em `requirements.txt`). Nada de pip novo.
- Testes: `python3 -m unittest discover -s tests -v` (stdlib unittest, fixtures em `tempfile`), rodando com `.venv/bin/python3`.
- Horários em BRT (America/Sao_Paulo, a máquina já está nesse fuso). Timestamps gravados em JSON: UTC ISO `AAAA-MM-DDTHH:MM:SSZ`.
- Nunca colocar segredo (tópico ntfy, senha SMTP) no repositório — é público. Só em `.env` (fora do git).
- Comentários e mensagens no estilo do projeto: português sem acento em `.py`/`.sh`, explicando o *porquê*.
- `docs/index.html`, `docs/historico.json` e tudo em `dados/` são gerados — não editar à mão (exceção: bootstrap único de `dados/analisados.json`).
- Os dois coletores continuam nunca escrevendo o mesmo arquivo; `dados/analisados.json` e `dados/triagem.json` são escritos só pela raia da análise.

## Review Focus

1. **Dois ciclos no mesmo dia:** item visto às 05h e já analisado não pode reaparecer na análise das 17h; item novo das 17h precisa aparecer. (Task 1, teste `test_segundo_ciclo_do_dia_so_ve_o_novo`.)
2. **Análise que não produziu arquivo** (limite de uso, recusa): o ciclo não pode marcar itens como analisados. (Task 1, `test_fechar_sem_arquivo_falha_e_nao_marca`.)
3. **Painel aberto como arquivo local / sem `historico.json`:** filtro continua funcionando com os 3 dias embutidos e avisa. (Task 3, fallback no JS + teste de payload.)
4. **Canal de alerta não configurado ou fora do ar:** nunca derruba o ciclo; loga e segue. (Task 2, `test_sem_config_nao_envia` e `test_erro_de_rede_nao_levanta`.)
5. **`triagem_pendente.json` malformado ou com chave desconhecida:** ignora a linha ruim, não perde as boas. (Task 1, `test_triagem_ignora_linhas_invalidas`.)

---

### Task 1: Lacuna por chave, `visto_em`, triagem e fechamento da análise

**Files:**
- Modify: `scripts/varredura.py` (`grava_resultado`: grava `visto_em`)
- Modify: `scripts/dou.py` (`artigos`/`classifica`: classificar texto integral)
- Rewrite: `scripts/lacuna_analise.py`
- Create: `scripts/fechar_analise.py`
- Create: `dados/analisados.json` (bootstrap: todas as chaves atuais de `dados/historico.json` — a análise de 29/09 02:40 cobriu tudo que existe hoje)
- Create: `dados/triagem.json` (`{}`)
- Test: `tests/test_lacuna_analise.py` (reescrever), `tests/test_fechar_analise.py` (novo)

**Interfaces:**
- Produces:
  - `lacuna_analise.lacuna(raiz, hoje=None) -> dict` com chaves `ate` (str data), `turno` (str), `ultima_analise` (str id, ex. `"2026-09-29-matinal"` ou `None`), `dados_de_hoje_disponiveis` (bool), `dias_com_dados_na_janela` (lista ordenada das `primeira_vez` distintas dos itens pendentes), `itens` (lista; cada item é o do histórico + campo `chave`).
  - `lacuna_analise.turno_atual(agora=None) -> "matinal"|"noturna"` (respeita env `TURNO`).
  - `lacuna_analise.id_analise(stem) -> (data, turno)`; stems válidos: `AAAA-MM-DD` → turno `"unica"`; `AAAA-MM-DD-matinal`; `AAAA-MM-DD-noturna`. Outros → `None`.
  - `fechar_analise.fechar(raiz, data, turno, chaves) -> dict` (`{"ok": bool, "motivo": str, "triados": int}`): exige `analises/{data}-{turno}.md` não vazio e `dados/analise_status.json` com `data==data` e `turno==turno`; se ok, acrescenta `chaves` a `dados/analisados.json` (`{"chaves": [...ordenadas, sem repetição]}`), incorpora `dados/triagem_pendente.json` (lista de `{"chave","veredito","motivo"}`, veredito ∈ `relevante|contexto|ruido`, só chaves existentes no histórico) em `dados/triagem.json` (`{chave: {"veredito","motivo","em": "AAAA-MM-DD-turno"}}`) e apaga o pendente. CLI: `python3 scripts/fechar_analise.py DATA TURNO ARQUIVO_LACUNA_JSON` (lê as chaves de `itens[].chave` do JSON salvo pelo wrapper), sai 1 se `ok` falso.
  - Itens novos no histórico ganham `visto_em` (UTC ISO).

- [ ] **Step 1: testes da lacuna (falham)** — em `tests/test_lacuna_analise.py`, casos: histórico com 3 itens e `analisados` com 1 → lacuna tem 2 com `chave`; `analisados.json` inexistente → todos pendentes; `test_segundo_ciclo_do_dia_so_ve_o_novo` (item A em analisados, item B novo, mesma `primeira_vez`) → só B; `ultima_analise` escolhe `2026-09-30-noturna` sobre `2026-09-30-matinal` e sobre `2026-09-29` (ordem: data, depois unica < matinal < noturna); `id_analise("README")` é `None`; `turno_atual` com hora 04 → matinal, 17 → noturna, env `TURNO=noturna` vence.
- [ ] **Step 2:** rodar, ver falhar.
- [ ] **Step 3:** reescrever `lacuna_analise.py` (manter `dados_disponiveis`; `chave` vem de `portais.base.chave` recalculada? **Não** — use a própria chave do dicionário do histórico, que é a mesma).
- [ ] **Step 4: testes do fechamento (falham)** em `tests/test_fechar_analise.py`: `test_fechar_sem_arquivo_falha_e_nao_marca`; `test_fechar_status_de_outro_turno_falha`; `test_fechar_ok_marca_chaves_e_triagem`; `test_triagem_ignora_linhas_invalidas` (veredito "talvez", chave inexistente, JSON que não é lista → ignorados, válidos entram); `test_sem_triagem_pendente_ok`.
- [ ] **Step 5:** implementar `fechar_analise.py`, rodar tudo verde.
- [ ] **Step 6:** `varredura.grava_resultado`: ao inserir item novo no histórico, `"visto_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`. `dou.artigos`: guardar `a["_texto_integral"]` (sem corte) e `classifica` usar `a.get("_texto_integral", a.get("_texto",""))`; o item gravado continua com `_texto` cortado. Teste curto em `tests/test_portais_base.py` ou novo `tests/test_dou.py`: termo só depois do caractere 20.000 → não é "descartado".
- [ ] **Step 7:** bootstrap `dados/analisados.json` a partir das chaves atuais do histórico; `dados/triagem.json` = `{}`.

### Task 2: `scripts/notificar.py` — push (ntfy) e e-mail

**Files:**
- Create: `scripts/notificar.py`, `tests/test_notificar.py`
- Modify: `.env.example` (documentar variáveis, valores vazios)

**Interfaces:**
- Consumes: `dados/analise_status.json` (`data`, `turno`, `situacao`, `resumo_curto`, `acoes` int), `analises/{data}-{turno}.md`.
- Produces: CLI `python3 scripts/notificar.py` (alerta do ciclo) e `python3 scripts/notificar.py --falha "mensagem"`. Sempre sai 0.
  - `monta_mensagem(status, md_texto, painel_url) -> dict(titulo, corpo, prioridade, click, md)`; prioridade `"high"` se `acoes > 0`, `"default"` se publicada, `"low"` se sem novidade.
  - `envia_ntfy(msg, topico, servidor="https://ntfy.sh") -> bool` (POST, headers `Title` codificado em UTF-8 via RFC 2047 ou usando o JSON publish endpoint — use o **JSON publish** `POST {servidor}` com corpo `{"topic","title","message","priority"(1-5),"click","tags"}` para evitar problema de acento em header).
  - `envia_email(msg, cfg) -> bool` (smtplib STARTTLS, `multipart/alternative` texto + HTML via `markdown`).
  - Env: `NTFY_TOPICO`, `NTFY_SERVIDOR` (opcional), `SMTP_HOST`, `SMTP_PORTA` (587), `SMTP_USUARIO`, `SMTP_SENHA`, `EMAIL_PARA` (vírgulas), `PAINEL_URL` (padrão `https://rodrigokratzer.github.io/reforma-tributaria-monitor/`).
  - `click` = `PAINEL_URL + "#analise=" + data + "-" + turno`.

- [ ] **Step 1: testes (falham):** `test_monta_mensagem_com_acao_prioridade_alta`, `test_sem_novidade_prioridade_baixa`, `test_sem_config_nao_envia` (nenhuma env → nenhuma chamada de rede, sai 0), `test_erro_de_rede_nao_levanta` (urlopen levanta → `envia_ntfy` devolve False), `test_email_monta_html` (mock `smtplib.SMTP`, confere destinatários e que há parte HTML), `test_falha_monta_prioridade_urgente`.
- [ ] **Step 2–4:** implementar até verde.

### Task 3: Painel — seletor de análises e histórico filtrável

**Files:**
- Modify: `scripts/gerar_painel.py`, `scripts/painel_template.html`
- Create: `tests/test_gerar_painel.py`

**Interfaces:**
- Consumes: `analises/*.md` (stems conforme `lacuna_analise.id_analise`), `dados/triagem.json`, `dados/historico.json`, `dados/analise_status.json`.
- Produces (payload `window.DADOS`, chaves novas/alteradas):
  - `analises`: lista desc de `{"id","data","turno","rotulo","resumo","html"}` — `rotulo` ex. `"30/09/2026 · matinal"`, turno `unica` → `"29/09/2026"`; `resumo` = primeira linha em negrito do md sem `**` (ou `""`).
  - `historico_recente`: itens com `primeira_vez` nos 3 últimos dias com dados (datas distintas mais recentes de `primeira_vez`), sem `texto`, com `triagem` (dict ou null) e `chave`.
  - `novidades`: como hoje + `triagem` + `chave`.
  - `fontes_historico`: lista ordenada das fontes distintas do histórico.
  - `historico_inicio`: menor `primeira_vez` do histórico.
  - remove `historico`, `analise_html`, `analise_data`.
  - Arquivo `docs/historico.json`: lista completa desc (sem `texto`, com `triagem`, `chave`).
- Funções testáveis: `lista_analises(dir) -> list`, `anexa_triagem(itens_dict, triagem) -> list`, `ultimos_dias(itens, n=3) -> list`.

UI (seguir estilo/tokens existentes do template, claro/escuro, funciona em 360px):
- Seção **"Análises"** (substitui "Resumo do dia"): barra com `‹` / `<select>` de rótulos / `›`, mais um `<input type=date>` que pula para a análise mais recente daquele dia (se não houver, mensagem "sem análise em DD/MM"). Seleção reflete em `location.hash = "analise=<id>"`; ao abrir com hash, seleciona.
- **"Publicações novas detectadas"**: chip por triagem — `relevante` (dot `--critical`), `contexto` (dot `--ink-3`), `ruído` (dot `--axis`, linha com opacidade .6); sem triagem e balde revisar → chip "não triado" (dot `--warning`); forte sem triagem → "forte".
- Seção **"Histórico de publicações"**: filtros De / Até (date), Fonte (select, "todas"), Busca (texto; casa título, órgão, ementa, sem acento e sem diferenciar maiúsculas; número "5.343" casa "5343"), Triagem (todas / relevantes / ocultar ruído — padrão "ocultar ruído"). Padrão: De = 2 dias antes da data mais recente, Até = mais recente. Ao mudar De para antes de `historico_recente` ou ao limpar, carrega `historico.json` via `fetch` uma vez; se falhar, aviso "histórico completo indisponível offline — mostrando os últimos 3 dias". Contador "N publicações", até 100 linhas + botão "mostrar mais". Colunas: Visto em, Publicação (+órgão +chip), Fonte. Botão "limpar filtros".
- Cabeçalho: "varredura de <data> · 2x ao dia (05h e 17h)". Rodapé: tirar "é o mesmo texto enviado por e-mail" → "também enviado por alerta (push/e-mail)".

- [ ] **Step 1: testes (falham)** em `tests/test_gerar_painel.py`: `lista_analises` ordena `2026-09-30-noturna`, `2026-09-30-matinal`, `2026-09-29` e ignora `README.md`; rótulo e resumo corretos; `anexa_triagem` põe `triagem` e `chave` e tira `texto`; `ultimos_dias` com datas 26,27,28,29 → só 27–29; `main()` em raiz temporária (monkeypatch `RAIZ/DADOS/ANALISES/DOCS`) gera `docs/historico.json` e `index.html` com o marcador substituído.
- [ ] **Step 2–4:** implementar até verde.
- [ ] **Step 5:** gerar com dados reais e abrir `docs/index.html` num navegador headless (playwright do `.venv`) — screenshot desktop e 390px, conferir console sem erro, filtros por fonte/data/número funcionando.

### Task 4: Orquestração — ciclo 05h/17h, brief, systemd, fallbacks, docs

**Files:**
- Create: `scripts/rodar_ciclo.sh`, `scripts/rodar_analise.sh` (substitui `rodar_analise_diaria.sh`, que é removido)
- Create: `deploy/systemd/reforma-ciclo.service`, `reforma-ciclo.timer`, `reforma-falha@.service`
- Remove: `deploy/systemd/reforma-{dou,varredura,analise}.{service,timer}` (desabilitar na máquina)
- Modify: `scripts/analise_brief.md`, `.github/workflows/dou.yml` (cron `10 10 * * *`), `.github/workflows/varredura.yml` (cron `40 10 * * *`), `docs/operacao-local.md`, `README.md`, `CLAUDE.md`
- Create: `docs/revisao-pendente.md`

`rodar_ciclo.sh`: `TURNO` calculado (`lacuna_analise.turno_atual`), roda `rodar_dou.sh` e `rodar_varredura.sh` (cada um já faz pull/commit/push; falha de um não impede o outro — registrar), depois `rodar_analise.sh "$TURNO"`, e no fim `notificar.py` (ou `--falha` com o que falhou). Sai ≠0 se algo falhou.

`rodar_analise.sh TURNO`: pull; salva a lacuna em `$HOME/.local/state/reforma/lacuna-<data>-<turno>.json`; se `itens` vazio, escreve ele mesmo `analises/<data>-<turno>.md` curto ("Sem publicações novas desde a última análise.") + status `sem_novidade` sem chamar o Claude; senão chama `claude -p` com prompt que aponta o brief e o arquivo da lacuna, proíbe git; depois `fechar_analise.py`; `gerar_painel.py`; `git add analises dados docs`; commit `analise <data> <turno>: <resumo>`; push.

Brief: saída passa a ser **sempre** `analises/AAAA-MM-DD-<turno>.md` (sem novidade = texto curto dizendo o que chegou e por que nada importa); status ganha `turno` e `acoes`; nova seção "Triagem por item" pedindo `dados/triagem_pendente.json` com um veredito para **todo** item da lacuna; título usa o período dos itens; não fazer git.

Timer: `OnCalendar=*-*-* 05:00:00` e `OnCalendar=*-*-* 17:00:00`, `Persistent=true`. Service: `EnvironmentFile=-.../.env`, flock, `TimeoutStartSec=7200`, `OnFailure=reforma-falha@%n.service` (que roda `notificar.py --falha "unidade %i falhou"`).

- [ ] Steps: escrever scripts; `bash -n`; rodar o ciclo de verdade uma vez (manual, TURNO=noturna) e conferir commit, painel publicado e push recebido; instalar units, desabilitar as 3 antigas, `systemctl list-timers`.
