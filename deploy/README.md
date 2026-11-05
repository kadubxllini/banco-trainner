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

## Publicar uma revisão

`update-release.sh` atualiza uma instalação existente; não é um instalador inicial.
Ele espera `/home/opc/radar-final.tar`, os diretórios persistentes, ambiente Python,
certificado e configuração privada já preparados. Instale as dependências de
`requirements-production.txt`. Na primeira instalação, inicialize as tabelas
com `criar_tabelas()` antes de iniciar o Gunicorn.

A configuração Nginx usa a zona `radar_login`: ela precisa existir no contexto
`http` antes de carregar o site. Na instalação em uso, a declaração é externa ao
repositório, em `/etc/nginx/conf.d/00-radar-limits.conf`. O formato esperado é
`limit_req_zone <chave-do-limite> zone=radar_login:10m rate=10r/m;`; a chave pode
restringir o limite aos POST de login. Preserve e revise essa configuração ao
provisionar outra VPS; o script não a cria. Confira também os includes
`/etc/nginx/radar-cloudflare.inc` e `/etc/nginx/radar-proxy.inc`. As faixas de IP da
Cloudflare versionadas devem ser revisadas quando a infraestrutura for atualizada.

Após revisar e validar o commit, na raiz do repositório:

```text
git archive --format=tar --output=radar-final.tar HEAD
```

Transfira o arquivo para `/home/opc/radar-final.tar` e o script
`deploy/update-release.sh` para o servidor por um canal administrativo autorizado.
Garanta finais de linha LF ao transferir o script do Windows. Na VPS:

```bash
sudo bash /home/opc/update-release.sh <hash-do-commit>
```

O script cria backup, prepara uma nova release, valida o Nginx, troca `current`,
reinicia o RADAR e verifica `/login` via HTTPS no origin. Se esse último teste
falhar, restaura o link da release anterior. Esse rollback não desfaz migrações
do banco nem todas as mudanças de configuração; confira-as separadamente.

Confira também o domínio público, login, telas alteradas e estáticos versionados:
o teste do origin não verifica o cache do navegador/CDN. Migrações do relatório
são aditivas e executadas ao abrir uma conexão. Nunca substitua o banco de
produção por uma cópia local durante um deploy de código.

## Recuperação de dados

Preserve os dados atuais em backup privado antes de restaurar. Pare `radar.service`
para impedir gravações concorrentes. Valide o SQLite escolhido com
`PRAGMA integrity_check`, restaure no diretório persistente correto e mantenha
dono `radar:radar` e permissões privadas. Reinicie e confira integridade, login
e painel. Trate arquivos WAL/journal de forma consistente; não copie um SQLite
em uso como se fosse um snapshot.

O `.db` baixado no painel contém apenas dados operacionais e relatório.
O `radar-auto-*.tar.gz` contém também `access.db`, `session.key` e `uploads/`.
Restaurar autenticação pode restaurar sessões antigas: considere revogá-las.
Restaurar um banco antigo também retorna o relatório ao estado daquele backup.
