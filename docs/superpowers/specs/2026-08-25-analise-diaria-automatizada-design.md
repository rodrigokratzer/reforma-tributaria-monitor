# Análise diária automatizada — design

**Data:** 2026-08-25
**Status:** aprovado para plano de implementação

## Contexto e objetivo

O projeto já separa deliberadamente duas camadas (ver README): **Fatos** (varredura
automática, sem IA, `varredura.yml` às 06:40 Brasília) e **Análise** (o que mudou, qual
o impacto — hoje escrita manualmente por mim em sessões avulsas, e publicada em
`analises/AAAA-MM-DD.md`).

De 7 dias com dados coletados, só 2 têm análise (`2026-08-17.md`, `2026-08-20.md`).
O objetivo deste projeto é fechar essa lacuna: automatizar a produção diária da
análise, mantendo a mesma qualidade e formato das duas análises manuais já
validadas, sem introduzir custo de API por token (usa a assinatura Claude já
paga, não `ANTHROPIC_API_KEY` faturada por uso).

**Restrição orientadora:** precisa funcionar mesmo com o computador do usuário
desligado — não pode depender de uma máquina local ligada.

## Decisões já tomadas (resumo das aprovações)

| Decisão | Escolha |
|---|---|
| Onde roda | Agente agendado na nuvem do Claude Code (skill `/schedule`), vinculado à assinatura — não GitHub Actions + API paga, não máquina local |
| Sincronismo com a varredura | Auto-checagem com retentativa (confere se os dados de hoje chegaram; espera e tenta de novo numa janela curta antes de desistir) |
| Publicação | Direto, sem aprovação manual prévia — com reversão fácil via `git revert` como saída de emergência |
| Entrega | Painel (já existente) **+** push notification para o usuário a cada execução |
| Dia sem novidade relevante | Não sobrescreve a última análise substantiva no painel — usa um status separado e sempre visível (ver abaixo), para o time (que só vê o painel, não o push) também saber que a rotina rodou |

## Arquitetura

Duas camadas continuam desacopladas — a única ponte entre elas é git:

```
[Fatos — inalterado]                    [Análise — novo]
GitHub Actions (varredura.yml)          Agente agendado (Claude Code, nuvem)
  06:40 Brasília, dias úteis              ~07:15 Brasília, dias úteis
  scrapes 12 fontes + DOU (opcional)      git pull → checa dados de hoje
  escreve dados/*.json                    → determina lacuna de cobertura
  commit + push                           → analisa (filtra ruído, categoriza impacto)
                                           → escreve analises/{data}.md
                                           → atualiza dados/analise_status.json
                                           → commit + push
                                           → push notification pro usuário
                        │
                        ▼
         push em analises/** ou dados/analise_status.json
         (já cai no path-filter existente de varredura.yml)
                        │
                        ▼
         varredura.yml regenera docs/index.html — painel atualizado
```

O `varredura.yml` precisa de um ajuste mínimo: hoje seu gatilho de `push.paths`
cobre `estado.json`, `analises/**`, `scripts/**` — falta incluir
`dados/analise_status.json` para que uma atualização de status sem análise nova
(dia tranquilo) também regenere o painel.

## Componentes novos

1. **Rotina agendada** — configurada via skill `/schedule`, dias úteis,
   ~07:15 Brasília, com lógica de auto-checagem/retentativa até ~08:00.

2. **`scripts/analise_brief.md`** — brief escrito com o formato e critérios já
   validados nas duas análises manuais: seções Ação requerida / Acompanhar /
   Contexto / No radar / Nota sobre a coleta; tom; e as armadilhas documentadas
   no README (nunca casar termo contra domínio/remetente, checar data
   declarada vs. pasta de upload, etc.). Dá instrução consistente ao agente a
   cada execução, em vez de reinventar do zero.

3. **`scripts/lacuna_analise.py`** (novo, determinístico) — não depende de
   julgamento do modelo: lista `analises/*.md` existentes, identifica a data
   mais recente coberta, lista `dados/AAAA-MM-DD.json` publicados depois dela
   até hoje, e devolve essa faixa + os itens de `novidades`/`historico`
   relevantes no período. Isolar essa bookkeeping em código comum evita que o
   agente "invente" a lacuna errada.

4. **`dados/analise_status.json`** (novo) — atualizado em **toda** execução do
   agente, independente do resultado:
   ```json
   {"data": "2026-08-26", "situacao": "publicada|sem_novidade|dados_pendentes",
    "gerado_em": "2026-08-26T10:22:00Z", "resumo_curto": "3 novidades, 1 exige ação"}
   ```

5. **Ajustes em `scripts/gerar_painel.py` e `scripts/painel_template.html`** —
   ler `analise_status.json` e renderizar uma faixa fixa no topo do painel
   (ex: "Última checagem: 26/08 07:22 — sem novidades relevantes"), visível
   para todo o time, sem depender do push. A análise completa mais recente
   continua sendo exibida normalmente abaixo, mesmo em dia sem novidade.

6. **Push notification** — enviada ao usuário ao final de cada execução
   (sucesso com novidade, sucesso sem novidade, ou falha), usando a
   capacidade nativa do Claude Code.

## Fluxo de dados

1. Agente acorda (dia útil, ~07:15 Brasília).
2. `git pull` no repositório.
3. Confere se `dados/{hoje}.json` / `novidades.json` refletem a data de hoje;
   se não, espera e tenta de novo dentro da janela (até ~08:00).
4. Roda `scripts/lacuna_analise.py` para obter a faixa de datas não coberta e
   os itens novos correspondentes.
5. Se a faixa não tiver itens relevantes: não escreve `analises/*.md`, grava
   `analise_status.json` com `situacao: "sem_novidade"`.
6. Se houver itens relevantes: aplica o critério de `analise_brief.md` para
   filtrar ruído e categorizar por impacto, escreve `analises/{hoje}.md`,
   grava `analise_status.json` com `situacao: "publicada"` e um
   `resumo_curto`.
7. Se os dados de hoje nunca chegarem (passo 3 esgotar a janela): grava
   `analise_status.json` com `situacao: "dados_pendentes"`, **não** escreve
   análise nova.
8. Commit + push (`git pull --rebase --autostash` antes, mesmo padrão do
   `varredura.yml`, para absorver corrida com outros commits automáticos).
9. Push notification com o resultado.
10. O push em `analises/**` ou `dados/analise_status.json` dispara o
    `varredura.yml` existente (após o ajuste de path-filter do item acima),
    que regenera `docs/index.html`.

## Tratamento de erro

- **Dados de hoje não chegam:** sem análise nova; status `dados_pendentes`;
  push avisando; a lacuna fica para o próximo run resolver.
- **Conflito de push:** `pull --rebase --autostash` + nova tentativa — mesmo
  padrão já usado em `varredura.yml`.
- **Falha do próprio agente:** push de erro, para o usuário saber que precisa
  olhar manualmente — nunca falha silenciosa.
- **Reversão de análise publicada errada:** `git revert` do commit — sem
  ferramenta especial, é a saída de emergência já decidida.

## Fora de escopo (registrado, não deste projeto)

- **Credencial/manutenção do INLABS:** a falha atual do DOU não é de
  infraestrutura (GitHub Actions é adequado e permanece). O erro de hoje
  (200 sem cookie) e a mensagem de manutenção programada do portal indicam
  que `dou.py` precisa distinguir "manutenção programada" de "credencial
  inválida" — os dois hoje caem no mesmo diagnóstico porque ambos respondem
  HTTP 200. Ajuste pontual futuro em `scripts/dou.py`, independente deste
  projeto.
- Não altera as 12 fontes web nem a lógica de filtro (`RELEVANTE`) da
  varredura.

## Validação antes do go-live

- Gerar retroativamente as análises que faltam (ex: 24/08, 25/08) e comparar
  com a régua de qualidade das duas análises manuais já publicadas.
- Testar `scripts/lacuna_analise.py` contra os casos de borda: dia sem
  novidade, dia com todas as fontes falhando, lacuna de mais de um dia
  (simular um dia pulado).
- Só ativar o agendamento real depois dessa validação.
