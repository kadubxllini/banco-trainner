# RADAR - Trainner RH

Painel web para acompanhar empresas e processos de recrutamento em uma tabela
compacta, com vagas, etapas, selecionadoras e pastas.

**Acesso:** [radar.clasure.com.br](https://radar.clasure.com.br).
Para usar basta um navegador e uma conta fornecida pela equipe. Não é necessário
instalar Python no computador do usuário.

## O que o sistema faz

- Empresas em pastas e subpastas, busca e filtros.
- Várias vagas por empresa, etapas editáveis na tabela e taxas por processo.
- Selecionadoras e contatos vinculados às empresas.
- Histórico de mensagens e anexos por empresa.
- Calendário de interações e lembretes com conclusão.
- Relatório diário com autor dos novos movimentos e filtros automáticos por
  período, usuário, tipo e texto, no horário de Cuiabá (GMT−4).
- Temas claro/escuro, janelas nativas do navegador, exportação CSV e download do banco.

## Contas e uso simultâneo

O acesso é individual, sem cadastro público. O administrador cria ou redefine
contas pelo terminal. Senhas não fazem parte deste repositório.
Sessões expiram após 30 minutos de inatividade ou 8 horas de duração.

Computadores diferentes podem trabalhar simultaneamente. Atualize a tela de
empresas para mostrar mudanças de outra pessoa. Evite editar a mesma empresa
ao mesmo tempo: o último formulário salvo pode sobrescrever alterações anteriores.
O relatório identifica a conta autenticada; registros anteriores à identificação
por usuário permanecem sem autor conhecido.

## Execução local

Recomendado: Python 3.12, usado também na implantação Linux. O projeto usa Flask,
SQLite, Jinja, JavaScript e CSS próprios. Não há build Node, Tailwind ou daisyUI
na implementação atual.

No PowerShell, a partir da raiz:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_access.py --email seu-email@trainner.com.br
.\.venv\Scripts\python.exe app.py
```

A senha é solicitada sem exibi-la. Abra [localhost:5000](http://127.0.0.1:5000).
O início por `app.py` cria as tabelas. O servidor de desenvolvimento é para uso
local; produção usa Gunicorn e Nginx.

| Caminho local padrão | Conteúdo |
| --- | --- |
| `banco_de_dados/dados.db` | Empresas, processos, mensagens e relatório |
| `instance/access.db` | Contas, sessões e tentativas de login |
| `instance/session.key` | Chave privada de assinatura |
| `static/uploads/` | Anexos privados servidos por rota autenticada |

Esses arquivos são ignorados pelo Git. Um clone não contém dados de produção.
Desenvolva com um banco separado e nunca publique credenciais ou backups.

## Backups

| Modalidade | Conteúdo | Horário e retenção |
| --- | --- | --- |
| Download no painel | Banco operacional e relatório | Manual, com login |
| Instalador Windows | Mesmo banco operacional | 13h no horário do PC; até 7 cópias |
| Serviço na VPS | Banco, contas, chave e anexos | 07h UTC / 03h Cuiabá, atraso de até 5 min; até 7 cópias automáticas |

Download e backup Windows não incluem contas nem anexos. Para o agendamento
Windows, o PC precisa estar ligado, com internet e usuário conectado ao Windows.
Backups na própria VPS não substituem uma cópia privada externa.

## Documentação

- [Relatório diário](DAILY_REPORT.md): eventos, autores, fuso e limitações.
- [Segurança e acessos](SECURITY.md): autenticação, sessões e configuração.
- [VPS e deploy](deploy/README.md): diretórios, serviços, publicação e recuperação.
- [Backup Windows](windows-backup/LEIA-ME.txt): instalação, destino e remoção.

Principais arquivos: `app.py` (rotas), `security.py` (acessos), `daily_report.py`
(histórico), `templates/` e `static/` (telas), `backup_radar.py` (backup da VPS)
e `windows-backup/` (cliente Windows).

## Verificação de alterações

```powershell
.\.venv\Scripts\python.exe -m unittest test_security.SecurityTests test_daily_report.DailyReportTests
```

Os testes usam bancos temporários e contas exclusivas de teste. A suíte copia
`banco_de_dados/dados.db` como base; inicialize o banco local com `app.py` antes.
Confira também os fluxos no navegador, nos dois temas, em telas menores e com zoom.
Não inclua bancos ou artefatos de teste nos commits.
