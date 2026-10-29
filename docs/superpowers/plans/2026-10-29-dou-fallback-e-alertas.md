# DOU sem INLABS + alerta de consulta com falha — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** (1) o DOU continua sendo coletado quando o INLABS está fora (manutenção desde 21/10/2026), lendo a "Leitura do Jornal" do in.gov.br, com texto integral; (2) os dias 21/10–29/10/2026 são recuperados; (3) o push do ntfy de cada ciclo informa toda consulta (fonte) que falhou ou que só funcionou pelo plano B.

**Diagnóstico (29/10/2026, controlador):**
- Desde o ciclo das 17h de 21/10, todo ciclo registra `DOU (INLABS) metodo=PULADO` com `RuntimeError: login do INLABS falhou apos 30 tentativas: HTTP 404…` (desiste na 1ª tentativa — 4xx encerra o laço, mas a mensagem diz "30 tentativas" e "o servidor caiu", ambos falsos). Em 26/10 de manhã houve também falhas de rede (DNS/TLS) por 1 h.
- `https://inlabs.in.gov.br/` responde 200 com a página "Estamos em manutenção … Os dados abertos disponibilizados no INLabs estão temporariamente disponíveis no link … Base de Dados de Publicações do DOU"; `logar.php` responde 404.
- O ciclo termina "ok" e o push não diz nada: `dou_diario.py` sai 0 mesmo sem coletar, e `notificar.py` não lê o status das fontes.
- Alternativa verificada: `GET https://www.in.gov.br/leiturajornal?data=DD-MM-AAAA&secao=<s>` devolve HTML com `<script id="params" type="application/json">{"jsonArray":[…]}`; cada item tem `pubName, urlTitle, title, titulo, subTitulo, content (prévia ≤403 chars), artType, hierarchyStr, hierarchyList, numberPage, pubDate (DD/MM/AAAA), editionNumber, pubOrder`. Seções: DO1→`do1` (≈300/dia), DO3→`do3` (≈2.200/dia, quase tudo extrato/aviso), DO1E→`do1e` (pubName `DO1_EXTRA_A`/`DO1_EXTRA_B`), DO3E→`do3e`. Texto integral em `https://www.in.gov.br/web/dou/-/<urlTitle>`, dentro de `<div class="texto-dou">`.

## Global Constraints
- Stdlib apenas (sem pip novo). Português nos comentários (sem acento obrigatório). Testes `unittest`, sem rede (fixtures embutidas); suíte com `/home/rodrigo/projects/reforma-tributaria-monitor/.venv/bin/python3 -m unittest discover -s tests`.
- O formato dos itens do DOU não muda (mesmas chaves que `dou.coleta()` produz hoje: `titulo, url, data, fonte ("DOU DO1" etc.), orgao, ementa, texto_integral, balde, continuacao, alerta, pasta_arquivo`). Classificação continua sendo `dou.classifica()` — sem regra nova de relevância.
- Uma falha do plano B nunca derruba o ciclo; nada falha em silêncio (stderr + registro no `dados/<dia>-dou.json`).
- Educação com o servidor: no máximo 4 downloads simultâneos de matérias, timeout 30 s, 2 tentativas por matéria.

## Review Focus
1. Matéria que o INLABS já coletou (pdfPage URL) e que o plano B coleta de novo com outra URL → duplicata no histórico. Esperado: deduplicação por (data, título normalizado) contra o histórico.
2. Página de matéria sem `texto-dou` / 404 / bloqueio → item classificado só pela prévia, registrado em `diag["erros"]`, sem exceção.
3. DO3 com 2.000+ itens → não pode virar 2.000 downloads por ciclo.
4. Ciclo em que o INLABS volta → usa o INLABS, não o plano B.
5. Push com várias fontes falhando → mensagem legível e dentro do limite de tamanho do ntfy.

---

### Task 1: Plano B do DOU (Leitura do Jornal) + detecção de manutenção do INLABS

**Files:** Create `scripts/dou_site.py`, `tests/test_dou_site.py`; Modify `scripts/dou.py` (abre_sessao), `scripts/varredura.py` (`coleta_dou`), `tests/test_dou.py`.

**Interfaces produced:**
- `dou.InlabsIndisponivel(RuntimeError)`; `dou.abre_sessao(...)`: antes de tentar o login, se a página inicial contém "manutenção programada"/"Estamos em manutenção" (normalizado, sem acento), levanta `InlabsIndisponivel("INLABS em manutencao programada")` na hora (sem 30 tentativas). Mensagem de erro 4xx corrigida: "HTTP {code} no login do INLABS (endereco de login indisponivel)" e o `RuntimeError` final diz quantas tentativas foram feitas de fato.
- `dou_site.lista(dia_iso, secao) -> list[dict]` (itens do jsonArray; `secao` em {"DO1","DO3","DO1E","DO3E"} mapeada para do1/do3/do1e/do3e).
- `dou_site.texto(url_title) -> str | None` (texto de `<div class="texto-dou">`, limpo, None se ausente/erro).
- `dou_site.coleta(dias, historico=None, log=sys.stderr) -> (itens, diag)` — mesmo contrato de `dou.coleta`. Para cada matéria monta o dict `a` que `dou.classifica` espera: `_titulo` = title (ou titulo), `_ementa` = content, `artType`, `artCategory` = hierarchyStr, `_texto_integral` = texto da página quando baixado. Estratégia de download (regra do controlador):
  - estágio 1 sem download: `classifica` com `_texto_integral=""`; `descartado` por SEM_NORMA/ROTINA no título/cabeça → fora.
  - DO1/DO1E: baixa o texto de todo item que não foi descartado no estágio 1 e reclassifica com o corpo.
  - DO3/DO3E: baixa só se `ORGAOS` casa `hierarchyStr` ou `TERMOS`/`REFS` casam título+prévia; os demais ficam descartados.
  - `fonte` = `f"DOU {secao}"`; `url` = `https://www.in.gov.br/web/dou/-/<urlTitle>`; `data` = dia ISO; `orgao` = hierarchyStr[:140]; `ementa` = content[:300]; `texto_integral` = texto baixado (ou content se o download falhou); `continuacao` False.
  - Deduplicação: se `historico` for passado, pula item cujo (data, título normalizado — minúsculo, sem acento, espaços colapsados) já existe no histórico para uma fonte que começa com "DOU". Contar em `diag["duplicados"]`.
  - `diag` = `{"lidas", "forte", "revisar", "baixados", "falhas_download", "duplicados", "sem_edicao": [], "erros": []}`.
- `varredura.coleta_dou(hoje, dias=None)`: tenta INLABS como hoje; se `dou.coleta` levantar qualquer exceção (incl. `InlabsIndisponivel`), registra o motivo e chama `dou_site.coleta(dias, historico)`. Registro resultante: `metodo="leiturajornal"`, `erro=None` se o plano B coletou, e um campo novo `aviso` = "INLABS indisponivel (<motivo>); coletado pela Leitura do Jornal (in.gov.br)". Se ambos falharem: `metodo=None`, `erro` com os dois motivos. Parâmetro `dias` opcional (lista ISO) para o backfill; padrão continua [D-1, D].
- `scripts/dou_diario.py`: aceita `--dias AAAA-MM-DD [AAAA-MM-DD ...]` (backfill) e repassa a `coleta_dou`.

**Tests (TDD, sem rede — monkeypatch das funções de HTTP):** HTML de leiturajornal com params JSON (inclua um item com "Lei Complementar nº 214" no title → forte; um extrato → descartado sem download; um DO3 de órgão irrelevante → não baixado); página de matéria com `texto-dou`; página sem `texto-dou` → usa prévia e conta falha; dedup contra histórico com título em caixa/acentos diferentes; `abre_sessao` com página de manutenção → `InlabsIndisponivel` sem sleep; 404 no login → mensagem nova e "1 tentativa"; `coleta_dou` com INLABS falhando → `metodo="leiturajornal"` + `aviso`; ambos falhando → `metodo=None`.

**Smoke (rede real, sem gravar em dados/):** `dou_site.coleta(["2026-10-22"])` → imprimir lidas/baixados/forte/revisar/duplicados e 5 títulos relevantes; tempo total.

### Task 2: Push do ntfy informa consultas com falha

**Files:** Modify `scripts/notificar.py`, `tests/test_notificar.py`.

**Interfaces:**
- `notificar.falhas_do_ciclo(raiz: Path, data: str) -> list[str]`: lê `dados/<data>.json` (portais) e `dados/<data>-dou.json` (DOU); para cada fonte com `metodo` vazio → `"<fonte>: <erro resumido ≤120 chars>"`; fonte com `aviso` → `"<fonte>: <aviso>"`; fontes "nao tentada: orcamento…" entram como `"<fonte>: nao consultada (tempo esgotado)"`. Arquivo ausente → `"<grupo>: sem registro da coleta de <data>"`.
- No push normal do ciclo (`main` sem `--falha`), se a lista não for vazia: o corpo ganha uma seção final "⚠ Consultas com falha:" com uma linha por item (corta para caber em `LIMITE_CORPO`), a prioridade sobe para `"high"` e entra a tag `"warning"`. Sem falhas, a mensagem não muda (teste de regressão).
- A data é a do status da análise (`status["data"]`).

**Tests:** sem falhas → mensagem idêntica à atual; DOU com `metodo=None` → linha do DOU + prioridade high; DOU com `aviso` (plano B) → linha de aviso; portal "nao tentada" → linha correspondente; arquivo do DOU ausente → linha "sem registro"; corpo longo continua ≤ limite.

### Rollout + recuperação (controlador)
1. Merge, suíte, push. 2. Backfill: `dou_diario.py --dias 2026-10-21 … 2026-10-29` (dedup contra o histórico cobre a sobreposição com a coleta de 21/10 05h); conferir contagens por dia; leitura/painel; publicar. 3. Rodar um ciclo manual (`systemctl start reforma-ciclo.service`) para a análise processar os itens recuperados e conferir o push com o aviso do plano B.
