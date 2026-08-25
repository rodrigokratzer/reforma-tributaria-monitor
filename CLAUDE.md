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

Run tests (the only test suite in the repo, stdlib `unittest`, no fixtures on disk):
```bash
python3 -m unittest tests/test_lacuna_analise.py -v
```

Run a single test:
```bash
python3 -m unittest tests.test_lacuna_analise.TestLacuna.test_lacuna_de_varios_dias_pulados -v
```

Run the pieces manually (each is a standalone script, no CLI framework):
```bash
python3 scripts/varredura.py       # scrapes the 12 web sources; needs playwright
python3 scripts/dou_diario.py      # scrapes the DOU; needs INLABS_EMAIL/INLABS_SENHA env vars, stdlib only
python3 scripts/gerar_painel.py    # rebuilds docs/index.html from dados/ + analises/ + estado.json
python3 scripts/lacuna_analise.py [data AAAA-MM-DD]   # prints the analysis coverage gap as JSON
python3 scripts/medir_inlabs.py [inicio] [fim]        # measures the DOU filter's recall; needs INLABS creds
```

No linter or formatter is configured.

## Architecture

**Two deliberately separate layers**, connected only through git:

- **Fatos** (facts) — `scripts/varredura.py` (12 web sources) and `scripts/dou_diario.py`
  (DOU/INLABS) run on their own GitHub Actions schedules, write JSON, and never
  interpret anything. No AI, no judgment calls.
- **Análise** (analysis) — a Claude agent, scheduled externally to this repo (Claude
  Code `/schedule`, not a GitHub Actions workflow, to avoid per-token API cost), reads
  `scripts/analise_brief.md` and writes `analises/AAAA-MM-DD.md`.

### Data flow

1. `scripts/varredura.py` (web sources, 06:40 BRT weekdays) and `scripts/dou_diario.py`
   (DOU, 02:00 BRT weekdays) both call the shared `grava_resultado()` in
   `scripts/varredura.py` to write their results.
2. **The two collectors never write the same file.** Web writes
   `dados/AAAA-MM-DD.json` + `dados/novidades.json`; DOU writes
   `dados/AAAA-MM-DD-dou.json` + `dados/novidades_dou.json`. This is deliberate —
   merge-on-write between two independently-scheduled workflows is a race condition
   waiting to happen (see "Gotchas" below).
3. The one file both collectors *do* share is `dados/historico.json` — safe by
   construction, because its dedup key (`chave()` in `scripts/varredura.py`) is a
   content hash (URL + title), not tied to which collector found the item first.
4. `scripts/lacuna_analise.py` reads only `analises/*.md` (by filename date) and
   `dados/historico.json` — it never touches the per-day snapshot files, so it's
   agnostic to which collector found what.
5. `scripts/gerar_painel.py` reads `estado.json`, both pairs of per-day/novidades
   files, `dados/historico.json`, `dados/analise_status.json`, and `analises/*.md`,
   embeds one JSON payload into `scripts/painel_template.html`, and writes
   `docs/index.html` (published via GitHub Pages, `/docs` on `main`).
6. `docs/index.html`, everything under `dados/`, and `dados/analise_status.json` are
   **generated** — never hand-edit them. `estado.json` and `scripts/analise_brief.md`
   are the two files meant for manual editing; `analises/*.md` is normally written by
   the scheduled agent but accepts manual edits too.

### GitHub Actions workflows

- `.github/workflows/varredura.yml` — scrapes the 12 web sources on a cron
  (weekdays), regenerates the panel, commits. Also fires on `push` to
  `estado.json`, `analises/**`, `dados/analise_status.json`, `dados/*-dou.json`,
  `dados/novidades_dou.json`, or `scripts/**` — but the scrape step is skipped on
  `push` (`if: github.event_name != 'push'`) so it only regenerates the panel, it
  never re-scrapes.
- `.github/workflows/dou.yml` — scrapes the DOU on its own cron (02:00 BRT), with
  its own 60-minute budget, decoupled from the web scrape's timing and time budget.
- `.github/workflows/medicao-inlabs.yml` — one-off recall measurement against the
  full DOU corpus. Self-retires: skips its body once `dados/medicao_inlabs.json`
  already exists.

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
- **INLABS login can respond "200 with no session cookie" as often as it responds
  5xx**, and that's usually scheduled maintenance, not a bad credential — `dou.py`'s
  `abre_sessao()` retries both cases (30 attempts, backoff capped at 120s); only a
  genuine 4xx gives up immediately.
- **Never merge two collectors' output into one file by reading-modifying-writing
  it.** Give each its own file instead (see Data flow above) — it removes the race
  condition entirely rather than making it rarer.
