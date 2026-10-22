# Relatório diário

A aba Relatório diário abre `/relatorio-diario`, exige o mesmo login do painel
e permite filtrar por uma data ou período, movimento e texto (incluindo empresa
e mensagem). Exibe até 100 movimentos por página, agrupados por dia.

O dia usa GMT−4 fixo, conforme solicitado para Cuiabá: 00:00 local inclusive
até 00:00 do dia seguinte exclusive. As datas do histórico ficam em UTC e
são convertidas para apresentação e filtro, sem depender do fuso da VPS.

São registrados os cadastros, alterações e exclusões de empresas, pastas,
vagas, etapas e selecionadoras; vínculos e desvínculos nas empresas; mudanças
de etapa e taxa; contatos; mensagens e anexos; criação e conclusão de lembretes.
Alterações de pasta e prioridade das empresas também aparecem. O texto completo
de mensagens editadas ou excluídas é preservado. Não são registrados acessos,
IP, cookies, senhas ou outras informações de autenticação.

A gravação ocorre na mesma transação SQLite da operação, em MovimentoDiario.
Não há limpeza automática nem vínculo em cascata com os cadastros, para manter
o histórico após exclusões. O backup do banco inclui o relatório.

O controle compara o estado das dez tabelas operacionais antes/depois das
gravações POST da aplicação, sob uma transação de escrita. A comparação fica
em memória; apenas diferenças reais são persistidas. Isso evita gerar eventos
falsos quando o formulário regrava vínculos ou contatos idênticos. As tabelas
de autenticação e o histórico acumulado não entram nessa comparação.

O registro começa no primeiro uso desta versão. Não há reconstrução de eventos
anteriores, nem captura de alterações feitas diretamente no arquivo SQLite por
programas externos. A importação de um banco substitui seu histórico pelo que
estiver contido no arquivo importado.

Validação local: `python -m unittest test_security.SecurityTests test_daily_report.DailyReportTests`.
Os testes usam bancos descartáveis e credenciais exclusivas de teste.
