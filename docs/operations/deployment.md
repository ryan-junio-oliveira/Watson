# Implantação

Guia para executar o Watson em produção, incluindo gerenciamento por **supervisord** (Linux) e **serviço Windows**, além da geração de um **executável**.

---

## Linux — Supervisord

O Watson roda como um programa do supervisord chamado `watson`.

### Instalação automática

```bash
sudo bash setup_supervisor.sh
```

O script:
1. Instala o supervisord e o Tesseract (se necessário).
2. Corrige a configuração principal do supervisord.
3. Cria o venv e instala as dependências.
4. Instala `watson-supervisord.conf`.
5. Inicia/rele o programa `watson`.

### Comandos de operação

Todos os comandos usam `-c /etc/supervisor/supervisord.conf` para apontar para a configuração correta do sistema.

| Comando | Descrição |
|---|---|
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf status watson` | Ver status |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf start watson` | Iniciar |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf stop watson` | Parar |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf restart watson` | Reiniciar |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf reread` | Reler configs alterados |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf update` | Aplicar configs novos |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf tail -f watson` | Log em tempo real |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf tail -100 watson` | Últimas 100 linhas |
| `sudo supervisorctl -c /etc/supervisor/supervisord.conf status` | Status de todos os programas |

> **Dica (alias):** adicione `alias sw='sudo supervisorctl -c /etc/supervisor/supervisord.conf'` no `~/.bashrc` e use `sw status watson`, `sw restart watson`, etc.

### Gerenciar o daemon supervisord (systemd)

| Comando | Descrição |
|---|---|
| `sudo systemctl status supervisor` | Status do daemon |
| `sudo systemctl start supervisor` | Iniciar |
| `sudo systemctl stop supervisor` | Parar |
| `sudo systemctl restart supervisor` | Reiniciar |
| `sudo systemctl enable supervisor` | Ativar no boot |
| `sudo systemctl disable supervisor` | Desativar no boot |
| `sudo systemctl reload supervisor` | Recarregar configs |

> O supervisord como serviço systemd inicia automaticamente no boot, e o programa `watson` também (`autostart=true`).

### Atualizar o serviço após deploy

```bash
cd ~/palace/Watson
git pull
sudo bash setup_supervisor.sh    # copia config, recarrega e inicia
```

### Logs (Linux)

| Arquivo | Descrição |
|---|---|
| `logs/supervisor.log` | Saída do programa watson |
| `/var/log/supervisor/supervisord.log` | Log do próprio supervisord |
| `logs/ai_agent.log` | Log da aplicação (configurado no `.env`) |

---

## Windows — Serviço nativo

O Watson pode rodar como um **serviço Windows** via `service.py` (win32serviceutil).

```bat
python service.py install    REM instala o serviço 'WatsonRAG'
python service.py start      REM inicia o serviço
python service.py stop       REM para o serviço
python service.py remove     REM remove o serviço
```

- Nome do serviço: `WatsonRAG`
- Executa o uvicorn em `0.0.0.0:9000`

---

## Windows — Executável (PyInstaller)

Gere um executável standalone com `build.bat`:

```bat
build.bat
```

Usa `watson.spec` (PyInstaller) para compilar `api.py` em `dist\watson\watson.exe`, copiando `.env` e `documents/` e criando os diretórios `logs/` e `database/`. O executável pode ser usado como serviço.

---

## Testar após iniciar

```bash
curl http://localhost:9000/api/health
curl http://localhost:9000/docs    # documentação interativa
```

---

## Próximos passos

- [Solução de problemas](troubleshooting.md)
- [Monitoramento](../guides/monitoring.md)
