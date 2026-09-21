# Migração da coleta e análise para notebook local — design

**Data:** 2026-09-21
**Status:** aprovado para plano de implementação

## Contexto e objetivo

O pipeline roda hoje inteiramente em GitHub Actions (coleta dos 12 portais,
DOU) mais um agente de análise que deveria rodar agendado na nuvem do Claude
Code. Dois problemas motivam esta migração:

**1. Falha de rede específica do CGIBS contra o IP do GitHub Actions.**
Medido diretamente em `dados/AAAA-MM-DD.json` dos últimos ~25 dias: a fonte
"CGIBS - Notícias" falhou (`net::ERR_CONNECTION_RESET` ou timeout) em **8 de
25 dias (32%)**; quase todas as páginas do CGIBS falharam juntas no mesmo dia
(20/08), sinal de bloqueio/instabilidade de rede contra o range de IP de
datacenter do GitHub, não bug no código. O restante do pipeline (workflows em
si) tem ~98,5% de sucesso — o problema é a coleta de fontes específicas
dentro de runs "verdes", não o orquestrador.

**2. A análise diária não tem rotina agendada ativa.** O README documenta a
análise como um agente agendado via skill `/schedule`, externo ao
repositório. Nenhuma tarefa agendada foi encontrada na conta que opera o
projeto — o commit de análise mais recente foi gerado manualmente.

**Reversão consciente de uma decisão anterior:** o spec
`2026-08-25-analise-diaria-automatizada-design.md` fixou como restrição
orientadora *"precisa funcionar mesmo com o computador do usuário desligado —
não pode depender de uma máquina local ligada"*, e por isso colocou a análise
na nuvem. Essa restrição deixa de valer: o usuário dedicou um notebook
(`lenovo-claude`) exclusivamente para este tipo de tarefa, sempre ligado —
suspensão/hibernação foram desabilitadas a nível de sistema
(`systemctl mask sleep.target suspend.target hibernate.target
hybrid-sleep.target`). Este documento substitui aquela restrição
explicitamente; não a ignora por omissão.

## Decisões já tomadas (resumo das aprovações)

| Decisão | Escolha |
|---|---|
| Escopo | Pipeline inteiro migra: coleta dos 12 portais, DOU, análise diária, geração do painel, commit e push |
| Onde roda | `lenovo-claude` (notebook dedicado, sempre ligado, IP residencial) |
| Frequência | **Todos os dias** (não só dia útil) — fontes publicam fim de semana; análise e o plano B do GitHub Actions seguem o mesmo padrão |
| Agendador local | systemd timers (`Persistent=true`), não cron — pega execução perdida se o notebook estiver desligado/reiniciando no horário, e dá log estruturado via `journalctl` sem esforço extra |
| GitHub Actions | Continua ativo, mas como **plano B automático**, 3h depois do horário local, reaproveitando o padrão "só roda se o arquivo do dia ainda não existe" que `varredura.yml` já usa no catch-up |
| Separação DOU vs portais | Mantida — timers separados, nunca um orquestrador único (é o mesmo princípio de "nunca mesclar coletas no mesmo arquivo/job" já documentado no README) |
| Credenciais INLABS | Saem dos GitHub Secrets, vão para `.env` local (fora do git), carregadas via `EnvironmentFile=` do systemd — sem mudar `scripts/dou.py` |
| Identidade git local | `rodrigokratzer@users.noreply.github.com` (e-mail privado do GitHub) em vez do e-mail pessoal, porque o repositório é público |
| Erro vs "sem itens" | **Sem mudança de lógica** — `scripts/varredura.py` já separa `fontes_com_erro` de `fontes_sem_itens`; a migração preserva esse comportamento porque reusa o script inalterado |

## Arquitetura

```
                    lenovo-claude (systemd timers, todos os dias)
┌──────────────────────────────────────────────────────────────────────┐
│  01:07  reforma-dou.timer      → dou_diario.py → gerar_painel.py     │
│                                    → commit/push                      │
│                                                                        │
│  02:10  reforma-varredura.timer → varredura.py → gerar_painel.py     │
│                                    → commit/push                      │
│                                                                        │
│  02:40  reforma-analise.timer  → lacuna_analise.py → claude (CLI,    │
│                                    não-interativo) lê analise_brief.md│
│                                    → analises/AAAA-MM-DD.md ou só     │
│                                    analise_status.json → commit/push  │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ push em dados/*.json, analises/**,
                                  │ dados/analise_status.json
                                  ▼
                    GitHub (origin) — Pages republica docs/ automaticamente

                    GitHub Actions (plano B automático, todos os dias)
┌──────────────────────────────────────────────────────────────────────┐
│  04:10  dou.yml        → roda só se dados/AAAA-MM-DD-dou.json        │
│                            ainda não existir                          │
│  05:10  varredura.yml  → roda só se dados/AAAA-MM-DD.json            │
│                            ainda não existir                          │
└──────────────────────────────────────────────────────────────────────┘
```

Se o notebook rodou, o plano B não faz nada além do que já faz hoje (regenerar
o painel em `push`). Se não rodou, o GitHub Actions cobre a lacuna pelo IP
dele mesmo — menos confiável contra o CGIBS, mas evita buraco total no
painel.

## O que muda em cada arquivo

**`.github/workflows/varredura.yml` e `dou.yml`:**
- Cron shift: `1-5` (dia útil) → `*` (todo dia)
- Horário +3h em relação ao atual (dá a janela de segurança para o notebook)
- Lógica "só roda se o arquivo do dia não existe" já existe — só muda o
  horário e os dias, não a lógica em si

**`.github/workflows/medicao-inlabs.yml`:** não muda — é medição avulsa,
autorretirável, fora do ciclo diário.

**Novo: unidades systemd** (`reforma-dou.{service,timer}`,
`reforma-varredura.{service,timer}`, `reforma-analise.{service,timer}`) —
cada uma roda seu script, depois `gerar_painel.py`, depois commit/push, com
`EnvironmentFile=` apontando para o `.env` local nos serviços que precisam de
credencial.

**Novo: `.env`** na raiz do projeto (fora do git) com `INLABS_EMAIL` e
`INLABS_SENHA`.

**`.gitignore`:** adicionar `.env`.

**Novo: script de análise não-interativa** — um wrapper (ex.:
`scripts/rodar_analise_diaria.sh`) que invoca o CLI `claude` em modo
não-interativo com o critério de `scripts/analise_brief.md` e a lacuna de
`scripts/lacuna_analise.py`, seguindo o fluxo dos 5 passos já documentados no
README (sem novidade → só status; com novidade → `analises/AAAA-MM-DD.md` +
status + commit + push; nunca termina em silêncio). O desenho detalhado deste
script (prompt exato, tratamento de falha do próprio `claude` CLI) fica para
o plano de implementação, não este documento.

**Git local:** `git config user.name`/`user.email` no notebook, usando o
e-mail privado do GitHub.

**Ambiente:** `python3 -m venv .venv`, `pip install -r requirements.txt`,
`playwright install --with-deps chromium` (dependências de sistema via apt,
precisa sudo uma vez).

## O que não muda

- `scripts/varredura.py`, `scripts/dou.py`, `scripts/dou_diario.py`,
  `scripts/portais/*`, `scripts/gerar_painel.py`, `scripts/lacuna_analise.py`
  — nenhum precisa de alteração de lógica.
- A separação de arquivos por coletor (`dados/AAAA-MM-DD.json` vs
  `dados/AAAA-MM-DD-dou.json`) e a dedup por hash em `dados/historico.json`.
- A distinção `fontes_com_erro` vs `fontes_sem_itens` em `varredura.py` —
  zero itens publicados num portal não é erro, e a migração não introduz
  lógica nova aqui, só preserva a existente.

## Observabilidade

- Logs de cada execução via `journalctl -u reforma-varredura`,
  `journalctl -u reforma-dou`, `journalctl -u reforma-analise`.
- O painel já mostra a idade da última análise/coleta e destaca em vermelho
  quando passa de um dia sem atualização (`dados/analise_status.json` →
  `scripts/painel_template.html`) — funciona como alerta visual mesmo sem
  notificação ativa nova.
- Nenhum mecanismo novo de alerta (e-mail, push) está no escopo deste
  documento.
