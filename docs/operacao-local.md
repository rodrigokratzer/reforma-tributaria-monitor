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
