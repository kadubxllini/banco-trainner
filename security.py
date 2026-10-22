"""Authentication, revocable sessions and request protection for RADAR."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from flask import abort, jsonify, redirect, render_template, request, session, g
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix


def auth_connection(app):
    conn = sqlite3.connect(app.config['AUTH_DB_PATH'], timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def create_access(app, email, password, nome=None):
    if not 12 <= len(password) <= 1024:
        raise ValueError('Use uma senha entre 12 e 1024 caracteres.')
    with closing(auth_connection(app)) as conn:
        email = email.strip().lower()
        nome = nome or ('Trainner' if email == 'suportevendas@trainner.com.br' else email.split('@')[0].capitalize())
        conn.execute('INSERT INTO Usuario(email, password_hash, nome) VALUES (?, ?, ?) '
                     'ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash,nome=excluded.nome',
                     (email, generate_password_hash(password), nome))
        conn.execute('DELETE FROM Sessao WHERE usuario_id=(SELECT id FROM Usuario WHERE email=?)', (email,))
        conn.commit()


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def install_security(app):
    if os.environ.get('RADAR_PROXY') == '1':
        # Only enable behind the local Nginx, which overwrites both headers.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    instance = Path(os.environ.get('RADAR_INSTANCE_PATH', Path(app.root_path) / 'instance'))
    instance.mkdir(mode=0o700, parents=True, exist_ok=True)
    key_path = instance / 'session.key'
    if not key_path.exists():
        try:
            with key_path.open('x', encoding='ascii') as handle:
                handle.write(secrets.token_hex(32))
            key_path.chmod(0o600)
        except FileExistsError:
            pass
    app.config.update(
        SECRET_KEY=key_path.read_text(encoding='ascii').strip(),
        AUTH_DB_PATH=str(instance / 'access.db'),
        SESSION_COOKIE_NAME='radar_session',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('RADAR_HTTPS') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
        MAX_FORM_PARTS=1200,
        MAX_FORM_MEMORY_SIZE=256 * 1024,
        TRUSTED_HOSTS=['localhost', '127.0.0.1', '[::1]'],
    )
    if os.environ.get('RADAR_TRUSTED_HOSTS'):
        app.config['TRUSTED_HOSTS'] = os.environ['RADAR_TRUSTED_HOSTS'].split(',')
    with closing(auth_connection(app)) as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS Usuario (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS Sessao (
                token TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, expires REAL NOT NULL, last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS Tentativa (ip TEXT NOT NULL, email TEXT NOT NULL, momento REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS tentativas_momento ON Tentativa(momento);
        ''')
        if 'nome' not in {r[1] for r in conn.execute('PRAGMA table_info(Usuario)')}:
            conn.execute('ALTER TABLE Usuario ADD COLUMN nome TEXT')
        conn.execute("UPDATE Usuario SET nome='Trainner' WHERE email='suportevendas@trainner.com.br' AND (nome IS NULL OR nome='')")
        conn.commit()
    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.context_processor
    def signed_in_user():
        return {'current_user': getattr(g, 'current_user', None)}

    def json_request():
        return (request.is_json or request.path.startswith(('/api/', '/get_')) or
                request.headers.get('X-Requested-With') == 'XMLHttpRequest')

    @app.before_request
    def protect_request():
        g.current_user = None
        if request.routing_exception and request.routing_exception.code == 400:
            raise request.routing_exception
        if request.endpoint == 'static':
            filename = (request.view_args or {}).get('filename', '')
            public = {'radar.css', 'login.css', 'security.js', 'legacy.js', 'radar.js', 'calendar.js', 'daily-report.js', 'modals.js',
                      'img/logo_clara.png', 'img/logo_escura.png', 'img/logosite.png'}
            if filename in public:
                return None
        if request.endpoint != 'login':
            token = session.get('sid')
            valid = False
            if token:
                with closing(auth_connection(app)) as conn:
                    now = time.time()
                    record = conn.execute('SELECT s.*,u.email,u.nome FROM Sessao s JOIN Usuario u ON u.id=s.usuario_id WHERE token=?',
                                          (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
                    if record and record['expires'] > now and record['last_seen'] > now - 1800:
                        valid = True
                        g.current_user = {'email': record['email'], 'nome': record['nome'] or record['email'].split('@')[0].capitalize()}
                        conn.execute('UPDATE Sessao SET last_seen=? WHERE token=?', (now, record['token']))
                        conn.commit()
            if not valid:
                if token:
                    session.clear()
                if json_request():
                    return jsonify(erro='Sua sessão expirou. Entre novamente.'), 401
                return redirect('/login')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            received = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token', '')
            expected = session.get('csrf', '')
            if not expected or not isinstance(received, str) or not hmac.compare_digest(expected, received):
                if json_request():
                    return jsonify(erro='Sessão inválida. Atualize a página.'), 400
                abort(400, 'Sessão inválida. Atualize a página.')
        if request.endpoint == 'static':
            # Downloads are handled separately; arbitrary static files are not public.
            filename = (request.view_args or {}).get('filename', '')
            if filename.startswith('uploads/'):
                return app.view_functions['protected_upload'](filename.removeprefix('uploads/'))
            abort(404)

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        # Inline handlers are retained for the legacy UI; user content is escaped separately.
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'")
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        status = 200
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()[:254]
            password = request.form.get('password', '')[:1024]
            ip = hmac.new(app.secret_key.encode(), (request.remote_addr or '').encode(), hashlib.sha256).hexdigest()
            now = time.time()
            with closing(auth_connection(app)) as conn:
                conn.execute('DELETE FROM Tentativa WHERE momento<?', (now - 900,))
                conn.execute('DELETE FROM Sessao WHERE expires<? OR last_seen<?', (now, now - 1800))
                ip_count = conn.execute('SELECT COUNT(*) FROM Tentativa WHERE ip=?', (ip,)).fetchone()[0]
                account_count = conn.execute('SELECT COUNT(*) FROM Tentativa WHERE email=?', (email,)).fetchone()[0]
                if ip_count >= 10 or account_count >= 30:
                    conn.commit()
                    response = make_login_response('Muitas tentativas. Aguarde 15 minutos e tente novamente.', 429)
                    response.headers['Retry-After'] = '900'
                    return response
                # Record before hashing, so concurrent attempts also count.
                conn.execute('INSERT INTO Tentativa VALUES (?, ?, ?)', (ip, email, now))
                conn.commit()
                user = conn.execute('SELECT * FROM Usuario WHERE email=?', (email,)).fetchone()
                comparison = user or conn.execute('SELECT * FROM Usuario LIMIT 1').fetchone()
                password_ok = bool(comparison and check_password_hash(comparison['password_hash'], password))
                if user and password_ok:
                    session.clear()
                    sid = secrets.token_urlsafe(32)
                    conn.execute('INSERT INTO Sessao VALUES (?, ?, ?, ?)',
                                 (hashlib.sha256(sid.encode()).hexdigest(), user['id'], now + 28800, now))
                    conn.execute('DELETE FROM Tentativa WHERE ip=? AND email=?', (ip, email))
                    conn.commit()
                    session['sid'] = sid
                    session['csrf'] = secrets.token_urlsafe(32)
                    session.permanent = True
                    return redirect('/')
                error, status = 'E-mail ou senha inválidos.', 401
        return make_login_response(error, status)

    def make_login_response(error, status):
        from flask import make_response
        return make_response(render_template('login.html', error=error), status)

    @app.post('/logout')
    def logout():
        sid = session.get('sid', '')
        with closing(auth_connection(app)) as conn:
            conn.execute('DELETE FROM Sessao WHERE token=?', (hashlib.sha256(sid.encode()).hexdigest(),))
            conn.commit()
        session.clear()
        return redirect('/login')
