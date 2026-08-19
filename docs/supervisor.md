# Supervisor - Gerenciamento do Watson no Linux

O Watson roda como um programa do **supervisord** chamado `watson`.
Este guia documenta todos os comandos necessarios para operar o servico.

---

## Comandos rapidos

Todos os comandos usam `-c /etc/supervisor/supervisord.conf` para apontar
para o config correto do sistema (evita o erro *".ini file does not include
supervisorctl section"*).

| Comando | Descricao |
|---|---|
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf status watson` | Ver status do servico |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf start watson` | Iniciar o servico |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf stop watson` | Parar o servico |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf restart watson` | Reiniciar o servico |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf reread` | Reler configs alterados (sem reiniciar) |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf update` | Aplicar configs novos/alterados |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf tail -f watson` | Log do servico em tempo real |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf tail -100 watson` | Ultimas 100 linhas do log |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf reload` | Reiniciar o proprio supervisord |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf shutdown` | Encerrar o supervisord (para tudo) |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf status` | Status de todos os programas |

---

## Alternativa sem digitar `-c` (alias)

Adicione no `~/.bashrc`:

```bash
alias sw='sudo supervisorctl -c /etc/supervisor/supervisord.conf'
```

Depois use: `sw status watson`, `sw restart watson`, `sw tail -f watson`, etc.

---

## Gerenciando o supervisord (o proprio daemon)

| Comando | Descricao |
|---|---|
| `sudo systemctl status supervisor` | Status do daemon supervisor |
| `sudo systemctl start supervisor` | Iniciar o daemon |
| `sudo systemctl stop supervisor` | Parar o daemon |
| `sudo systemctl restart supervisor` | Reiniciar o daemon |
| `sudo systemctl enable supervisor` | Ativar na inicializacao do sistema |
| `sudo systemctl disable supervisor` | Desativar da inicializacao |
| `sudo systemctl reload supervisor` | Recarregar configs (equivalente ao reread+update) |

> O supervisord como servico do systemd (padrao em Debian/Ubuntu) ja inicia
> automaticamente no boot, e o programa `watson` tambem (`autostart=true`).

---

## Logs

| Arquivo | Descricao |
|---|---|
| `/home/administrador/palace/Watson/logs/supervisor.log` | Log de saida do programa watson |
| `/var/log/supervisor/supervisord.log` | Log do proprio supervisord (daemon) |
| `/home/administrador/palace/Watson/logs/ai_agent.log` | Log da aplicacao (configurado no .env) |

---

## Testar a API apos iniciar

```bash
curl http://localhost:9000/api/health
curl http://localhost:9000/docs   # documentacao interativa
```

---

## Reinstalar / atualizar config

```bash
cd ~/palace/Watson
git pull
sudo bash setup_supervisor.sh     # copia config, recarrega e inicia
```

---

## Solucao de problemas

| Sintoma | Causa / Solucao |
|---|---|
| `Error: .ini file does not include supervisorctl section` | Rodou `supervisorctl` sem `-c` dentro de `~/palace/Watson` (o `supervisord.conf` do projeto nao tem essa secao). Use sempre `-c /etc/supervisor/supervisord.conf`. |
| `PermissionError` / `Permission denied` | Socket acessivel apenas por root. Use `sudo` ou ajuste `chmod`/`chown` no `[unix_http_server]` do config. |
| `unix:///var/run/supervisor.sock no such file` | Supervisord nao esta rodando. Rode `sudo systemctl start supervisor`. |
| Servico para em segundos | Veja o log: `sudo supervisorctl -c /etc/supervisor/supervisord.conf tail -f watson` (ex.: Ollama fora do ar, porta 9000 ocupada). |