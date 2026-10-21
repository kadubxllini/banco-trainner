"""Security regressions, using disposable copies and test-only credentials."""
import io
import os
import re
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

temporary = tempfile.TemporaryDirectory()
os.environ['RADAR_INSTANCE_PATH'] = str(Path(temporary.name) / 'auth')
import app as module
from security import auth_connection, create_access

TEST_PASSWORD = 'Password-for-tests-2026!'


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary.name)
        module.BANCO_DIR = str(self.root / 'data')
        Path(module.BANCO_DIR).mkdir(exist_ok=True)
        module.BANCO_PATH = str(self.root / 'data' / 'dados.db')
        source = sqlite3.connect('file:banco_de_dados/dados.db?mode=ro', uri=True)
        with closing(sqlite3.connect(module.BANCO_PATH)) as target:
            source.backup(target)
        source.close()
        module.app.config.update(TESTING=True, UPLOAD_FOLDER=str(self.root / 'uploads'))
        module.criar_tabelas()
        with closing(auth_connection(module.app)) as db:
            db.execute('DELETE FROM Tentativa')
            db.execute('DELETE FROM Usuario')
            db.commit()
        create_access(module.app, 'test@example.com', TEST_PASSWORD)
        self.client = module.app.test_client()

    def token(self, response):
        return re.search(r'name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))[1]

    def login(self):
        token = self.token(self.client.get('/login'))
        response = self.client.post('/login', data={'email':'test@example.com', 'password':TEST_PASSWORD, 'csrf_token':token})
        self.assertEqual(response.status_code, 302)
        return self.token(self.client.get('/'))

    def test_every_data_route_requires_login(self):
        for route in module.app.url_map.iter_rules():
            if route.endpoint in {'login', 'static'}: continue
            url = re.sub(r'<(?:int:|path:)?\w+>', '1', route.rule)
            method = 'get' if 'GET' in route.methods else 'post'
            response = getattr(self.client, method)(url)
            self.assertIn(response.status_code, (302,401), url)
            self.assertNotIn(b'radarRows', response.data)
        self.assertEqual(self.client.get('/static/uploads/test.txt').status_code,302)
        with self.client.get('/static/radar.css') as response:
            self.assertEqual(response.status_code,200)

    def test_login_and_csrf(self):
        self.assertEqual(self.client.post('/login', data={}).status_code,400)
        token=self.login()
        self.assertEqual(self.client.post('/api/processos/etapa',json={}).status_code,400)
        self.assertEqual(self.client.post('/api/processos/etapa',json={},headers={'X-CSRF-Token':token}).status_code,400)
        response=self.client.get('/')
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        cookie=self.client.get_cookie('radar_session')
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site,'Lax')

    def test_anonymous_requests_do_not_invalidate_login_form(self):
        token=self.token(self.client.get('/login'))
        self.assertEqual(self.client.get('/api/lista_lembretes').status_code,401)
        self.assertEqual(self.client.get('/favicon.ico').status_code,302)
        response=self.client.post('/login',data={'email':'test@example.com','password':TEST_PASSWORD,'csrf_token':token})
        self.assertEqual(response.status_code,302)

    def test_logout_revokes_copied_cookie(self):
        token=self.login()
        stolen=self.client.get_cookie('radar_session').value
        self.assertEqual(self.client.post('/logout',data={'csrf_token':token}).status_code,302)
        other=module.app.test_client()
        other.set_cookie('radar_session',stolen)
        self.assertEqual(other.get('/api/lista_lembretes').status_code,401)

    def test_idle_session_expires(self):
        self.login()
        with closing(auth_connection(module.app)) as db:
            db.execute('UPDATE Sessao SET last_seen=?',(time.time()-1900,))
            db.commit()
        self.assertEqual(self.client.get('/api/lista_lembretes').status_code,401)

    def test_rate_limit(self):
        token=self.token(self.client.get('/login'))
        for _ in range(10):
            response=self.client.post('/login',data={'email':'test@example.com','password':'wrong','csrf_token':token})
            self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.post('/login',data={'email':'test@example.com','password':TEST_PASSWORD,'csrf_token':token}).status_code,429)

    def test_exclusions_require_post_and_csrf(self):
        token=self.login()
        for path in ('/excluir/1','/excluir_vaga/1','/excluir_status/1','/excluir_pasta/1','/excluir_selecionadora/1','/resgatar_limbo'):
            self.assertEqual(self.client.get(path).status_code,405)
            self.assertEqual(self.client.post(path).status_code,400)
        self.assertEqual(self.client.post('/salvar_vaga',data={'nome_vaga':'Security test','csrf_token':token}).status_code,302)
        with closing(module.conectar()) as db:
            row=db.execute('SELECT id FROM Vaga WHERE nome=?',('Security test',)).fetchone()
        self.assertEqual(self.client.post(f'/excluir_vaga/{row[0]}',data={'csrf_token':token}).status_code,302)

    def test_uploads_and_path_escape(self):
        token=self.login()
        with closing(module.conectar()) as db:
            company=db.execute('SELECT id FROM Cliente LIMIT 1').fetchone()[0]
        response=self.client.post('/enviar_mensagem',data={'cliente_id':company,'csrf_token':token,'arquivo':(io.BytesIO(b'<script>bad()</script>'),'bad.html')})
        self.assertEqual(response.status_code,400)
        response=self.client.post('/enviar_mensagem',data={'cliente_id':company,'csrf_token':token,'arquivo':(io.BytesIO(b'<script>bad()</script>'),'fake.png')})
        self.assertEqual(response.status_code,200)
        with closing(module.conectar()) as db:
            path=db.execute('SELECT arquivo_path FROM Mensagem WHERE cliente_id=? AND arquivo_path IS NOT NULL ORDER BY id DESC',(company,)).fetchone()[0]
        download=self.client.get('/static/'+path)
        self.assertIn('attachment',download.headers['Content-Disposition'])
        self.assertEqual(download.mimetype,'application/octet-stream')
        download.close()
        self.assertEqual(self.client.get('/anexos/../app.py').status_code,404)
        self.assertEqual(self.client.get('/static/../app.py').status_code,404)
        self.assertEqual(module.app.test_client().get('/static/'+path).status_code,302)

    def test_password_is_hashed_and_export_safe(self):
        with closing(auth_connection(module.app)) as db:
            stored=db.execute('SELECT password_hash FROM Usuario').fetchone()[0]
        self.assertNotIn(TEST_PASSWORD,stored)
        token=self.login()
        self.client.post('/salvar',data={'nome_cliente':'=HYPERLINK("bad")','csrf_token':token})
        exported=self.client.get('/exportar_relatorio').get_data(as_text=True)
        self.assertIn("'=HYPERLINK",exported)

    def test_untrusted_hosts_and_private_files(self):
        self.assertEqual(self.client.get('/login',headers={'Host':'attacker.example'}).status_code,400)
        self.login()
        for path in ('/static/../instance/access.db','/static/../backups/test.db','/static/style.css'):
            self.assertEqual(self.client.get(path).status_code,404)

    def test_tampered_cookie_cannot_authenticate(self):
        self.login()
        other=module.app.test_client()
        other.set_cookie('radar_session',self.client.get_cookie('radar_session').value+'tampered')
        self.assertEqual(other.get('/api/lista_lembretes').status_code,401)

    def test_https_cookie_and_hsts(self):
        module.app.config['SESSION_COOKIE_SECURE']=True
        try:
            response=self.client.get('/login',base_url='https://localhost')
            self.assertIn('Secure',response.headers['Set-Cookie'])
            self.assertEqual(response.headers['Strict-Transport-Security'],'max-age=31536000')
        finally:
            module.app.config['SESSION_COOKIE_SECURE']=False

    def test_download_current_consistent_database(self):
        self.assertEqual(self.client.get('/backup/banco').status_code,302)
        token=self.login()
        self.client.post('/salvar',data={'nome_cliente':'Backup current snapshot','csrf_token':token})
        with self.client.get('/backup/banco') as response:
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn('attachment;',response.headers['Content-Disposition'])
            self.assertIn('.db',response.headers['Content-Disposition'])
            downloaded=self.root/'downloaded.db'
            downloaded.write_bytes(response.data)
        with closing(sqlite3.connect(downloaded)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertIsNotNone(db.execute('SELECT id FROM Cliente WHERE nome=?',('Backup current snapshot',)).fetchone())
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('Usuario',tables)
            self.assertNotIn('Sessao',tables)


if __name__=='__main__':
    try:
        unittest.main()
    finally:
        temporary.cleanup()
