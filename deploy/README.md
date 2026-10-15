# RADAR na VPS

Destino: `https://radar.clasure.com.br`. Serviço `radar.service`, Gunicorn em loopback `127.0.0.1:5056`, atrás do Nginx. Python 3.12 e usuário dedicado `radar`.

Arquivos do aplicativo em `/var/oled/radar/releases/<revisao>`, com `current` apontando para a revisão publicada. Código e ambiente Python pertencem ao root; o serviço só escreve em `/var/oled/radar/shared`.

Dados persistentes:

- `shared/data/dados.db`: banco do RADAR.
- `shared/auth`: contas, sessões e chave de assinatura. Nunca servir essa pasta por HTTP.
- `shared/uploads`: anexos, disponíveis apenas pelas rotas autenticadas do aplicativo.
- `shared/backups`: sete backups automáticos mais recentes, com SQLite consistente, autenticação e anexos; acesso exclusivo do usuário do serviço. Os backups locais importados ficam em `shared/backups/importados` e não entram na limpeza automática.

Configuração privada em `/etc/radar/radar.env`: `RADAR_DATA_DIR`, `RADAR_INSTANCE_PATH`, `RADAR_UPLOAD_DIR`, `RADAR_BACKUP_DIR`, `RADAR_TRUSTED_HOSTS`, `RADAR_HTTPS=1`, `RADAR_PROXY=1`. O Nginx substitui os cabeçalhos encaminhados, e o backend só aceita conexões de loopback. Não habilite a confiança em proxy se expuser o Gunicorn diretamente.

O timer `radar-backup.timer` executa diariamente às 07:00 UTC (03:00 em Cuiabá), com atraso aleatório de até cinco minutos. Backups permanecem no mesmo servidor: recuperação de perda total da VPS exige uma cópia privada externa.

O Certbot administra o certificado. A renovação utiliza webroot `/var/www/radar-acme`, e um deploy hook recarrega o Nginx após a renovação. Nenhuma outra aplicação precisa ser reiniciada.

## Operação

```
sudo systemctl status radar radar-backup.timer
sudo journalctl -u radar -n 80 --no-pager
sudo systemctl start radar-backup.service
```

Para uma atualização, crie o backup antes de alterar a revisão, instale um novo diretório em `releases`, valide, troque o link `current` e reinicie apenas `radar`. Para rollback de código, restaure o link para a revisão anterior. Não sobrescreva `shared` durante atualizações.

O login é criado interativamente com `setup_access.py`; a senha não faz parte da revisão nem dos scripts de deploy.
