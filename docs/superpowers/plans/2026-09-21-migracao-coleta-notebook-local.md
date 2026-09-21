# Migração da coleta e análise para notebook local — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rodar o pipeline inteiro (DOU, 12 portais, análise diária, painel, commit/push) todos os dias a partir do notebook `lenovo-claude`, via systemd timers, com o GitHub Actions atual virando um plano B automático que só age se o notebook não coletou.

**Architecture:** Três pares service+timer do systemd (DOU 01:07, varredura 02:10, análise 02:40, horário de Brasília — timezone do sistema já é `America/Sao_Paulo`), cada um chamando um script wrapper em `scripts/` que roda o script Python existente (inalterado), regenera o painel, e faz commit+push. `varredura.yml`/`dou.yml` do GitHub Actions perdem seus horários "primários" e passam a rodar só 3h depois, todo dia, como plano B condicional (reaproveitando o padrão "só roda se o arquivo do dia não existe" que `varredura.yml` já tinha).

**Tech Stack:** Python 3.14 + venv, Playwright/Chromium, systemd (service + timer units), Claude Code CLI (`claude -p`) para a análise, GitHub Actions (YAML), git/gh.

**Spec:** [docs/superpowers/specs/2026-09-21-migracao-coleta-notebook-local-design.md](../specs/2026-09-21-migracao-coleta-notebook-local-design.md)

## Global Constraints

- Timezone do sistema é `America/Sao_Paulo` — `OnCalendar=` do systemd usa horário local direto, sem conversão.
- Agendamento cobre **todos os dias** (não só dia útil) — em todos os timers/crons deste plano.
- Não modificar a lógica de `scripts/varredura.py`, `scripts/dou.py`, `scripts/dou_diario.py`, `scripts/gerar_painel.py`, `scripts/lacuna_analise.py`, `scripts/portais/*` — só chamá-los.
- Credenciais (`INLABS_EMAIL`, `INLABS_SENHA`) vêm de `.env` na raiz do repo via `EnvironmentFile=` do systemd, nunca hardcoded em unit file nem em código.
- Identidade git deste notebook: `user.name = rodrigokratzer`, `user.email = 316981768+rodrigokratzer@users.noreply.github.com` (e-mail privado do GitHub — repositório é público).
- Repositório em `/home/rodrigo/projects/reforma-tributaria-monitor`, remoto `origin` já autenticado via `gh` (HTTPS).
- Qualquer passo com `sudo` precisa ser rodado no terminal visível ao usuário (ele digita a senha) — um subagente não consegue responder ao prompt de senha sozinho. Marque esses passos claramente.
- Execução: **subagent-driven** — a sessão principal atua como gerente: dispara um subagente por task, revisa o que ele entregou (diff, saída de comando, log) antes de liberar a próxima task, e só then segue adiante.

## Review Focus

1. **Notebook reinicia ou fica desligado no horário agendado** — o timer precisa recuperar sozinho ao ligar de novo, sem intervenção manual. `Persistent=true` é idêntico nas três unidades (Task 3, 4, 5); testado uma vez de verdade na Task 3 Step 7 — é o mesmo mecanismo do systemd, não lógica própria de cada script, então provar uma vez cobre as três.
2. **`.env` ausente ou incompleto no primeiro deploy** — `dou_diario.py` já trata a ausência de credencial como "pular a fonte", não como falha total; a integração via `EnvironmentFile=-` (com `-`, opcional) precisa preservar esse comportamento em vez de derrubar o serviço. (Task 3.)
3. **`claude -p` falha ou trava na análise diária** (erro de rede, sessão expirada, crash) — o wrapper precisa terminar com código de saída não-zero para o systemd marcar o serviço como falho (visível em `systemctl status` / `journalctl`), em vez de silenciosamente não fazer nada. (Task 5.)
4. **Notebook e GitHub Actions coletando o mesmo dia ao mesmo tempo** (corrida rara se o notebook atrasar mais de 3h) — o plano B só deve agir se o arquivo do dia realmente não existir; verificar a condição isoladamente, sem depender de esperar 3h de verdade em teste. (Task 6.)
5. **Ambiente Python quebrado silenciosamente** (venv apagado, path errado, dependência de sistema faltando após atualização do SO) — os `ExecStart=` dos serviços devem usar caminho absoluto do Python do venv, não depender de `PATH`, para falhar de forma visível em vez de rodar com o Python errado do sistema. (Task 1, 3, 4, 5.)

---

### Task 1: Ambiente Python local

**Files:**
- Modify: nenhum arquivo do repo (instala dependências de sistema e cria `.venv/`, que não é versionado)

**Interfaces:**
- Produces: `.venv/bin/python3` funcional com `playwright` e `markdown` instalados, Chromium baixado; `python3 -m unittest discover -s tests -v` passando — todas as tasks seguintes que rodam scripts Python dependem deste executável.

- [ ] **Step 1: Instalar pacotes de sistema para venv e pip**

Requer sudo — rodar no terminal visível:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
```

- [ ] **Step 2: Criar o venv e instalar dependências do projeto**

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Expected: instala `playwright==1.56.0` e `markdown==3.7` sem erro.

- [ ] **Step 3: Instalar o Chromium do Playwright**

Requer sudo (dependências de sistema do navegador) — rodar no terminal visível:

```bash
.venv/bin/playwright install --with-deps chromium
```

- [ ] **Step 4: Rodar a suíte de testes existente para confirmar a base**

```bash
.venv/bin/python3 -m unittest discover -s tests -v
```

Expected: todos os testes de `test_lacuna_analise.py`, `test_portais_base.py`, `test_portal_cgibs.py` passam (`OK` no final). Se algo falhar aqui, é um problema do ambiente, não desta migração — pare e investigue antes de seguir.

- [ ] **Step 5: Rodar a varredura uma vez manualmente para validar o ambiente completo**

```bash
DATA_REF=$(date +%Y-%m-%d) .venv/bin/python3 scripts/varredura.py
```

Expected: imprime o progresso de cada uma das 12 fontes em stderr, sem traceback do Python (falha de rede de um site específico é esperada e ok — é o que `erro`/`erro_browser` por fonte já cobre).

---

### Task 2: Credenciais e identidade git

**Files:**
- Create: `.env.example`
- Modify: `.gitignore`
- Verify: identidade git local (já configurada nesta sessão; este passo a torna reproduzível/idempotente)

**Interfaces:**
- Produces: `.env` (não versionado, preenchido manualmente pelo humano) lido por `EnvironmentFile=` nas unidades systemd da Task 3 e 5.

- [ ] **Step 1: Adicionar `.env` ao `.gitignore`**

Adicionar ao final de `/home/rodrigo/projects/reforma-tributaria-monitor/.gitignore`:

```
.env
```

- [ ] **Step 2: Criar `.env.example` versionado, como referência**

Criar `/home/rodrigo/projects/reforma-tributaria-monitor/.env.example`:

```
INLABS_EMAIL=
INLABS_SENHA=
```

- [ ] **Step 3: Confirmar a identidade git local (idempotente)**

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
git config user.name "rodrigokratzer"
git config user.email "316981768+rodrigokratzer@users.noreply.github.com"
git config user.name && git config user.email
```

Expected: imprime exatamente os dois valores acima.

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example
git commit -m "chore: preparar .env local para credenciais do INLABS"
```

- [ ] **Step 5 (manual, do humano — não do subagente): preencher `.env`**

Criar `/home/rodrigo/projects/reforma-tributaria-monitor/.env` (fora do git) com:

```
INLABS_EMAIL=<e-mail cadastrado em inlabs.in.gov.br>
INLABS_SENHA=<senha correspondente>
```

O subagente desta task **não tem esses valores** e não deve inventá-los nem pedir por eles em texto plano — sinalize ao gerente (sessão principal) que este passo manual está pendente e siga para a próxima task; a coleta do DOU funciona sem `.env` (pula a fonte, como já acontece hoje sem os secrets), então isso não bloqueia o restante da migração.

---

### Task 3: Unidade systemd — DOU (INLABS)

**Files:**
- Create: `scripts/rodar_dou.sh`
- Create: `deploy/systemd/reforma-dou.service`
- Create: `deploy/systemd/reforma-dou.timer`

**Interfaces:**
- Consumes: `.venv/bin/python3` (Task 1), `.env` (Task 2, opcional — `EnvironmentFile=-` não falha se ausente)
- Produces: `dados/AAAA-MM-DD-dou.json`, `dados/novidades_dou.json`, `docs/index.html` atualizados e commitados diariamente às 01:07.

- [ ] **Step 1: Criar o script wrapper `scripts/rodar_dou.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --rebase --autostash -q
.venv/bin/python3 scripts/dou_diario.py
.venv/bin/python3 scripts/gerar_painel.py
git add dados docs
if git diff --staged --quiet; then
  echo "Nada mudou hoje (DOU)."
else
  git commit -m "dou $(date +%Y-%m-%d)"
  git push
fi
```

```bash
chmod +x scripts/rodar_dou.sh
```

- [ ] **Step 2: Testar o wrapper manualmente antes de agendar**

```bash
./scripts/rodar_dou.sh
```

Expected: roda sem traceback; se `.env` ainda não foi preenchido (Task 2, Step 5), a fonte DOU aparece como pulada por falta de credencial — isso é esperado, não é falha do wrapper.

- [ ] **Step 3: Criar `deploy/systemd/reforma-dou.service`**

```ini
[Unit]
Description=Reforma Tributaria - coleta do DOU (INLABS)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=rodrigo
Group=rodrigo
Environment=HOME=/home/rodrigo
WorkingDirectory=/home/rodrigo/projects/reforma-tributaria-monitor
EnvironmentFile=-/home/rodrigo/projects/reforma-tributaria-monitor/.env
ExecStart=/home/rodrigo/projects/reforma-tributaria-monitor/scripts/rodar_dou.sh
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 4: Criar `deploy/systemd/reforma-dou.timer`**

```ini
[Unit]
Description=Agenda diaria da coleta do DOU (01:07, horario de Brasilia, todos os dias)

[Timer]
OnCalendar=*-*-* 01:07:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Instalar e ativar o timer (requer sudo — rodar no terminal visível)**

```bash
sudo cp deploy/systemd/reforma-dou.service deploy/systemd/reforma-dou.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reforma-dou.timer
systemctl list-timers reforma-dou.timer
```

Expected: `list-timers` mostra `reforma-dou.timer` com o próximo disparo em 01:07 do dia seguinte (ou hoje, se ainda não passou).

- [ ] **Step 6: Testar o serviço via systemd diretamente (não só o script solto)**

```bash
sudo systemctl start reforma-dou.service
sudo systemctl status reforma-dou.service
journalctl -u reforma-dou.service -n 30 --no-pager
```

Expected: `status` mostra `Active: inactive (dead)` com `SUCCESS` no último resultado (serviço `oneshot` completo), e o `journalctl` mostra a saída do script sem traceback.

- [ ] **Step 7: Testar o catch-up do `Persistent=true` (Review Focus #1)**

```bash
sudo systemctl stop reforma-dou.timer
sudo systemctl disable reforma-dou.timer
sudo systemctl daemon-reload
sudo systemctl enable --now reforma-dou.timer
systemctl status reforma-dou.timer --no-pager
```

Expected: como o horário de 01:07 de hoje já passou (estamos rodando isso durante o dia), `Persistent=true` faz o timer dispara-lo quase imediatamente ao ser reativado — confirme no `journalctl -u reforma-dou.service` um novo run logo após o `enable --now`. Isso confirma que uma reinicialização do notebook durante a janela agendada não perde o dia.

- [ ] **Step 8: Commit**

```bash
git add scripts/rodar_dou.sh deploy/systemd/reforma-dou.service deploy/systemd/reforma-dou.timer
git commit -m "feat: agendar coleta do DOU via systemd timer local"
```

---

### Task 4: Unidade systemd — Varredura (12 portais)

**Files:**
- Create: `scripts/rodar_varredura.sh`
- Create: `deploy/systemd/reforma-varredura.service`
- Create: `deploy/systemd/reforma-varredura.timer`

**Interfaces:**
- Consumes: `.venv/bin/python3` (Task 1)
- Produces: `dados/AAAA-MM-DD.json`, `dados/novidades.json`, `docs/index.html` atualizados e commitados diariamente às 02:10.

- [ ] **Step 1: Criar `scripts/rodar_varredura.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --rebase --autostash -q
.venv/bin/python3 scripts/varredura.py
.venv/bin/python3 scripts/gerar_painel.py
git add dados docs
if git diff --staged --quiet; then
  echo "Nada mudou hoje (varredura)."
else
  git commit -m "varredura $(date +%Y-%m-%d)"
  git push
fi
```

```bash
chmod +x scripts/rodar_varredura.sh
```

- [ ] **Step 2: Testar o wrapper manualmente**

```bash
./scripts/rodar_varredura.sh
```

Expected: mesmo comportamento já visto na Task 1 Step 5 (falhas pontuais de fonte são ok), mas agora seguido de `gerar_painel.py` e, se houve mudança, um commit local.

- [ ] **Step 3: Criar `deploy/systemd/reforma-varredura.service`**

```ini
[Unit]
Description=Reforma Tributaria - varredura dos 12 portais web
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=rodrigo
Group=rodrigo
Environment=HOME=/home/rodrigo
WorkingDirectory=/home/rodrigo/projects/reforma-tributaria-monitor
ExecStart=/home/rodrigo/projects/reforma-tributaria-monitor/scripts/rodar_varredura.sh
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
```

(`TimeoutStartSec=900` dá 15 minutos de folga acima do orçamento interno de 10 minutos do próprio `varredura.py`, para o systemd nunca matar o processo antes do script fechar sozinho.)

- [ ] **Step 4: Criar `deploy/systemd/reforma-varredura.timer`**

```ini
[Unit]
Description=Agenda diaria da varredura dos 12 portais (02:10, horario de Brasilia, todos os dias)

[Timer]
OnCalendar=*-*-* 02:10:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Instalar e ativar (requer sudo — terminal visível)**

```bash
sudo cp deploy/systemd/reforma-varredura.service deploy/systemd/reforma-varredura.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reforma-varredura.timer
systemctl list-timers reforma-varredura.timer
```

- [ ] **Step 6: Testar o serviço via systemd**

```bash
sudo systemctl start reforma-varredura.service
sudo systemctl status reforma-varredura.service
journalctl -u reforma-varredura.service -n 50 --no-pager
```

Expected: `SUCCESS`, sem traceback, progresso das 12 fontes visível no log.

- [ ] **Step 7: Commit**

```bash
git add scripts/rodar_varredura.sh deploy/systemd/reforma-varredura.service deploy/systemd/reforma-varredura.timer
git commit -m "feat: agendar varredura dos 12 portais via systemd timer local"
```

---

### Task 5: Script de análise diária + unidade systemd

**Files:**
- Create: `scripts/rodar_analise_diaria.sh`
- Create: `deploy/systemd/reforma-analise.service`
- Create: `deploy/systemd/reforma-analise.timer`

**Interfaces:**
- Consumes: `claude` CLI (já instalado neste notebook, `claude --version` funcional), `scripts/analise_brief.md`, `scripts/lacuna_analise.py` (inalterados)
- Produces: `analises/AAAA-MM-DD.md` (quando há novidade) e/ou `dados/analise_status.json` atualizado, commitados e enviados diariamente às 02:40. Código de saída não-zero quando o `claude -p` falha (Review Focus #3).

- [ ] **Step 1: Criar `scripts/rodar_analise_diaria.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
git pull --rebase --autostash -q

PROMPT="Leia scripts/analise_brief.md e siga as instrucoes dele por completo, para a data de hoje ($(date +%Y-%m-%d)). Rode scripts/lacuna_analise.py para obter a lacuna de cobertura, aplique o criterio do brief aos itens novos, e produza a saida exatamente como o brief especifica: analises/AAAA-MM-DD.md quando houver novidade relevante, ou so dados/analise_status.json quando nao houver. Ao final, se analises/ ou dados/analise_status.json mudaram, faca 'git add', commit com mensagem no formato 'analise AAAA-MM-DD: <resumo curto>' e 'git push'. Nao pergunte nada - decida e execute sozinho."

claude -p "$PROMPT" --permission-mode bypassPermissions --output-format json \
  > /tmp/reforma-analise-ultima-saida.json
codigo=$?

if [ $codigo -ne 0 ]; then
  echo "claude -p saiu com codigo $codigo - analise diaria NAO concluida. Ver /tmp/reforma-analise-ultima-saida.json" >&2
  exit $codigo
fi

echo "Analise diaria concluida (codigo 0)."
```

```bash
chmod +x scripts/rodar_analise_diaria.sh
```

- [ ] **Step 2: Testar o wrapper manualmente**

```bash
./scripts/rodar_analise_diaria.sh
echo "codigo de saida: $?"
```

Expected: código de saída `0`; `analises/AAAA-MM-DD.md` criado (se houve novidade desde a última análise publicada) ou `dados/analise_status.json` atualizado com `"situacao": "sem_novidade"`; commit e push feitos automaticamente pelo próprio Claude, seguindo o brief.

- [ ] **Step 3: Testar o caminho de falha do wrapper (Review Focus #3)**

Simule uma falha do `claude` CLI temporariamente (ex.: renomeie o binário ou aponte `PATH` errado só para este teste) e confirme que o script termina com código diferente de zero:

```bash
PATH=/usr/bin ./scripts/rodar_analise_diaria.sh; echo "codigo: $?"
```

Expected: `claude: comando não encontrado` (ou equivalente) e código de saída diferente de `0` — confirma que uma falha real do `claude` não passa em silêncio.

- [ ] **Step 4: Criar `deploy/systemd/reforma-analise.service`**

```ini
[Unit]
Description=Reforma Tributaria - analise diaria automatizada (Claude)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=rodrigo
Group=rodrigo
Environment=HOME=/home/rodrigo
WorkingDirectory=/home/rodrigo/projects/reforma-tributaria-monitor
ExecStart=/home/rodrigo/projects/reforma-tributaria-monitor/scripts/rodar_analise_diaria.sh
TimeoutStartSec=1800
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 5: Criar `deploy/systemd/reforma-analise.timer`**

```ini
[Unit]
Description=Agenda diaria da analise automatizada (02:40, horario de Brasilia, todos os dias, depois da varredura)

[Timer]
OnCalendar=*-*-* 02:40:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 6: Instalar e ativar (requer sudo — terminal visível)**

```bash
sudo cp deploy/systemd/reforma-analise.service deploy/systemd/reforma-analise.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reforma-analise.timer
systemctl list-timers reforma-analise.timer
```

- [ ] **Step 7: Commit**

```bash
git add scripts/rodar_analise_diaria.sh deploy/systemd/reforma-analise.service deploy/systemd/reforma-analise.timer
git commit -m "feat: agendar analise diaria via systemd timer local, chamando claude -p"
```

---

### Task 6: GitHub Actions como plano B diário

**Files:**
- Modify: `.github/workflows/varredura.yml`
- Modify: `.github/workflows/dou.yml`

**Interfaces:**
- Consumes: nenhum artefato das tasks anteriores diretamente — edita só os workflows.
- Produces: workflows que só coletam quando o notebook não coletou (Review Focus #4), rodando 3h depois do horário local, todos os dias.

- [ ] **Step 1: Trocar o bloco `schedule:` de `varredura.yml`**

Old:
```yaml
on:
  schedule:
    # 05:10 UTC = 02:10 em Brasília (UTC-3), de segunda a sexta — 1h depois
    # do DOU (01:07) para não concorrer por horário com ele, e bem antes do
    # e-mail das 07h para o dado já estar no ar.
    - cron: "10 5 * * 1-5"
    # Rede de segurança: às vezes o cron do GitHub não é só "melhor esforço e
    # atrasa" — em 2026-09-15 e 2026-09-16 ele simplesmente não disparou
    # (nenhum run com evento "schedule" nesses dias). Este segundo horário,
    # 1h depois, repete a varredura só quando o arquivo do dia ainda não
    # existe (ver passo "Verificar se já varreu hoje" abaixo), então não
    # dobra o trabalho nos dias em que o primeiro horário funcionou. Os
    # minutos (:10 e :15) são de propósito fora do início exato da hora —
    # ver comentário equivalente em dou.yml sobre o incidente de 27-28/08.
    - cron: "15 6 * * 1-5"
  workflow_dispatch:        # permite disparar na mão pela aba Actions
```

New:
```yaml
on:
  schedule:
    # Plano B: a coleta primária agora roda no notebook lenovo-claude, todo
    # dia às 02:10 Brasília (systemd timer, ver docs/operacao-local.md). Este
    # workflow só age como rede de segurança, 3h depois — 08:10 UTC = 05:10
    # Brasília, todo dia (não só dia útil, porque fontes publicam fim de
    # semana também) — e só coleta de verdade se dados/AAAA-MM-DD.json ainda
    # não existir (ver "Verificar se já varreu hoje" abaixo). O minuto (:10)
    # é de propósito fora do início exato da hora — ver comentário
    # equivalente em dou.yml sobre o incidente de 27-28/08.
    - cron: "10 8 * * *"
  workflow_dispatch:        # permite disparar na mão pela aba Actions
```

- [ ] **Step 2: Trocar o bloco `schedule:` de `dou.yml`**

Old:
```yaml
on:
  schedule:
    # Fora do início exato da hora de propósito: o GitHub documenta que
    # "high load times include the start of each hour", e um cron pode
    # atrasar ou ser pulado silenciosamente nesses horários — foi o que
    # aconteceu em 27-28/08/2026, quando o agendamento parou de disparar
    # por dois dias seguidos sem erro nenhum.
    - cron: "7 4 * * 1-5"   # 04:07 UTC ~= 01:07 Brasília, dias úteis
  workflow_dispatch:        # permite disparar na mão pela aba Actions
```

New:
```yaml
on:
  schedule:
    # Plano B: a coleta primária do DOU agora roda no notebook lenovo-claude,
    # todo dia às 01:07 Brasília (systemd timer, ver docs/operacao-local.md).
    # Este workflow só age como rede de segurança, 3h depois — 07:10 UTC =
    # 04:10 Brasília, todo dia — e só coleta de verdade se
    # dados/AAAA-MM-DD-dou.json ainda não existir (ver "Verificar se já
    # coletou hoje" abaixo). Fora do início exato da hora de propósito: o
    # GitHub documenta que "high load times include the start of each hour",
    # e um cron pode atrasar ou ser pulado silenciosamente nesses horários —
    # foi o que aconteceu em 27-28/08/2026.
    - cron: "10 7 * * *"
  workflow_dispatch:        # permite disparar na mão pela aba Actions
```

- [ ] **Step 3: Adicionar a checagem "já coletou hoje" em `dou.yml`**

Old (bloco `jobs.coletar.steps`, antes de "Coletar DOU (INLABS)"):
```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Coletar DOU (INLABS)
        env:
          INLABS_EMAIL: ${{ secrets.INLABS_EMAIL }}
          INLABS_SENHA: ${{ secrets.INLABS_SENHA }}
        run: python scripts/dou_diario.py
```

New:
```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Verificar se já coletou hoje
        id: checar
        if: github.event_name == 'schedule'
        run: |
          hoje=$(date -u +%F)
          if [ -f "dados/${hoje}-dou.json" ]; then
            echo "ja_rodou=true" >> "$GITHUB_OUTPUT"
          else
            echo "ja_rodou=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Coletar DOU (INLABS)
        if: github.event_name == 'workflow_dispatch' || (github.event_name == 'schedule' && steps.checar.outputs.ja_rodou != 'true')
        env:
          INLABS_EMAIL: ${{ secrets.INLABS_EMAIL }}
          INLABS_SENHA: ${{ secrets.INLABS_SENHA }}
        run: python scripts/dou_diario.py
```

(`varredura.yml` já tem essa checagem — não precisa de mudança nessa parte, só no `schedule:` do Step 1.)

- [ ] **Step 4: Verificar a lógica da condição isoladamente (Review Focus #4), sem esperar 3h de verdade**

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
hoje=$(date -u +%F)
touch "dados/${hoje}-dou.json.teste"
mv "dados/${hoje}-dou.json.teste" "/tmp/teste-${hoje}-dou.json"
# simula "arquivo existe":
if [ -f "/tmp/teste-${hoje}-dou.json" ]; then echo "ja_rodou=true"; else echo "ja_rodou=false"; fi
rm -f "/tmp/teste-${hoje}-dou.json"
```

Expected: imprime `ja_rodou=true`, confirmando que a expressão do step (`[ -f "dados/${hoje}-dou.json" ]`) funciona como esperado antes de confiar nela dentro do workflow.

- [ ] **Step 5: Validar o YAML**

```bash
gh workflow view "Varredura Reforma Tributária" --yaml > /tmp/check-varredura.yml 2>&1 || true
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/varredura.yml'))" && echo "varredura.yml OK"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/dou.yml'))" && echo "dou.yml OK"
```

Expected: ambos imprimem `OK`, sem erro de parsing.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/varredura.yml .github/workflows/dou.yml
git commit -m "ci: GitHub Actions vira plano B diario, 3h depois do notebook local"
```

Não faça push ainda — o gerente (sessão principal) confirma com o humano antes de qualquer push para o GitHub, conforme já combinado.

---

### Task 7: Verificação end-to-end

**Files:** nenhum novo — só validação do conjunto.

**Interfaces:**
- Consumes: tudo das Tasks 1–6.
- Produces: confirmação de que o pipeline local roda de ponta a ponta e que o plano B do GitHub Actions não duplica trabalho.

- [ ] **Step 1: Conferir os três timers agendados**

```bash
systemctl list-timers 'reforma-*' --no-pager
```

Expected: `reforma-dou.timer`, `reforma-varredura.timer`, `reforma-analise.timer`, cada um com `NEXT` apontando para o horário correto do dia seguinte (ou de hoje, se ainda não passou).

- [ ] **Step 2: Rodar a sequência completa manualmente, na ordem real**

```bash
cd /home/rodrigo/projects/reforma-tributaria-monitor
sudo systemctl start reforma-dou.service && sleep 2 && systemctl status reforma-dou.service --no-pager
sudo systemctl start reforma-varredura.service && sleep 2 && systemctl status reforma-varredura.service --no-pager
sudo systemctl start reforma-analise.service && sleep 2 && systemctl status reforma-analise.service --no-pager
```

Expected: os três terminam com `SUCCESS`; `git log --oneline -5` mostra os commits `dou ...`, `varredura ...` e `analise ...` (ou "nada mudou" nos casos sem novidade, sem commit).

- [ ] **Step 3: Confirmar que o painel gerado reflete os dados novos**

```bash
grep -o '"data":"[0-9-]*"' docs/index.html | head -3
```

Expected: a data mais recente embutida no painel é a de hoje.

- [ ] **Step 4: Revisão final do humano antes de qualquer push para o GitHub**

Listar tudo que está pronto para envio e aguardar confirmação explícita do usuário:

```bash
git log origin/main..HEAD --oneline
git status --short
```

Apresentar esta lista ao usuário e só rodar `git push` (dos commits desta migração, incluindo os workflows da Task 6) depois de um "sim" explícito — mesma régua já usada neste projeto para qualquer ação que afete o GitHub público.

---

### Task 8: Documentação

**Files:**
- Create: `docs/operacao-local.md`
- Modify: `CLAUDE.md` (seção "GitHub Actions workflows")
- Modify: `README.md` (seção "Estrutura", uma linha apontando para o novo doc)

**Interfaces:** nenhuma — só texto.

- [ ] **Step 1: Criar `docs/operacao-local.md`**

```markdown
# Operação local (lenovo-claude)

Este documento descreve como esta instância específica do projeto roda de
fato — não é o guia genérico de fork (esse continua em README.md, "Como
rodar uma cópia sua", e continua funcionando só com GitHub Actions).

## O quê roda onde

| Etapa | Onde | Quando |
|---|---|---|
| DOU (INLABS) | `lenovo-claude`, systemd | 01:07, todo dia |
| 12 portais web | `lenovo-claude`, systemd | 02:10, todo dia |
| Análise diária | `lenovo-claude`, systemd, via `claude -p` | 02:40, todo dia |
| Plano B (DOU) | GitHub Actions | 04:10, todo dia, só se o notebook não coletou |
| Plano B (portais) | GitHub Actions | 05:10, todo dia, só se o notebook não coletou |

## Verificar status

```bash
systemctl list-timers 'reforma-*'
journalctl -u reforma-dou.service -n 50
journalctl -u reforma-varredura.service -n 50
journalctl -u reforma-analise.service -n 50
```

## Credenciais

`INLABS_EMAIL`/`INLABS_SENHA` ficam em `.env` na raiz do repo (fora do git,
ver `.env.example` para o formato), lidas pelas unidades systemd via
`EnvironmentFile=`.

## Reinstalar as unidades systemd depois de editar os arquivos em `deploy/systemd/`

```bash
sudo cp deploy/systemd/reforma-*.service deploy/systemd/reforma-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart reforma-dou.timer reforma-varredura.timer reforma-analise.timer
```
```

- [ ] **Step 2: Atualizar a seção "GitHub Actions workflows" do `CLAUDE.md`**

Old:
```
### GitHub Actions workflows

- `.github/workflows/varredura.yml` — scrapes the 12 web sources on two crons
  (weekdays): 02:10 BRT, plus a 03:15 catch-up that only re-scrapes if the
  day's `dados/AAAA-MM-DD.json` doesn't exist yet (the GitHub cron scheduler
  can silently skip a run — see Gotchas). Also fires on `push` to
  `estado.json`, `analises/**`, `dados/analise_status.json`, `dados/*-dou.json`,
  `dados/novidades_dou.json`, or `scripts/**`, and on `workflow_dispatch`. The
  scrape step only runs for `workflow_dispatch` or a `schedule` event that
  still needs to scrape — `push` always just regenerates the panel.
- `.github/workflows/dou.yml` — scrapes the DOU on its own cron (01:07 BRT), with
  its own 60-minute budget, decoupled from the web scrape's timing and time budget.
- `.github/workflows/medicao-inlabs.yml` — one-off recall measurement against the
  full DOU corpus. Self-retires: skips its body once `dados/medicao_inlabs.json`
  already exists.
```

New:
```
### Where this actually runs

Primary execution moved to a dedicated always-on local machine — see
`docs/operacao-local.md` for the full picture (systemd timers, schedule,
credentials). Summary:

### GitHub Actions workflows (now a daily fallback, not primary)

- `.github/workflows/varredura.yml` — runs daily at 05:10 BRT (3h after the
  local systemd timer), and only actually scrapes if `dados/AAAA-MM-DD.json`
  doesn't exist yet — i.e. only when the local machine failed to collect.
  Also fires on `push` (same paths as before) and `workflow_dispatch`.
- `.github/workflows/dou.yml` — same fallback pattern, daily at 04:10 BRT,
  only scrapes if `dados/AAAA-MM-DD-dou.json` doesn't exist yet.
- `.github/workflows/medicao-inlabs.yml` — unchanged, one-off recall
  measurement, self-retires once `dados/medicao_inlabs.json` exists.
```

- [ ] **Step 3: Adicionar uma linha em `README.md`, seção "Estrutura", apontando para o novo doc**

Adicionar logo após a listagem em bloco de código da seção "Estrutura":

```
Esta instância específica do projeto roda com coleta e análise primárias
num notebook dedicado, não só em GitHub Actions — ver
[`docs/operacao-local.md`](docs/operacao-local.md) para como isso funciona
na prática. O guia de fork logo abaixo continua valendo tal como está: só
GitHub Actions, sem depender de máquina local nenhuma.
```

- [ ] **Step 4: Commit**

```bash
git add docs/operacao-local.md CLAUDE.md README.md
git commit -m "docs: documentar operacao local (systemd) e GitHub Actions como plano B"
```
