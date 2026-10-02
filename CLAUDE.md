# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily monitor for the Brazilian consumption tax reform (EC 132/2023, LC 214/2025,
LC 227/2026). It scrapes official sources, publishes a public dashboard via GitHub
Pages, and has a scheduled Claude agent write a daily analysis. See `README.md`
for the full picture — this file focuses on what's needed to work in the code.

## Commands

Dependencies (Playwright + markdown; PEP 668 "externally-managed" environments may
need a venv first: `python3 -m venv .venv && .venv/bin/pip install ...`):
```bash
pip install -r requirements.txt
playwright install --with-deps chromium   # only needed for scripts/varredura.py
```

Run the tests (stdlib `unittest`, no fixtures on disk — three files:
`test_lacuna_analise.py`, `test_portais_base.py`, `test_portal_cgibs.py`):
```bash
python3 -m unittest discover -s tests -v
```

Run one file, or a single test:
```bash
python3 -m unittest tests.test_portais_base -v
python3 -m unittest tests.test_lacuna_analise.TestLacuna.test_lacuna_de_varios_dias_pulados -v
```

Run the pieces manually (each is a standalone script, no CLI framework):
```bash
python3 scripts/varredura.py       # scrapes the 16 web sources; needs playwright
python3 scripts/dou_diario.py      # scrapes the DOU; needs INLABS_EMAIL/INLABS_SENHA env vars, stdlib only
python3 scripts/gerar_painel.py    # rebuilds docs/index.html from dados/ + analises/ + estado.json
python3 scripts/ler_textos.py [--sem-limite] [--chave K]   # reading lane: full text into dados/textos/; needs pdftotext + tesseract (por)
python3 scripts/cobertura_textos.py   # reports how many history items have full text, per source
python3 scripts/reler_dou.py          # backfills full text of old DOU items from INLABS; needs INLABS creds
python3 scripts/semear_analisados.py --fonte F [--aplicar]   # marks a new source's backlog as analyzed (dry run without --aplicar)
python3 scripts/lacuna_analise.py [data AAAA-MM-DD]   # prints the analysis coverage gap as JSON
python3 scripts/medir_inlabs.py [inicio] [fim]        # measures the DOU filter's recall; needs INLABS creds
```

No linter or formatter is configured.

## Architecture

**Three deliberately separate layers**, connected only through git:

- **Fatos** (facts) — `scripts/varredura.py` (16 web sources, via the
  `scripts/portais/` package) and `scripts/dou_diario.py` (DOU/INLABS) run on
  their own GitHub Actions schedules, write JSON, and never interpret anything.
  No AI, no judgment calls.
- **Leitura** (reading) — `scripts/ler_textos.py` runs right after the web scrape,
  only on the local machine (poppler + tesseract from the system packages). For every
  history item without full text it downloads the page (HTML body by domain rule) and
  its PDF attachments (`pdftotext`, OCR on pages without a text layer), and writes only
  `dados/textos/<chave>.txt` + `dados/leituras.json` (status `lido`, `parcial`,
  `falhou`, `desistiu`; `origem` `coleta`, `coleta_cortada`, `inlabs`, `html`, `pdf`,
  `pdf+ocr`, `html+ocr`). Code lives in `scripts/leitura/` (`paginas`, `pdf`, `baixar`).
  DOU items are not downloaded here: their text comes from INLABS at collection time.
- **Análise** (analysis) — `claude -p` run by `scripts/rodar_analise.sh` on the
  local machine (subscription, no per-token API cost), twice a day: turno `matinal`
  (05:00) and `noturna` (17:00). It reads `scripts/analise_brief.md` and writes only
  files — `analises/AAAA-MM-DD-<turno>.md`, `dados/analise_status.json`,
  `dados/triagem_pendente.json`; it never runs git. `scripts/fechar_analise.py`
  validates them and only then marks items as analyzed (`dados/analisados.json`)
  and merges the per-item verdicts into `dados/triagem.json`. When a publication
  changes a deadline, pending item or milestone, the analysis also writes
  `dados/estado_proposta.json` (the full `estado.json` + declared `mudancas`);
  `scripts/atualizar_estado.py` (called by `fechar_analise.py`) validates schema,
  dates, status values and that nothing disappears undeclared, then applies it and
  logs to `dados/estado_mudancas.json`. An invalid proposal is dropped; the panel
  keeps the previous state.

### Data flow

1. `scripts/rodar_ciclo.sh` (systemd `reforma-ciclo.timer`, 05:00 and 17:00 BRT)
   runs `scripts/dou_diario.py` (DOU), then `scripts/varredura.py` (web sources),
   (`rodar_varredura.sh` runs `scripts/ler_textos.py` right after it; a reading failure
   does not block publishing the scrape), then the analysis, then `scripts/notificar.py` (ntfy push + optional SMTP email).
   Both collectors call the shared `grava_resultado()` in `scripts/varredura.py`,
   which stamps new history items with `visto_em` (UTC).
2. **The two collectors never write the same file.** Web writes
   `dados/AAAA-MM-DD.json` + `dados/novidades.json`; DOU writes
   `dados/AAAA-MM-DD-dou.json` + `dados/novidades_dou.json`. This is deliberate —
   merge-on-write between two independently-scheduled workflows is a race condition
   waiting to happen (see "Gotchas" below).
3. The one file both collectors *do* share is `dados/historico.json` — safe by
   construction, because its dedup key (`chave()` in `scripts/portais/base.py`,
   imported by `varredura.py`) is a content hash (URL + title), not tied to which
   collector found the item first.
4. `scripts/lacuna_analise.py` returns every `dados/historico.json` item whose key is
   not in `dados/analisados.json` — by item key, not by date, because two cycles run
   on the same day. An item whose full text is still being read is held back
   (`aguardando_leitura` in the lacuna) for up to 3 days, then goes to the analysis with
   whatever text exists. Analysis file stems: `AAAA-MM-DD` (legacy, turno `unica`),
   `AAAA-MM-DD-matinal`, `AAAA-MM-DD-noturna`.
5. `scripts/gerar_painel.py` reads `estado.json`, both pairs of per-day/novidades
   files, `dados/historico.json`, `dados/triagem.json`, `dados/analise_status.json`,
   and `analises/*.md`, embeds one JSON payload (all analyses + last 3 days of
   publications) into `scripts/painel_template.html`, and writes `docs/index.html`
   plus `docs/historico.json` (full history, fetched by the panel's period filter;
   both published via GitHub Pages, `/docs` on `main`).
6. `docs/index.html`, everything under `dados/`, and `dados/analise_status.json` are
   **generated** — never hand-edit them. `scripts/analise_brief.md` is meant for manual
   editing; `estado.json` accepts manual edits but is normally updated by the
   analysis through `scripts/atualizar_estado.py`; `analises/*.md` is normally written by
   the scheduled agent but accepts manual edits too.

### Os scrapers web (`scripts/portais/`)

Cada fonte web é um objeto `Portal` (`scripts/portais/base.py`). A classe base
tem toda a mecânica de coleta (2 tentativas via navegador, fallback HTTP puro,
filtro por um regex global) e dois pontos de extensão: `filtro_relevancia()` e
`extrai_texto()`. `scripts/portais/registro.py` lista as 16 instâncias
(`PORTAIS`), na ordem que importa para o orçamento de tempo. As subclasses são
`GovBrNoticiasPortal` (`govbr.py`), `SVRSNoticiasPortal` (`svrs.py`),
`NFeInformesPortal` e `NFeListaPortal` (`nfe.py`); cada uma só sabe achar as
publicações da sua página. Nenhuma extrai texto: ler o conteúdo é da raia de
leitura. As fontes SVRS e NF-e filtram com o regex específico `REFORMA`
(`scripts/portais/base.py`), não com o global `RELEVANTE`, que casa toda "nota
técnica"/"NF-e"/"DF-e". Adicionar um portal sem regra própria é uma linha em
`registro.py`; com regra própria, uma subclasse pequena + a linha.

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

## Gotchas (each cost a real bug — see README's "Decisões de projeto" for the full stories)

- **Relevance filtering must match against the item's title/URL path, never against
  the domain or sender.** `cgibs.gov.br` contains "cgibs"; matching the whole URL or
  the órgão name turns everything from that source into a false positive.
- **"New" means never-seen-link, not "recent date."** Official sources publish with
  wrong/backdated dates; the scraper compares against links already seen, not dates.
- **`git pull --rebase --autostash -q` in the automated commit steps must never
  hardcode a branch name.** It broke when a workflow ran on a PR branch instead of
  `main` — rebasing a multi-commit branch onto `main` produced spurious `add/add`
  conflicts from the shallow `actions/checkout`. Let it use whatever the checkout
  already tracks.
- **Fonte cuja publicação não é link** (SVRS, informes do NF-e): o coletor genérico de
  links pega o menu e ninguém percebe, porque a fonte "tem itens". Confira se os itens
  são publicações, não só se a contagem é maior que zero.
- **INLABS login can respond "200 with no session cookie" as often as it responds
  5xx**, and that's usually scheduled maintenance, not a bad credential — `dou.py`'s
  `abre_sessao()` retries both cases (30 attempts, backoff capped at 120s); only a
  genuine 4xx gives up immediately.
- **Never merge two collectors' output into one file by reading-modifying-writing
  it.** Give each its own file instead (see Data flow above) — it removes the race
  condition entirely rather than making it rarer.
- **`docs/` is generated, so a rebase conflict there is not a real conflict.** All
  three lanes commit/push through `scripts/publicar.sh`, which resolves conflicts
  limited to `docs/` by re-running `gerar_painel.py` and aborts on any other
  conflict. The GitHub Actions `push` trigger was cut down to `estado.json` only:
  regenerating the panel there raced the local cycle and took down the first new
  cycle on 30/09/2026.
