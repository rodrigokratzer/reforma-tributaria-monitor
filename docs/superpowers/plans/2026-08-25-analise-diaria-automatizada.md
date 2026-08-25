# Análise Diária Automatizada — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar a lacuna entre a camada de fatos (varredura automática existente) e a camada de análise (hoje escrita manualmente), automatizando a produção diária de `analises/AAAA-MM-DD.md` e tornando o status da rotina sempre visível no painel, sem custo de API por token.

**Architecture:** Um script determinístico (`scripts/lacuna_analise.py`) identifica o que falta analisar comparando `analises/*.md` já publicadas com `dados/historico.json`. Um agente agendado na nuvem do Claude Code lê essa lacuna, aplica os critérios de `scripts/analise_brief.md` para escrever a análise em prosa, grava um status de execução sempre atualizado (`dados/analise_status.json`), comita e empurra. O painel (`scripts/gerar_painel.py` + `scripts/painel_template.html`) passa a exibir esse status numa faixa fixa, além da análise em si.

**Tech Stack:** Python 3.12 stdlib (sem novas dependências pip), `unittest` para testes, skill `/schedule` do Claude Code para o agendamento na nuvem, push notification nativa do Claude Code.

**Spec:** [docs/superpowers/specs/2026-08-25-analise-diaria-automatizada-design.md](../specs/2026-08-25-analise-diaria-automatizada-design.md)

## Global Constraints

- Sem custo de API por token: a rotina diária roda como agente agendado na nuvem (skill `/schedule`), nunca como chamada direta à API da Anthropic faturada por uso.
- Nenhuma dependência pip nova além de `playwright==1.56.0` e `markdown==3.7` já em `requirements.txt` — `lacuna_analise.py` e seus testes usam só biblioteca padrão.
- Todo texto voltado ao usuário (commits, análises, mensagens de push, status) em português.
- Falha nunca é silenciosa: todo caminho de erro grava `dados/analise_status.json` e/ou envia push notification.
- O painel precisa continuar de pé sozinho mesmo sem `dados/analise_status.json` existir — compatibilidade com o estado atual do projeto.
- Antes de qualquer `git push` feito pela automação, rodar `git pull --rebase --autostash` primeiro (mesmo padrão já usado em `varredura.yml`).
- Horários de referência: rotina roda ~07:15 Brasília (~10:15 UTC), dias úteis; janela de retentativa até ~08:00 Brasília (~11:00 UTC).

---

### Task 1: `scripts/lacuna_analise.py` — determina a lacuna de cobertura

**Files:**
- Create: `scripts/lacuna_analise.py`
- Test: `tests/test_lacuna_analise.py`

**Interfaces:**
- Consumes: `analises/*.md` (nomes `AAAA-MM-DD.md`), `dados/*.json` (nomes `AAAA-MM-DD.json`), `dados/historico.json` (dict de `{chave: {"primeira_vez": str, "fonte": str, "titulo": str, "url": str, "data": str|None, "pasta_arquivo": str|None, "alerta": str|None}}`).
- Produces: função `lacuna(raiz: Path, hoje: str|None) -> dict` com chaves `desde` (str|None), `ate` (str), `dados_de_hoje_disponiveis` (bool), `dias_com_dados_na_janela` (list[str]), `itens` (list[dict], mesmo formato do historico, ordenado por `primeira_vez` depois `fonte`). CLI: `python3 scripts/lacuna_analise.py [hoje]` imprime esse dict como JSON no stdout — é o que o agente agendado (Task 6) consome.

- [ ] **Step 1: Escrever o arquivo de teste completo**

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lacuna_analise as la


def escreve(raiz, rel, conteudo):
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(conteudo, (dict, list)):
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), "utf-8")
    else:
        caminho.write_text(conteudo, "utf-8")


class TestDataUltimaAnalise(unittest.TestCase):
    def test_sem_analises_devolve_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "analises").mkdir()
            self.assertIsNone(la.data_ultima_analise(raiz))

    def test_pasta_inexistente_devolve_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self.assertIsNone(la.data_ultima_analise(raiz))

    def test_pega_a_mais_recente(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-17.md", "x")
            escreve(raiz, "analises/2026-08-20.md", "x")
            escreve(raiz, "analises/2026-08-05.md", "x")
            self.assertEqual(la.data_ultima_analise(raiz), "2026-08-20")

    def test_ignora_arquivo_sem_nome_de_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-17.md", "x")
            escreve(raiz, "analises/README.md", "x")
            self.assertEqual(la.data_ultima_analise(raiz), "2026-08-17")


class TestDadosDisponiveis(unittest.TestCase):
    def test_lista_apenas_arquivos_com_nome_de_data_ordenados(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "dados/2026-08-20.json", {})
            escreve(raiz, "dados/2026-08-18.json", {})
            escreve(raiz, "dados/historico.json", {})
            escreve(raiz, "dados/novidades.json", {})
            self.assertEqual(la.dados_disponiveis(raiz),
                              ["2026-08-18", "2026-08-20"])

    def test_pasta_inexistente_devolve_lista_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self.assertEqual(la.dados_disponiveis(raiz), [])


class TestItensDaLacuna(unittest.TestCase):
    def _historico(self, raiz):
        escreve(raiz, "dados/historico.json", {
            "a": {"primeira_vez": "2026-08-18", "fonte": "Z", "titulo": "item 18",
                  "url": "https://x/18", "data": None, "pasta_arquivo": None, "alerta": None},
            "b": {"primeira_vez": "2026-08-19", "fonte": "A", "titulo": "item 19",
                  "url": "https://x/19", "data": None, "pasta_arquivo": None, "alerta": None},
            "c": {"primeira_vez": "2026-08-20", "fonte": "M", "titulo": "item 20",
                  "url": "https://x/20", "data": None, "pasta_arquivo": None, "alerta": None},
            "d": {"primeira_vez": "2026-08-17", "fonte": "M", "titulo": "item 17 (antigo)",
                  "url": "https://x/17", "data": None, "pasta_arquivo": None, "alerta": None},
        })

    def test_filtra_janela_desde_exclusivo_ate_inclusivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._historico(raiz)
            itens = la.itens_da_lacuna(raiz, desde="2026-08-17", ate="2026-08-19")
            titulos = [i["titulo"] for i in itens]
            self.assertEqual(titulos, ["item 18", "item 19"])

    def test_sem_desde_pega_tudo_ate_a_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._historico(raiz)
            itens = la.itens_da_lacuna(raiz, desde=None, ate="2026-08-19")
            titulos = [i["titulo"] for i in itens]
            self.assertEqual(titulos, ["item 17 (antigo)", "item 18", "item 19"])

    def test_sem_historico_devolve_lista_vazia(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "dados").mkdir()
            self.assertEqual(la.itens_da_lacuna(raiz, desde=None, ate="2026-08-19"), [])


class TestLacuna(unittest.TestCase):
    def test_dados_de_hoje_ausentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-20.md", "x")
            escreve(raiz, "dados/2026-08-21.json", {})
            escreve(raiz, "dados/historico.json", {})
            resultado = la.lacuna(raiz, hoje="2026-08-25")
            self.assertFalse(resultado["dados_de_hoje_disponiveis"])
            self.assertEqual(resultado["desde"], "2026-08-20")

    def test_lacuna_de_varios_dias_pulados(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            escreve(raiz, "analises/2026-08-20.md", "x")
            for dia in ("2026-08-21", "2026-08-24", "2026-08-25"):
                escreve(raiz, f"dados/{dia}.json", {})
            escreve(raiz, "dados/historico.json", {
                "a": {"primeira_vez": "2026-08-21", "fonte": "Z", "titulo": "t21",
                      "url": "u", "data": None, "pasta_arquivo": None, "alerta": None},
                "b": {"primeira_vez": "2026-08-25", "fonte": "Z", "titulo": "t25",
                      "url": "u", "data": None, "pasta_arquivo": None, "alerta": None},
            })
            resultado = la.lacuna(raiz, hoje="2026-08-25")
            self.assertTrue(resultado["dados_de_hoje_disponiveis"])
            self.assertEqual(resultado["dias_com_dados_na_janela"],
                              ["2026-08-21", "2026-08-24", "2026-08-25"])
            self.assertEqual([i["titulo"] for i in resultado["itens"]], ["t21", "t25"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python3 -m unittest tests/test_lacuna_analise.py -v`
Expected: `ModuleNotFoundError: No module named 'lacuna_analise'`

- [ ] **Step 3: Escrever a implementação**

```python
#!/usr/bin/env python3
"""
Determina a lacuna de cobertura da analise diaria: quais dias desde a
ultima analises/AAAA-MM-DD.md ja publicada ainda nao tem analise, e quais
itens de dados/historico.json caem nessa janela.

Uso: python scripts/lacuna_analise.py [hoje AAAA-MM-DD]
Saida: JSON no stdout.
"""
import json, re, sys, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def data_ultima_analise(raiz):
    analises = raiz / "analises"
    if not analises.exists():
        return None
    datas = sorted(p.stem for p in analises.glob("*.md") if DATA_RX.match(p.stem))
    return datas[-1] if datas else None


def dados_disponiveis(raiz):
    dados = raiz / "dados"
    if not dados.exists():
        return []
    return sorted(p.stem for p in dados.glob("*.json") if DATA_RX.match(p.stem))


def itens_da_lacuna(raiz, desde, ate):
    caminho = raiz / "dados" / "historico.json"
    if not caminho.exists():
        return []
    historico = json.loads(caminho.read_text("utf-8"))
    itens = [v for v in historico.values()
             if v.get("primeira_vez") and
             (desde is None or v["primeira_vez"] > desde) and
             v["primeira_vez"] <= ate]
    itens.sort(key=lambda i: (i["primeira_vez"], i.get("fonte", "")))
    return itens


def lacuna(raiz, hoje=None):
    hoje = hoje or datetime.date.today().isoformat()
    desde = data_ultima_analise(raiz)
    disponiveis = dados_disponiveis(raiz)
    return {
        "desde": desde,
        "ate": hoje,
        "dados_de_hoje_disponiveis": hoje in disponiveis,
        "dias_com_dados_na_janela": [d for d in disponiveis
                                      if (desde is None or d > desde) and d <= hoje],
        "itens": itens_da_lacuna(raiz, desde, hoje),
    }


def main():
    hoje = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(lacuna(RAIZ, hoje), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `python3 -m unittest tests/test_lacuna_analise.py -v`
Expected: todos os testes `ok`, `OK` no resumo final.

- [ ] **Step 5: Rodar contra os dados reais do repositório para conferir a saída**

Run: `python3 scripts/lacuna_analise.py`
Expected: JSON válido, `desde` igual a `2026-08-20` (última análise publicada hoje), `itens` contendo as novidades de 21, 24 e 25/08 acumuladas em `dados/historico.json`.

- [ ] **Step 6: Commit**

```bash
git add scripts/lacuna_analise.py tests/test_lacuna_analise.py
git commit -m "feat: script de lacuna de cobertura para a análise diária"
```

---

### Task 2: `scripts/analise_brief.md` — critério e formato para quem escreve a análise

**Files:**
- Create: `scripts/analise_brief.md`

**Interfaces:**
- Consumes: nada (documento autocontido).
- Produces: texto que a rotina agendada (Task 6) lê e aplica sobre a saída de `lacuna_analise.py` para decidir o que escrever em `analises/AAAA-MM-DD.md`.

- [ ] **Step 1: Escrever o brief completo**

```markdown
# Brief da análise diária

Instruções para quem (ou o que) escreve `analises/AAAA-MM-DD.md`. O objetivo é
o mesmo de toda análise manual já publicada no projeto: separar o que exige
ação do que é só contexto, e explicar o impacto em termos que um contador ou
um cliente entenda — não apenas descrever o que foi publicado.

## Estrutura

Uma análise segue, nesta ordem, só as seções que tiverem conteúdo:

1. **Título de uma linha em negrito**, resumindo o achado do período. Ex:
   `**30 itens novos entre 18 e 20/08; três importam, e um deles é urgente.**`
2. **### Ação requerida** — itens que mudam prazo, obrigação ou decisão de
   alguém. Cada item:
   - título em negrito com o achado principal, fonte e data
   - `**Antes:**` / `**Agora:**` quando houver mudança de regra
   - `**Impacto para o cliente:**` em termos práticos, não jurídicos
   - `**O que não resolve:**` quando a norma deixa algo em aberto
   - `**Fonte:**` link
3. **### Acompanhar** — relevante, mas sem ação imediata. Mesmo formato,
   mais enxuto.
4. **### Contexto** — publicações que não afetam o contribuinte (ex:
   governança interna, nomeação de diretoria). Uma ou duas frases, sem as
   subseções acima.
5. **### No radar** — prazos próximos relevantes, formato `**N dias** — DD/MM:
   descrição`.
6. **### Nota sobre a coleta** — só quando houver algo digno de registro sobre
   a qualidade da coleta do período (ex: taxa de falso positivo do filtro,
   fonte que falhou).

Sem novidade relevante no período: não escrever o arquivo. Ver tratamento em
`docs/superpowers/specs/2026-08-25-analise-diaria-automatizada-design.md`.

## Critério de relevância

- **Muda prazo, obrigação, ou decisão de um contribuinte real** → Ação
  requerida.
- **Afeta como um sistema ou processo deve ser ajustado, mesmo sem prazo
  formal** → Acompanhar.
- **Ato interno do órgão sem efeito externo** (eleição de diretoria, ata de
  reunião, ajuste de convênio) → Contexto, ou nem cite.
- **Extrato de contrato, edital de licitação, aviso de dispensa, resultado de
  julgamento administrativo sem relação com a reforma** → não cite. É ruído
  do filtro, não notícia.

## Armadilhas conhecidas (do README do projeto)

- **Data declarada pode estar errada.** Antes de tratar uma publicação como
  antiga ou fora de janela, confira contra a pasta de upload do arquivo, não
  só a data no título.
- **Nunca julgue relevância pelo remetente ou pela URL conterem o termo.**
  `cgibs.gov.br` contém "cgibs", "Comitê Gestor do IBS" contém "IBS" — isso
  não torna o conteúdo relevante. O termo tem que estar no *assunto* da
  publicação.
- **Item "forte" do filtro do DOU pode ser falso positivo** (ex: ato de
  jurisdição de tribunal). Leia a ementa antes de classificar.
- **Proposta não é norma.** Uma resolução do CGIBS que propõe um percentual
  não fixa alíquota. Estimativa divulgada na imprensa não é norma.

## Tom

Direto, sem jargão desnecessário. Frases curtas. Quando o impacto for para
"o cliente" (contador que usa o painel para aconselhar clientes), diga o que
muda na prática — não apenas cite o dispositivo legal.
```

- [ ] **Step 2: Verificar que o brief cobre os elementos exigidos**

```bash
for termo in "Ação requerida" "Acompanhar" "Contexto" "No radar" "Nota sobre a coleta" \
             "pasta de upload" "remetente ou pela URL" "falso positivo" "Proposta não é norma"; do
  grep -qF "$termo" scripts/analise_brief.md && echo "OK: $termo" || echo "FALTA: $termo"
done
```
Expected: `OK:` para todos os nove termos.

- [ ] **Step 3: Commit**

```bash
git add scripts/analise_brief.md
git commit -m "docs: brief de critério e formato para a análise diária"
```

---

### Task 3: Status diário visível no painel

**Files:**
- Modify: `scripts/gerar_painel.py:40-77`
- Modify: `scripts/painel_template.html` (CSS ~linha 99, HTML ~linha 118, JS ~linha 178)

**Interfaces:**
- Consumes: `dados/analise_status.json` (quando existir) no formato `{"data": "AAAA-MM-DD", "situacao": "publicada"|"sem_novidade"|"dados_pendentes", "gerado_em": "AAAA-MM-DDTHH:MM:SSZ", "resumo_curto": str opcional}` — produzido pela rotina agendada (Task 6).
- Produces: `payload["status_diario"]` no JSON embutido em `docs/index.html`, renderizado na faixa `#status-diario`.

- [ ] **Step 1: Modificar `gerar_painel.py` para ler e propagar o status**

Em `scripts/gerar_painel.py`, logo após a linha que lê `novid` (linha 43):

```python
    novid = ler_json(DADOS / "novidades.json", {"itens": [], "data": None})
    data_ref = novid.get("data") or datetime.date.today().isoformat()
    status_diario = ler_json(DADOS / "analise_status.json", None)
```

E dentro do dict `payload` (após `"analise_data": analise_data,`):

```python
        "analise_html": analise_html,
        "analise_data": analise_data,
        "status_diario": status_diario,
    }
```

- [ ] **Step 2: Adicionar CSS da faixa de status em `painel_template.html`**

Logo após a regra `.alerta{...}` (linha 100), adicionar:

```css
  .status-diario{border-left:3px solid var(--axis);background:var(--wash);padding:10px 14px;
    border-radius:0 8px 8px 0;font-size:13px;margin-top:16px;display:none}
  .status-diario.on{display:block}
```

- [ ] **Step 3: Adicionar o elemento da faixa no HTML**

Logo após `</header>` (linha 118), antes de `<h2>Prazos em contagem regressiva</h2>`:

```html
  <div class="status-diario" id="status-diario"></div>
```

- [ ] **Step 4: Renderizar o status no JS**

Logo após `$('gerado').textContent = 'Painel gerado em ' + (D.gerado_em || '—') + '.';` (linha 178):

```javascript
  if(D.status_diario){
    var sd = D.status_diario;
    var cor = {publicada:'var(--good)', sem_novidade:'var(--ink-3)',
      dados_pendentes:'var(--warning)'}[sd.situacao] || 'var(--axis)';
    var texto = {publicada: sd.resumo_curto || 'análise publicada',
      sem_novidade: 'sem novidades relevantes',
      dados_pendentes: 'varredura de hoje ainda não chegou'}[sd.situacao] || sd.situacao;
    var el = $('status-diario');
    el.style.borderLeftColor = cor;
    el.innerHTML = '<strong>Última checagem:</strong> ' + br(sd.data) +
      (sd.gerado_em ? ' &middot; ' + sd.gerado_em.slice(11,16) + ' UTC' : '') +
      ' — ' + esc(texto);
    el.className = 'status-diario on';
  }
```

- [ ] **Step 5: Testar com um status de exemplo**

```bash
cp dados/analise_status.json /tmp/analise_status_backup.json 2>/dev/null || true
python3 -c "
import json
json.dump({'data': '2026-08-25', 'situacao': 'sem_novidade',
           'gerado_em': '2026-08-25T10:22:00Z'},
          open('dados/analise_status.json', 'w'), ensure_ascii=False)
"
python3 scripts/gerar_painel.py
grep -q '"status_diario": {"data": "2026-08-25", "situacao": "sem_novidade"' docs/index.html \
  && echo "OK: status_diario presente no payload" || echo "FALHOU"
```
Expected: `OK: status_diario presente no payload`.

- [ ] **Step 6: Reverter o arquivo de teste e regenerar o painel real**

```bash
rm dados/analise_status.json
mv /tmp/analise_status_backup.json dados/analise_status.json 2>/dev/null || true
python3 scripts/gerar_painel.py
grep -q '"status_diario": null' docs/index.html \
  && echo "OK: painel volta a ficar de pé sem status_diario" || echo "FALHOU"
```
Expected: `OK: painel volta a ficar de pé sem status_diario` (a menos que já existisse um `analise_status.json` real de execução anterior — nesse caso o backup restaurado é o que deve aparecer).

- [ ] **Step 7: Commit**

```bash
git add scripts/gerar_painel.py scripts/painel_template.html docs/index.html
git commit -m "feat: faixa de status diário sempre visível no painel"
```

---

### Task 4: Disparar a regeneração do painel quando o status mudar

**Files:**
- Modify: `.github/workflows/varredura.yml:10-14`

**Interfaces:**
- Consumes: nada de código — só o path-filter do gatilho `push`.
- Produces: regeneração automática de `docs/index.html` quando a rotina da Task 6 empurrar `dados/analise_status.json` (ex: num dia sem novidade, onde nenhuma `analises/*.md` nova é criada).

- [ ] **Step 1: Adicionar o novo path ao gatilho**

Em `.github/workflows/varredura.yml`, o bloco `push.paths` atual é:

```yaml
  push:
    paths:
      - "estado.json"       # editou a camada curada? regenera o painel
      - "analises/**"
      - "scripts/**"
```

Alterar para:

```yaml
  push:
    paths:
      - "estado.json"       # editou a camada curada? regenera o painel
      - "analises/**"
      - "dados/analise_status.json"   # status da rotina de análise, mesmo em dia sem novidade
      - "scripts/**"
```

- [ ] **Step 2: Verificar a alteração**

```bash
grep -A5 "^  push:" .github/workflows/varredura.yml
```
Expected: a lista de `paths` mostrando as quatro entradas, incluindo `dados/analise_status.json`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/varredura.yml
git commit -m "ci: regenerar painel também quando o status da análise mudar"
```

---

### Task 5: Validação retroativa — preencher a lacuna existente

**Files:**
- Create: `analises/2026-08-21.md` ou o(s) arquivo(s) que a lacuna real indicar
- Create: `dados/analise_status.json`

**Interfaces:**
- Consumes: `python3 scripts/lacuna_analise.py` (Task 1) e `scripts/analise_brief.md` (Task 2).
- Produces: as duas análises que faltam desde `2026-08-20.md`, servindo de calibração de qualidade antes de ligar o agendamento (Task 6).

- [ ] **Step 1: Rodar a lacuna atual**

Run: `python3 scripts/lacuna_analise.py`
Expected: JSON com `"desde": "2026-08-20"` e a lista de itens novos entre 21 e 25/08 (o intervalo real depende da data em que esta task for executada).

- [ ] **Step 2: Aplicar o brief manualmente sobre os itens da lacuna**

Ler cada item de `itens` no JSON do Step 1, aplicar o critério de relevância de `scripts/analise_brief.md` (armadilhas incluídas — checar data declarada vs. pasta de upload, não classificar pelo domínio/remetente), e escrever `analises/{data-mais-recente-da-lacuna}.md` seguindo a mesma estrutura de `analises/2026-08-20.md`.

- [ ] **Step 3: Comparar qualidade com as análises manuais existentes**

Abrir lado a lado `analises/2026-08-20.md` e o arquivo novo. Confirmar: mesma separação Ação requerida / Acompanhar / Contexto / No radar; mesmo nível de "o que não resolve"; nenhuma citação de item que é só ruído de filtro (extrato de contrato, edital, etc.).

- [ ] **Step 4: Escrever o status correspondente**

```bash
python3 -c "
import json, datetime
json.dump({'data': '<data-mais-recente-da-lacuna>', 'situacao': 'publicada',
           'gerado_em': datetime.datetime.now(datetime.timezone.utc)
                         .strftime('%Y-%m-%dT%H:%M:%SZ'),
           'resumo_curto': '<preencher com a contagem real, ex: 4 novidades, 1 exige ação>'},
          open('dados/analise_status.json', 'w'), ensure_ascii=False)
"
```

- [ ] **Step 5: Regenerar o painel e conferir visualmente**

```bash
python3 scripts/gerar_painel.py
open docs/index.html   # ou abrir manualmente no navegador
```
Expected: a faixa de status no topo mostrando "publicada" com o resumo curto, e a análise nova aparecendo na seção "Resumo do dia".

- [ ] **Step 6: Commit**

```bash
git add analises dados/analise_status.json docs/index.html
git commit -m "chore: preenche lacuna de análise até $(date -u +%Y-%m-%d) — validação pré go-live"
```

---

### Task 6: Configurar a rotina agendada na nuvem

**Files:**
- Nenhum arquivo de código — configuração operacional via skill `schedule`.

**Interfaces:**
- Consumes: `scripts/lacuna_analise.py` (Task 1), `scripts/analise_brief.md` (Task 2), `dados/analise_status.json` (Task 3), acesso de escrita ao repositório git.
- Produces: uma rotina agendada ativa que roda dias úteis e mantém `analises/` e `dados/analise_status.json` atualizados.

- [ ] **Step 1: Confirmar acesso de escrita ao repositório a partir de um agente na nuvem**

Antes de agendar, validar manualmente (via uma execução avulsa do agente, não agendada) que ele consegue `git pull`, escrever um arquivo e dar `git push` neste repositório. Se não conseguir, resolver a autenticação antes de prosseguir — sem isso a rotina agendada falha silenciosamente todo dia.

- [ ] **Step 2: Invocar a skill `schedule` para criar a rotina**

Usar a skill `schedule` (não `CronCreate` diretamente) para criar uma rotina com:

- **Cadência:** dias úteis, ~10:15 UTC (~07:15 Brasília)
- **Prompt da rotina:**

```
Você é o agente de análise diária do projeto reforma-tributaria-monitor.

1. git pull no repositório.
2. Rode `python3 scripts/lacuna_analise.py` e leia o JSON de saída.
3. Se `dados_de_hoje_disponiveis` for false: espere e tente de novo o
   passo 2, checando a cada poucos minutos, até no máximo 11:00 UTC
   (~08:00 Brasília). Se esgotar a janela sem sucesso: grave
   dados/analise_status.json com {"data": "<hoje>",
   "situacao": "dados_pendentes", "gerado_em": "<timestamp UTC ISO 8601>"},
   dê `git pull --rebase --autostash`, comite, empurre, envie push
   notification avisando que a varredura de hoje não chegou, e pare.
4. Leia scripts/analise_brief.md e aplique o critério dele aos `itens`
   do JSON da lacuna.
5. Se não sobrar nenhum item relevante: grave dados/analise_status.json
   com situacao "sem_novidade" e o mesmo formato de timestamp. Dê
   `git pull --rebase --autostash`, comite, empurre, envie push
   notification "sem novidades relevantes hoje", e pare.
6. Se sobrar item relevante: escreva analises/<hoje>.md seguindo a
   estrutura do brief. Grave dados/analise_status.json com situacao
   "publicada" e um resumo_curto (ex: "3 novidades, 1 exige ação"). Dê
   `git pull --rebase --autostash`, comite os dois arquivos juntos, e
   empurre — se o push falhar por conflito, repita pull+push uma vez.
7. Envie push notification com o resumo_curto.
8. Se qualquer passo falhar de forma inesperada e não coberta acima:
   envie push notification de erro com a mensagem da exceção, para
   revisão manual. Nunca termine em silêncio sem gravar status ou
   notificar.
```

- [ ] **Step 3: Disparar uma execução manual única antes de confiar no agendamento**

Rodar a rotina uma vez fora do horário agendado (usando o disparo manual da própria skill `schedule`, se disponível) contra o estado atual do repositório. Conferir: `dados/analise_status.json` foi atualizado, o commit apareceu no histórico do git, e a push notification chegou.

- [ ] **Step 4: Confirmar o agendamento ativo**

Usar a ação de listagem/status da skill `schedule` para confirmar que a rotina está registrada com a cadência correta.

---

## Fora de escopo deste plano

- Ajuste de `scripts/dou.py` para distinguir "manutenção programada" de "credencial inválida" no login do INLABS — registrado na spec como item avulso, independente deste projeto.
- Qualquer mudança nas 12 fontes web ou na regex `RELEVANTE` da varredura.
