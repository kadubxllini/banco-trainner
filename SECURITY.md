# Acesso e segurança do RADAR

O painel, APIs, relatórios e anexos exigem login. Não existe cadastro público.

- Senhas usam o hash scrypt do Werkzeug. Nenhuma senha inicial está no código.
- `instance/access.db` armazena contas, tentativas e sessões; `instance/session.key` assina o cookie. Esses arquivos são privados e ignorados pelo Git. Preserve-os no servidor e em backups privados; não publique essa pasta.
- Sessões expiram após 30 minutos de inatividade ou 8 horas. Sair revoga a sessão no servidor. Redefinir a senha com `setup_access.py` revoga as sessões dessa conta, sem encerrar sessões de outras contas.
- São permitidas até 10 tentativas de login por IP e 30 por conta em uma janela de 15 minutos. Na implantação com proxy, o Nginx substitui os cabeçalhos encaminhados e o Flask usa RADAR_PROXY=1. Não habilite confiança em proxy se o backend estiver exposto diretamente.
- Alterações e exclusões exigem POST e token CSRF. Downloads exigem sessão e não são armazenados em cache.
- Uploads têm limite de 20 MiB por requisição e uma lista de extensões permitidas. Somente imagens raster reconhecidas pelo cabeçalho são exibidas; os demais anexos são baixados como arquivos. Nomes recebem UUID e caminhos não podem escapar da pasta de anexos.
- Campos dinâmicos do histórico, contatos e lembretes são escapados antes de compor HTML. O CSV evita fórmulas iniciadas por caracteres perigosos.

## Criar ou redefinir um acesso

Execute no ambiente Python do aplicativo:

```
python setup_access.py --email seu-email@empresa.com.br
```

A senha é solicitada sem eco e não deve ser colocada no comando ou no Git.
Ela deve ter entre 12 e 1024 caracteres. O comando cria ou redefine a conta;
o nome exibido é derivado do e-mail, com a identificação Trainner para a conta
de suporte existente. Não há tela pública para administrar usuários.

## Publicação na VPS

O projeto possui configuração de produção em deploy/. Ao instalar ou atualizar uma implantação:

1. Use HTTPS no Nginx e um servidor WSGI de produção; não exponha `app.run()`.
2. Configure `RADAR_HTTPS=1` para cookies Secure e HSTS.
3. Configure `RADAR_TRUSTED_HOSTS` com os domínios permitidos separados por vírgulas. Por padrão somente localhost e os endereços de loopback são aceitos.
4. Encaminhe todas as requisições, inclusive `/static/uploads/`, ao Flask. Não exponha anexos, banco, backups ou `instance/` por um alias público do Nginx.
5. Execute com um usuário sem privilégios e limite acesso às pastas de dados e `instance/`. Com um proxy compartilhando o mesmo IP entre usuários, mantenha os limites de login também no proxy.

A CSP bloqueia objetos, frames e origens externas, mas ainda permite scripts inline para compatibilidade com os handlers da interface legada. Não se trata de certificação ou garantia de segurança absoluta; autenticação e proteção da aplicação não substituem TLS, atualização de dependências e configuração correta do servidor.

## Verificações

`python test_security.py` testa autenticação de todas as rotas, CSRF, logout revogável, expiração, limite de tentativas, exclusões, anexos e CSV em bancos temporários.

`python validate_radar.py` verifica os fluxos funcionais autenticados em uma cópia do banco.
Essas verificações também precisam de um banco local inicializado em
`banco_de_dados/dados.db`; os dados de trabalho são copiados para diretórios
temporários. `validate_radar.py` gera `outputs/radar-preview.html`, que pode conter
dados copiados do banco e deve permanecer privado e fora do Git.

O relatório guarda nome e e-mail do autor no banco operacional e no backup baixado.
Hashes de senha e sessões ficam no banco de acesso separado. Registros antigos
sem identificação não recebem um autor presumido.

Para validar também autoria, filtros e datas:
`python -m unittest test_daily_report.DailyReportTests`.
