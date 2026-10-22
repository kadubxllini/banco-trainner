"""Business-report regressions. Every request uses a disposable DB and login."""
import io
import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from test_security import SecurityTests
import app as module
from daily_report import day_bounds


class DailyReportTests(unittest.TestCase):
    setUp = SecurityTests.setUp
    token = SecurityTests.token
    login = SecurityTests.login

    def post(self, path, data=None, payload=None):
        token = self.login_token
        if payload is not None:
            response = self.client.post(path, json=payload, headers={'X-CSRF-Token': token})
        else:
            response = self.client.post(path, data=data or {}, headers={'X-CSRF-Token': token})
        self.assertIn(response.status_code, (200, 302))
        return response

    def events(self):
        with closing(sqlite3.connect(module.BANCO_PATH)) as conn:
            return conn.execute('SELECT categoria,empresa,resumo,detalhes,antes,depois FROM MovimentoDiario ORDER BY id').fetchall()

    def scalar(self, sql):
        with closing(sqlite3.connect(module.BANCO_PATH)) as conn:
            return conn.execute(sql).fetchone()[0]

    def company(self, name='Empresa Teste Diário', linked=False):
        self.login_token = self.login()
        data = {'nome_cliente': name}
        if linked:
            self.vaga = self.scalar('SELECT id FROM Vaga LIMIT 1')
            self.stage = self.scalar('SELECT id FROM Status LIMIT 1')
            self.selector = self.scalar('SELECT id FROM Selecionadora LIMIT 1')
            data.update(vagas_ids=str(self.vaga), selecionadoras_ids=str(self.selector))
            data[f'status_vaga_{self.vaga}'] = str(self.stage)
        self.post('/salvar', data)
        return self.scalar('SELECT MAX(id) FROM Cliente')

    def test_create_company_links_and_stage_change(self):
        company = self.company(linked=True)
        self.assertEqual([e[0] for e in self.events()], ['Empresa', 'Vaga da empresa', 'Selecionadora da empresa'])
        self.assertTrue(all(e[1] == 'Empresa Teste Diário' for e in self.events()))
        self.post('/api/processos/etapa', payload={'cliente_id':company,'vaga_id':self.vaga,'status_id':None})
        event = self.events()[-1]
        details = json.loads(event[3])
        self.assertEqual(event[0], 'Vaga da empresa')
        self.assertEqual(details[0]['campo'], 'Etapa')
        self.assertIn('→ Não definido', details[0]['valor'])

    def test_unchanged_form_rewrites_are_not_movements(self):
        company = self.company(linked=True)
        data={'nome_cliente':'Empresa Teste Diário','vagas_ids':str(self.vaga),
              'selecionadoras_ids':str(self.selector),f'status_vaga_{self.vaga}':str(self.stage),
              'contato_nome[]':'Ana','contato_email[]':'ana@example.test','contato_telefone[]':'123'}
        self.post(f'/editar/{company}', data)
        count=len(self.events())
        self.post(f'/editar/{company}', data)
        self.assertEqual(len(self.events()), count)
        data.pop('vagas_ids')
        data.pop('selecionadoras_ids')
        self.post(f'/editar/{company}', data)
        self.assertEqual([e[0] for e in self.events()[-2:]], ['Vaga da empresa', 'Selecionadora da empresa'])
        self.assertTrue(all('desvinculada' in e[2] for e in self.events()[-2:]))

    def test_messages_attachments_reminders_and_deleted_history(self):
        company = self.company()
        self.post('/enviar_mensagem', {'cliente_id':company,'texto':'Proposta enviada à empresa'})
        message = self.scalar('SELECT MAX(id) FROM Mensagem')
        self.post(f'/editar_mensagem/{message}', {'texto':'Proposta revisada'})
        edited = self.events()[-1]
        self.assertIn('Proposta enviada à empresa → Proposta revisada', edited[3])
        self.post('/api/criar_lembrete', {'mensagem_id':message,'texto':'Retornar contato','data_alerta':'2026-10-23T13:00'})
        reminder = self.scalar('SELECT MAX(id) FROM Lembrete')
        self.assertEqual(self.events()[-1][1], 'Empresa Teste Diário')
        self.post(f'/api/marcar_lembrete_lido/{reminder}')
        self.assertIn('concluído', self.events()[-1][2])
        self.post('/enviar_mensagem', {'cliente_id':company,'arquivo':(io.BytesIO(b'proposta de teste'),'proposta.txt')})
        self.assertEqual(self.events()[-1][0], 'Anexo')
        self.post(f'/excluir/{company}')
        events=self.events()
        self.assertTrue(any('Proposta revisada' in e[3] and 'excluída' in e[2] for e in events))
        self.assertTrue(any(e[0]=='Lembrete' and 'excluído' in e[2] for e in events))
        self.assertTrue(all(e[1]=='Empresa Teste Diário' for e in events))
        page=self.client.get('/relatorio-diario').get_data(as_text=True)
        self.assertIn('Proposta revisada',page)
        self.assertIn('Empresa Teste Diário',page)

    def test_failed_and_rolled_back_operations_are_not_saved(self):
        self.company()
        before = len(self.events())
        response=self.client.post('/salvar',data={'nome_cliente':'Sem CSRF'})
        self.assertEqual(response.status_code,400)
        with module.app.test_request_context('/salvar', method='POST'):
            conn=module.conectar()
            conn.execute("INSERT INTO Cliente(nome) VALUES ('Nunca confirmado')")
            conn.rollback()
            conn.close()
        self.assertEqual(len(self.events()),before)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Cliente WHERE nome='Nunca confirmado'"),0)

    def test_midnight_cuiaba_boundaries_and_date_filters(self):
        self.login_token=self.login()
        for moment, name in [('2026-10-22T03:59:59.999999Z','Dia anterior'),
                             ('2026-10-22T04:00:00.000000Z','Início do dia'),
                             ('2026-10-23T03:59:59.999999Z','Fim do dia'),
                             ('2026-10-23T04:00:00.000000Z','Dia seguinte')]:
            with patch('daily_report.utc_now',return_value=moment):
                self.post('/salvar',{'nome_cliente':name})
        page=self.client.get('/relatorio-diario?inicio=2026-10-22&fim=2026-10-22')
        text=page.get_data(as_text=True)
        self.assertEqual(page.status_code,200)
        self.assertIn('Início do dia',text)
        self.assertIn('Fim do dia',text)
        self.assertNotIn('Dia anterior',text)
        self.assertNotIn('Dia seguinte',text)
        self.assertIn('00:00:00',text)
        self.assertIn('23:59:59',text)
        self.assertEqual(day_bounds('2026-10-22','2026-10-22'),('2026-10-22T04:00:00.000000Z','2026-10-23T04:00:00.000000Z'))

    def test_filters_escaping_protection_and_invalid_dates(self):
        self.company('<script>alert(1)</script> 100%')
        text=self.client.get('/relatorio-diario?busca=100%25').get_data(as_text=True)
        self.assertIn('&lt;script&gt;',text)
        self.assertNotIn('<script>alert(1)</script>',text)
        self.assertNotIn('report-movement-body',self.client.get('/relatorio-diario?categoria=Mensagem').get_data(as_text=True))
        for query in ['inicio=erro','inicio=2026-12-01&fim=2026-01-01','pagina=-1','inicio=2020-01-01&fim=2026-01-01']:
            self.assertEqual(self.client.get('/relatorio-diario?'+query).status_code,400)
        self.assertEqual(module.app.test_client().get('/relatorio-diario').status_code,302)
        with self.client.get('/static/daily-report.js') as response:
            self.assertEqual(response.status_code,200)

    def test_catalogue_changes_and_backup_include_history(self):
        self.login_token=self.login()
        for path, field in [('vaga','nome_vaga'),('status','nome_status'),('selecionadora','nome_selecionadora'),('pasta','nome_pasta')]:
            self.post('/salvar_'+path,{field:'Cadastro Diário '+path})
        self.assertEqual({e[0] for e in self.events()},{'Vaga','Etapa','Selecionadora','Pasta'})
        response=self.client.get('/backup/banco')
        db=sqlite3.connect(':memory:')
        try:
            db.deserialize(response.data)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM MovimentoDiario').fetchone()[0],4)
        finally:
            db.close()

    def test_pagination_does_not_drop_movements(self):
        self.company()
        with module.app.test_request_context('/salvar', method='POST'):
            conn=module.conectar()
            conn.executemany('INSERT INTO Vaga(nome) VALUES (?)',[(f'Cargo {i}',) for i in range(110)])
            conn.commit()
            conn.close()
        first=self.client.get('/relatorio-diario').get_data(as_text=True)
        second=self.client.get('/relatorio-diario?pagina=2').get_data(as_text=True)
        self.assertEqual(first.count('class="report-movement"'),100)
        self.assertEqual(second.count('class="report-movement"'),11)

    def test_history_failure_rolls_back_the_business_operation(self):
        self.company()
        with closing(sqlite3.connect(module.BANCO_PATH)) as db:
            db.execute("CREATE TRIGGER reject_history BEFORE INSERT ON MovimentoDiario BEGIN SELECT RAISE(ABORT, 'test history failure'); END")
            db.commit()
        count=len(self.events())
        with module.app.test_request_context('/salvar', method='POST'):
            conn=module.conectar()
            try:
                conn.execute("INSERT INTO Vaga(nome) VALUES ('Nao pode ficar sem historico')")
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.commit()
            finally:
                conn.close()
        self.assertEqual(len(self.events()),count)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Vaga WHERE nome='Nao pode ficar sem historico'"),0)

    def test_sequential_connections_only_record_their_own_changes(self):
        self.company()
        baseline=len(self.events())
        for company_name in ['Requisicao A','Requisicao B']:
            with module.app.test_request_context('/salvar', method='POST'):
                conn=module.conectar()
                conn.execute('INSERT INTO Cliente(nome) VALUES (?)',(company_name,))
                conn.commit()
                conn.close()
        self.assertEqual(len(self.events()),baseline+2)
        self.assertEqual([e[1] for e in self.events()[-2:]],['Requisicao A','Requisicao B'])

    def test_two_accounts_attribution_and_user_filter(self):
        from security import create_access
        self.login_token=self.login()
        create_access(module.app,'sandra@example.test','Test-password-2026!','Sandra')
        # Creating another account must preserve the first user's active session.
        self.assertEqual(self.client.get('/relatorio-diario').status_code,200)
        other=module.app.test_client()
        token=self.token(other.get('/login'))
        other.post('/login',data={'email':'sandra@example.test','password':'Test-password-2026!','csrf_token':token})
        other_token=self.token(other.get('/'))
        self.post('/salvar',{'nome_cliente':'Empresa do primeiro usuário','usuario_email':'sandra@example.test'})
        response=other.post('/salvar',data={'nome_cliente':'Empresa da Sandra'},headers={'X-CSRF-Token':other_token})
        self.assertEqual(response.status_code,302)
        with closing(sqlite3.connect(module.BANCO_PATH)) as db:
            authors=db.execute('SELECT empresa,usuario_email,usuario_nome FROM MovimentoDiario ORDER BY id').fetchall()
        self.assertEqual(authors,[('Empresa do primeiro usuário','test@example.com','Test'),('Empresa da Sandra','sandra@example.test','Sandra')])
        page=self.client.get('/relatorio-diario?usuario=sandra@example.test').get_data(as_text=True)
        self.assertIn('Empresa da Sandra',page)
        self.assertNotIn('Empresa do primeiro usuário',page)
        self.assertIn('Por Sandra',page)
        self.assertEqual(other.get('/relatorio-diario').status_code,200)

    def test_legacy_history_migration_keeps_unknown_author(self):
        self.company()
        with closing(sqlite3.connect(module.BANCO_PATH)) as db:
            db.execute('DROP INDEX movimento_usuario')
            db.execute('ALTER TABLE MovimentoDiario DROP COLUMN usuario_email')
            db.execute('ALTER TABLE MovimentoDiario DROP COLUMN usuario_nome')
            db.commit()
        response=self.client.get('/relatorio-diario?usuario=__sem_usuario__')
        self.assertEqual(response.status_code,200)
        self.assertIn('Empresa Teste Diário',response.get_data(as_text=True))
        self.assertIn('Não identificado',response.get_data(as_text=True))
        self.assertEqual(len(self.events()),1)


if __name__ == '__main__':
    unittest.main()
