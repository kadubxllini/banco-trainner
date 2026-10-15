"""Validate the RADAR against a disposable database copy."""
import sqlite3
import tempfile
import os
import re
from pathlib import Path
from contextlib import closing

with tempfile.TemporaryDirectory() as temporary:
    os.environ['RADAR_INSTANCE_PATH'] = str(Path(temporary) / 'auth')
    import app as module
    from security import create_access
    create_access(module.app, 'validation@example.com', 'Validation-only-password!')
    source = sqlite3.connect('file:banco_de_dados/dados.db?mode=ro', uri=True)
    target = sqlite3.connect(str(Path(temporary) / 'dados.db'))
    source.backup(target)
    source.close()
    target.close()
    module.BANCO_DIR = temporary
    module.BANCO_PATH = str(Path(temporary) / 'dados.db')
    module.app.config['UPLOAD_FOLDER'] = str(Path(temporary) / 'uploads')
    module.criar_tabelas()
    client = module.app.test_client()
    login_page = client.get('/login').get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([^"]+)"', login_page)[1]
    assert client.post('/login', data={'email': 'validation@example.com', 'password':'Validation-only-password!', 'csrf_token':token}).status_code == 302
    token = re.search(r'name="csrf-token" content="([^"]+)"', client.get('/').get_data(as_text=True))[1]
    client.environ_base['HTTP_X_CSRF_TOKEN'] = token
    response = client.get('/')
    assert response.status_code == 200
    assert b'radarRows' in response.data
    assert client.get('/exportar_relatorio').status_code == 200
    assert client.post('/salvar', data={'nome_cliente': 'Validação RADAR'}).status_code == 302
    assert 'Validação RADAR' in client.get('/').get_data(as_text=True)
    assert client.post('/api/processos/etapa', json={}).status_code == 400
    with closing(module.conectar()) as db:
        pair = db.execute('SELECT cliente_id,vaga_id FROM Cliente_Vaga LIMIT 1').fetchone()
        stage = db.execute('SELECT id FROM Status LIMIT 1').fetchone()
    if pair and stage:
        assert client.post('/api/processos/etapa', json={'cliente_id': pair[0], 'vaga_id': pair[1], 'status_id': stage[0]}).status_code == 200
        assert client.post('/api/processos/etapa', json={'cliente_id': pair[0], 'vaga_id': pair[1], 'status_id': -99}).status_code == 400
        assert client.post('/api/processos/etapa', json={'cliente_id': -99, 'vaga_id': pair[1]}).status_code == 404
    Path('outputs').mkdir(exist_ok=True)
    Path('outputs/radar-preview.html').write_bytes(response.data)
    print('OK: rendering, CSV, company creation, stage changes and invalid input on a disposable copy.')
