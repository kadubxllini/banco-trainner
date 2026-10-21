import os
import csv
import io
import sqlite3
import logging
import uuid
import tempfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from contextlib import closing

from flask import Flask, render_template, request, redirect, jsonify, make_response, cli, abort, send_from_directory, send_file
from werkzeug.utils import secure_filename

# ==========================================
# CONFIGURAÇÕES DO APP
# ==========================================
cli.show_server_banner = lambda *args: None
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
app.config['UPLOAD_FOLDER'] = os.environ.get('RADAR_UPLOAD_DIR', str(BASE_DIR / 'static' / 'uploads'))

BANCO_DIR = os.environ.get('RADAR_DATA_DIR', str(BASE_DIR / 'banco_de_dados'))
BANCO_PATH = os.path.join(BANCO_DIR, 'dados.db')

# ==========================================
# BANCO DE DADOS
# ==========================================
def conectar():
    """Retorna a conexão com o SQLite, garantindo que os diretórios existam."""
    os.makedirs(BANCO_DIR, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) 
    conn = sqlite3.connect(BANCO_PATH, timeout=10)
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def upload_path(relative):
    if not relative.startswith('uploads/'):
        abort(404)
    root = Path(app.config['UPLOAD_FOLDER']).resolve()
    candidate = (root / relative.removeprefix('uploads/')).resolve()
    if candidate.parent != root:
        abort(404)
    return candidate


def raster_type(path):
    with open(path, 'rb') as image:
        header = image.read(16)
    if header.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if header.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if header.startswith((b'GIF87a', b'GIF89a')): return 'image/gif'
    if header.startswith(b'RIFF') and header[8:12] == b'WEBP': return 'image/webp'
    return None


@app.get('/anexos/<path:filename>')
def protected_upload(filename):
    path = upload_path('uploads/' + filename)
    if not path.is_file(): abort(404)
    mime = raster_type(path)
    response = send_from_directory(app.config['UPLOAD_FOLDER'], path.name,
                                   mimetype=mime or 'application/octet-stream',
                                   as_attachment=not bool(mime), conditional=False)
    response.headers['Cache-Control'] = 'no-store'
    return response

def criar_tabelas():
    """Inicializa as tabelas e aplica atualizações em bancos legados."""
    conn = conectar()
    
    tabelas_sql = [
        'CREATE TABLE IF NOT EXISTS Pasta (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, parent_id INTEGER REFERENCES Pasta(id) ON DELETE CASCADE)',
        'CREATE TABLE IF NOT EXISTS Vaga (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS Status (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS Selecionadora (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)',
        '''CREATE TABLE IF NOT EXISTS Lembrete (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mensagem_id INTEGER, texto TEXT NOT NULL,
            data_criacao DATETIME DEFAULT (datetime('now', 'localtime')), data_alerta DATETIME NOT NULL, lido INTEGER DEFAULT 0,
            FOREIGN KEY (mensagem_id) REFERENCES Mensagem(id) ON DELETE CASCADE
        )''',
        '''CREATE TABLE IF NOT EXISTS Cliente (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, pasta_id INTEGER,
            urgencia TEXT NOT NULL DEFAULT 'BAIXA', FOREIGN KEY (pasta_id) REFERENCES Pasta(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS Cliente_Vaga (
            cliente_id INTEGER, vaga_id INTEGER, status_id INTEGER, taxa REAL,
            PRIMARY KEY (cliente_id, vaga_id),
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE,
            FOREIGN KEY (vaga_id) REFERENCES Vaga(id) ON DELETE CASCADE,
            FOREIGN KEY (status_id) REFERENCES Status(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS Cliente_Selecionadora (
            cliente_id INTEGER, selecionadora_id INTEGER, PRIMARY KEY (cliente_id, selecionadora_id),
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE,
            FOREIGN KEY (selecionadora_id) REFERENCES Selecionadora(id) ON DELETE CASCADE
        )''',
        '''CREATE TABLE IF NOT EXISTS Mensagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, texto TEXT, arquivo_path TEXT,
            tipo TEXT, data_hora DATETIME DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE
        )''',
        '''CREATE TABLE IF NOT EXISTS Contato (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, nome TEXT, email TEXT, telefone TEXT,
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE
        )'''
    ]
    
    for sql in tabelas_sql:
        conn.execute(sql)
        
    # Migrações para garantir compatibilidade com versões antigas do banco
    migracoes = [
        'ALTER TABLE Cliente ADD COLUMN urgencia TEXT NOT NULL DEFAULT "BAIXA"',
        'ALTER TABLE Pasta ADD COLUMN parent_id INTEGER REFERENCES Pasta(id) ON DELETE CASCADE',
        'ALTER TABLE Cliente_Vaga ADD COLUMN status_id INTEGER REFERENCES Status(id)',
        'ALTER TABLE Cliente_Vaga ADD COLUMN taxa REAL'
    ]
    for sql in migracoes:
        try: conn.execute(sql)
        except sqlite3.OperationalError: pass
        
    conn.commit()
    conn.close()

# ==========================================
# ROTA PRINCIPAL (DASHBOARD)
# ==========================================
@app.route('/')
def index():
    conn = conectar()
    
    # 1. Mapeamento de Pastas
    todas_pastas = conn.execute('SELECT id, nome, parent_id FROM Pasta ORDER BY id DESC').fetchall()
    pastas_principais, pastas_formatadas = [], []
    subpastas = defaultdict(list)
    pastas_dict = {p[0]: p[1] for p in todas_pastas}
    
    for p_id, p_nome, p_parent in todas_pastas:
        if p_parent:
            subpastas[p_parent].append((p_id, p_nome, p_parent))
            pastas_formatadas.append((p_id, f"{pastas_dict.get(p_parent, 'Desconhecida')} > {p_nome}"))
        else:
            pastas_principais.append((p_id, p_nome, p_parent))
            pastas_formatadas.append((p_id, p_nome))

    # 2. Dados Auxiliares
    vagas = conn.execute('SELECT id, nome FROM Vaga ORDER BY nome ASC').fetchall()
    status_lista = conn.execute('SELECT id, nome FROM Status ORDER BY id ASC').fetchall()
    selecionadoras = conn.execute('SELECT id, nome FROM Selecionadora ORDER BY nome ASC').fetchall()
    
    # 3. Clientes e Agrupamentos
    clientes = conn.execute('SELECT id, nome, urgencia, pasta_id, NULL FROM Cliente ORDER BY id DESC').fetchall()
    radar = conn.execute('''
        SELECT c.id, c.nome, COALESCE(p.nome, 'Sem pasta'),
               COALESCE(v.nome, 'Sem vaga'), COALESCE(st.nome, 'Sem etapa'), cv.taxa,
               COALESCE((SELECT GROUP_CONCAT(s.nome, ', ') FROM Cliente_Selecionadora cs
                         JOIN Selecionadora s ON s.id = cs.selecionadora_id WHERE cs.cliente_id = c.id), 'Sem responsável'), cv.vaga_id, cv.status_id
        FROM Cliente c LEFT JOIN Pasta p ON p.id = c.pasta_id
        LEFT JOIN Cliente_Vaga cv ON cv.cliente_id = c.id
        LEFT JOIN Vaga v ON v.id = cv.vaga_id LEFT JOIN Status st ON st.id = cv.status_id
        ORDER BY c.nome COLLATE NOCASE, v.nome COLLATE NOCASE
    ''').fetchall()
    empresas_radar = {}
    for row in radar:
        empresa = empresas_radar.setdefault(row[0], {'id': row[0], 'nome': row[1], 'pasta': row[2], 'responsavel': row[6], 'vagas': []})
        empresa['vagas'].append({'id': row[7], 'nome': row[3], 'status': row[4], 'status_id': row[8], 'taxa': row[5]})
    sem_pasta = []
    por_pasta = defaultdict(list)
    
    for c_id, nome, urgencia, pasta_id, status_id in clientes:
        cli_data = (c_id, nome, urgencia, status_id)
        if pasta_id:
            por_pasta[pasta_id].append(cli_data)
        else:
            sem_pasta.append(cli_data)
            
    # 4. Relacionamentos
    vpe, spe, cpe = defaultdict(list), defaultdict(list), defaultdict(list)
    
    for c_id, v_id, st_id, taxa in conn.execute('SELECT cliente_id, vaga_id, status_id, taxa FROM Cliente_Vaga').fetchall():
        vpe[c_id].append(f"{v_id}:{st_id or ''}:{taxa or ''}")

    for c_id, s_id in conn.execute('SELECT cliente_id, selecionadora_id FROM Cliente_Selecionadora').fetchall():
        spe[c_id].append(s_id)

    for c_id, nome, email, telefone in conn.execute('SELECT cliente_id, nome, email, telefone FROM Contato').fetchall():
        cpe[c_id].append({'nome': nome or '', 'email': email or '', 'telefone': telefone or ''})

    # 5. Lembretes Ativos
    atrasados_db = conn.execute("SELECT DISTINCT c.id FROM Lembrete l JOIN Mensagem m ON l.mensagem_id = m.id JOIN Cliente c ON c.id = m.cliente_id WHERE l.lido = 0 AND l.data_alerta <= datetime('now', 'localtime')").fetchall()
    pendentes_db = conn.execute("SELECT DISTINCT c.id FROM Lembrete l JOIN Mensagem m ON l.mensagem_id = m.id JOIN Cliente c ON c.id = m.cliente_id WHERE l.lido = 0 AND l.data_alerta > datetime('now', 'localtime')").fetchall()
    
    conn.close()
    
    return render_template(
        'index.html', radar=radar, empresas_radar=list(empresas_radar.values()), cliente_pastas={c[0]: c[3] for c in clientes}, todas_pastas_lookup={p[0]: p[2] for p in todas_pastas},
        pastas=pastas_formatadas, pastas_principais=pastas_principais, subpastas=subpastas,
        clientes_sem_pasta=sem_pasta, clientes_por_pasta=por_pasta,
        vagas=vagas, status_lista=status_lista, selecionadoras=selecionadoras,
        vpe=vpe, spe=spe, cpe=cpe,
        clientes_atrasados=[c[0] for c in atrasados_db], clientes_pendentes=[c[0] for c in pendentes_db]
    )

# ==========================================
# CHAT E MENSAGENS
# ==========================================
@app.route('/api/processos/etapa', methods=['POST'])
def atualizar_etapa():
    data = request.get_json(silent=True) or {}
    try:
        cliente_id = int(data['cliente_id'])
        vaga_id = int(data['vaga_id'])
        status_id = int(data['status_id']) if data.get('status_id') else None
    except (ValueError, TypeError, KeyError):
        return jsonify(erro='Dados inválidos.'), 400
    with closing(conectar()) as conn:
        if status_id is not None and not conn.execute('SELECT 1 FROM Status WHERE id=?', (status_id,)).fetchone():
            return jsonify(erro='Etapa não encontrada.'), 400
        cursor = conn.execute('UPDATE Cliente_Vaga SET status_id=? WHERE cliente_id=? AND vaga_id=?', (status_id, cliente_id, vaga_id))
        if not cursor.rowcount:
            return jsonify(erro='Processo não encontrado.'), 404
        conn.commit()
    return jsonify(status='sucesso')

@app.route('/get_mensagens/<int:cliente_id>')
def get_mensagens(cliente_id):
    conn = conectar()
    mensagens = conn.execute('''
        SELECT m.id, m.texto, m.arquivo_path, m.tipo, strftime('%d/%m/%Y %H:%M', m.data_hora),
               (SELECT COUNT(*) FROM Lembrete WHERE mensagem_id = m.id)
        FROM Mensagem m WHERE cliente_id = ? ORDER BY data_hora ASC
    ''', (cliente_id,)).fetchall()
    conn.close()
    return jsonify([{'id': m[0], 'texto': m[1], 'path': m[2], 'tipo': m[3], 'data': m[4], 'tem_lembrete': m[5] > 0} for m in mensagens])

@app.route('/get_arquivos/<int:cliente_id>')
def get_arquivos(cliente_id):
    conn = conectar()
    arquivos = conn.execute('''
        SELECT texto, arquivo_path, tipo, strftime('%d/%m/%Y %H:%M', data_hora) 
        FROM Mensagem WHERE cliente_id = ? AND arquivo_path IS NOT NULL ORDER BY data_hora DESC
    ''', (cliente_id,)).fetchall()
    conn.close()
    return jsonify([{'texto': a[0], 'path': a[1], 'tipo': a[2], 'data': a[3]} for a in arquivos])

@app.route('/api/pesquisar_mensagens')
def pesquisar_mensagens():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    
    conn = conectar()
    resultados = conn.execute('''
        SELECT m.id, m.texto, c.id, c.nome, strftime('%d/%m/%Y %H:%M', m.data_hora) 
        FROM Mensagem m JOIN Cliente c ON m.cliente_id = c.id
        WHERE m.texto LIKE ? ORDER BY m.data_hora DESC LIMIT 50
    ''', (f'%{q}%',)).fetchall()
    conn.close()
    return jsonify([{'msg_id': r[0], 'texto': r[1], 'cliente_id': r[2], 'cliente_nome': r[3], 'data': r[4]} for r in resultados])

@app.route('/enviar_mensagem', methods=['POST'])
def enviar_mensagem():
    cliente_id = request.form.get('cliente_id')
    texto = request.form.get('texto')
    arquivos = request.files.getlist('arquivo')
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    allowed = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.zip'}
    for arquivo in arquivos:
        if arquivo and arquivo.filename and Path(secure_filename(arquivo.filename)).suffix.lower() not in allowed:
            return jsonify(erro='Tipo de arquivo não permitido.'), 400
    conn = conectar()
    if not conn.execute('SELECT id FROM Cliente WHERE id=?', (cliente_id,)).fetchone():
        conn.close()
        return jsonify(erro='Empresa não encontrada.'), 404
    if texto and texto.strip():
        conn.execute('INSERT INTO Mensagem (cliente_id, texto, tipo, data_hora) VALUES (?, ?, ?, ?)', (cliente_id, texto, 'texto', agora))

    for arquivo in arquivos:
        if arquivo and arquivo.filename:
            nome_seguro = secure_filename(arquivo.filename)
            filename = f"{uuid.uuid4().hex}_{nome_seguro}"
            arquivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            tipo = 'imagem' if os.path.splitext(filename)[1].lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp'] else 'arquivo'
            conn.execute('INSERT INTO Mensagem (cliente_id, arquivo_path, tipo, data_hora) VALUES (?, ?, ?, ?)', (cliente_id, f"uploads/{filename}", tipo, agora))

    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/editar_mensagem/<int:id>', methods=['POST'])
def editar_mensagem(id):
    texto = request.form.get('texto')
    if texto is not None:
        conn = conectar()
        conn.execute('UPDATE Mensagem SET texto = ? WHERE id = ?', (texto, id))
        conn.commit()
        conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/excluir_mensagem/<int:id>', methods=['POST'])
def excluir_mensagem(id):
    conn = conectar()
    msg = conn.execute('SELECT arquivo_path FROM Mensagem WHERE id = ?', (id,)).fetchone()
    if msg and msg[0]:
        caminho = upload_path(msg[0])
        if caminho.is_file(): caminho.unlink()
            
    conn.execute('DELETE FROM Mensagem WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

# ==========================================
# CLIENTES (EMPRESAS)
# ==========================================
@app.route('/salvar', methods=['POST'])
def salvar():
    nome = request.form.get('nome_cliente', '').strip()
    if not nome: return redirect('/')
    
    conn = conectar()
    if conn.execute('SELECT id FROM Cliente WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone():
        conn.close()
        return redirect('/') 
        
    cursor = conn.cursor()
    cursor.execute('INSERT INTO Cliente (nome, pasta_id, urgencia) VALUES (?, ?, ?)', (nome, request.form.get('pasta_id') or None, 'BAIXA'))
    c_id = cursor.lastrowid
    
    v_ids = request.form.getlist('vagas_ids')
    if v_ids:
        vagas_dados = [(c_id, v, request.form.get(f'status_vaga_{v}') or None, request.form.get(f'taxa_vaga_{v}') or None) for v in v_ids]
        cursor.executemany('INSERT INTO Cliente_Vaga (cliente_id, vaga_id, status_id, taxa) VALUES (?, ?, ?, ?)', vagas_dados)
        
    s_ids = request.form.getlist('selecionadoras_ids')
    if s_ids: 
        cursor.executemany('INSERT INTO Cliente_Selecionadora (cliente_id, selecionadora_id) VALUES (?, ?)', [(c_id, s) for s in s_ids])
        
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/editar/<int:id>', methods=['POST'])
def editar(id):
    nome = request.form.get('nome_cliente', '').strip()
    conn = conectar()
    if conn.execute('SELECT id FROM Cliente WHERE LOWER(nome) = LOWER(?) AND id != ?', (nome, id)).fetchone():
        conn.close()
        return redirect('/') 

    conn.execute('UPDATE Cliente SET nome = ?, pasta_id = ?, urgencia = ? WHERE id = ?', (nome, request.form.get('pasta_id') or None, 'BAIXA', id))
    
    conn.execute('DELETE FROM Cliente_Vaga WHERE cliente_id = ?', (id,))
    v_ids = request.form.getlist('vagas_ids')
    if v_ids:
        vagas_dados = [(id, v, request.form.get(f'status_vaga_{v}') or None, request.form.get(f'taxa_vaga_{v}') or None) for v in v_ids]
        conn.executemany('INSERT INTO Cliente_Vaga (cliente_id, vaga_id, status_id, taxa) VALUES (?, ?, ?, ?)', vagas_dados)
    
    conn.execute('DELETE FROM Cliente_Selecionadora WHERE cliente_id = ?', (id,))
    s_ids = request.form.getlist('selecionadoras_ids')
    if s_ids: 
        conn.executemany('INSERT INTO Cliente_Selecionadora (cliente_id, selecionadora_id) VALUES (?, ?)', [(id, s) for s in s_ids])

    conn.execute('DELETE FROM Contato WHERE cliente_id = ?', (id,))
    contatos = zip(request.form.getlist('contato_nome[]'), request.form.getlist('contato_email[]'), request.form.getlist('contato_telefone[]'))
    for n, e, t in contatos:
        if n.strip() or e.strip() or t.strip():
            conn.execute('INSERT INTO Contato (cliente_id, nome, email, telefone) VALUES (?, ?, ?, ?)', (id, n, e, t))
        
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/excluir/<int:id>', methods=['POST'])
def excluir(id):
    conn = conectar()
    conn.execute('DELETE FROM Cliente WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

# ==========================================
# GESTÃO DE PASTAS E ATRIBUTOS (VAGA, STATUS, ETC)
# ==========================================
def gerenciar_entidade_simples(tabela, acao, id=None, nome=None, parent_id=None):
    """Função genérica para reduzir a repetição no CRUD de Vaga, Status e Selecionadora."""
    if tabela not in {'Vaga', 'Status', 'Selecionadora'}:
        abort(400)
    conn = conectar()
    if acao == 'salvar' and nome:
        if not conn.execute(f'SELECT id FROM {tabela} WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone():
            conn.execute(f'INSERT INTO {tabela} (nome) VALUES (?)', (nome,))
    elif acao == 'editar' and nome and id:
        if not conn.execute(f'SELECT id FROM {tabela} WHERE LOWER(nome) = LOWER(?) AND id != ?', (nome, id)).fetchone():
            conn.execute(f'UPDATE {tabela} SET nome = ? WHERE id = ?', (nome, id))
    elif acao == 'excluir' and id:
        if tabela == 'Status': conn.execute('UPDATE Cliente_Vaga SET status_id = NULL WHERE status_id = ?', (id,))
        conn.execute(f'DELETE FROM {tabela} WHERE id = ?', (id,))
    conn.commit()
    conn.close()

# VAGAS
@app.route('/salvar_vaga', methods=['POST'])
def salvar_vaga(): gerenciar_entidade_simples('Vaga', 'salvar', nome=request.form.get('nome_vaga', '').strip()); return redirect('/')
@app.route('/editar_vaga/<int:id>', methods=['POST'])
def editar_vaga(id): gerenciar_entidade_simples('Vaga', 'editar', id, nome=request.form.get('nome_vaga', '').strip()); return redirect('/')
@app.route('/excluir_vaga/<int:id>', methods=['POST'])
def excluir_vaga(id): gerenciar_entidade_simples('Vaga', 'excluir', id); return redirect('/')

# STATUS
@app.route('/salvar_status', methods=['POST'])
def salvar_status(): gerenciar_entidade_simples('Status', 'salvar', nome=request.form.get('nome_status', '').strip()); return redirect('/')
@app.route('/editar_status/<int:id>', methods=['POST'])
def editar_status(id): gerenciar_entidade_simples('Status', 'editar', id, nome=request.form.get('nome_status', '').strip()); return redirect('/')
@app.route('/excluir_status/<int:id>', methods=['POST'])
def excluir_status(id): gerenciar_entidade_simples('Status', 'excluir', id); return redirect('/')

# SELECIONADORAS
@app.route('/salvar_selecionadora', methods=['POST'])
def salvar_selecionadora(): gerenciar_entidade_simples('Selecionadora', 'salvar', nome=request.form.get('nome_selecionadora', '').strip()); return redirect('/')
@app.route('/editar_selecionadora/<int:id>', methods=['POST'])
def editar_selecionadora(id): gerenciar_entidade_simples('Selecionadora', 'editar', id, nome=request.form.get('nome_selecionadora', '').strip()); return redirect('/')
@app.route('/excluir_selecionadora/<int:id>', methods=['POST'])
def excluir_selecionadora(id): gerenciar_entidade_simples('Selecionadora', 'excluir', id); return redirect('/')

# PASTAS (Contém lógica de hierarquia, não usa função genérica)
@app.route('/salvar_pasta', methods=['POST'])
def salvar_pasta():
    nome, parent_id = request.form.get('nome_pasta', '').strip(), request.form.get('parent_id') or None
    if nome:
        conn = conectar()
        if not parent_id and conn.execute('SELECT id FROM Pasta WHERE LOWER(nome) = LOWER(?) AND parent_id IS NULL', (nome,)).fetchone():
            return redirect('/') 
        conn.execute('INSERT INTO Pasta (nome, parent_id) VALUES (?, ?)', (nome, parent_id))
        conn.commit()
        conn.close()
    return redirect('/')

@app.route('/editar_pasta/<int:id>', methods=['POST'])
def editar_pasta(id):
    nome, parent_id = request.form.get('nome_pasta', '').strip(), request.form.get('parent_id') or None
    if str(parent_id) == str(id): parent_id = None
    if nome:
        conn = conectar()
        if not parent_id and conn.execute('SELECT id FROM Pasta WHERE LOWER(nome) = LOWER(?) AND parent_id IS NULL AND id != ?', (nome, id)).fetchone():
            return redirect('/') 
        conn.execute('UPDATE Pasta SET nome = ?, parent_id = ? WHERE id = ?', (nome, parent_id, id))
        conn.commit()
        conn.close()
    return redirect('/')

@app.route('/excluir_pasta/<int:id>', methods=['POST'])
def excluir_pasta(id):
    conn = conectar()
    conn.execute('UPDATE Cliente SET pasta_id = NULL WHERE pasta_id = ?', (id,))
    conn.execute('UPDATE Pasta SET parent_id = NULL WHERE parent_id = ?', (id,))
    conn.execute('DELETE FROM Pasta WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/resgatar_limbo', methods=['POST'])
def resgatar_limbo():
    conn = conectar()
    conn.execute('UPDATE Pasta SET parent_id = NULL WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT id FROM Pasta)')
    conn.commit()
    conn.close()
    return redirect('/')

# ==========================================
# LEMBRETES E INTERAÇÕES
# ==========================================
@app.route('/api/criar_lembrete', methods=['POST'])
def criar_lembrete():
    texto = request.form.get('texto')
    mensagem_id = request.form.get('mensagem_id')
    data_alerta = request.form.get('data_alerta').replace('T', ' ') + ':00'
    
    conn = conectar()
    if conn.execute('SELECT id FROM Lembrete WHERE mensagem_id = ? AND lido = 0', (mensagem_id,)).fetchone():
        conn.close()
        return jsonify({'status': 'erro', 'mensagem': 'Essa mensagem já possui um lembrete pendente!'})
        
    conn.execute('INSERT INTO Lembrete (mensagem_id, texto, data_alerta) VALUES (?, ?, ?)', (mensagem_id, texto, data_alerta))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/api/lembrete_pendente')
def lembrete_pendente():
    conn = conectar()
    res = conn.execute('''
        SELECT l.id, l.texto, c.nome FROM Lembrete l JOIN Mensagem m ON l.mensagem_id = m.id JOIN Cliente c ON m.cliente_id = c.id
        WHERE l.lido = 0 AND l.data_alerta <= ? ORDER BY l.data_alerta ASC LIMIT 1
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),)).fetchone()
    conn.close()
    return jsonify({'id': res[0], 'texto': res[1], 'empresa': res[2]}) if res else jsonify(None)

@app.route('/api/lista_lembretes')
def lista_lembretes():
    conn = conectar()
    lembretes = conn.execute('''
        SELECT l.id, l.texto, strftime('%d/%m/%Y %H:%M', l.data_alerta), l.lido, c.nome,
               CASE WHEN l.data_alerta <= datetime('now', 'localtime') AND l.lido = 0 THEN 1 ELSE 0 END
        FROM Lembrete l JOIN Mensagem m ON l.mensagem_id = m.id JOIN Cliente c ON m.cliente_id = c.id
        ORDER BY l.lido ASC, l.data_alerta DESC
    ''').fetchall()
    conn.close()
    return jsonify([{'id': l[0], 'texto': l[1], 'data': l[2], 'lido': bool(l[3]), 'empresa': l[4], 'vencido': bool(l[5])} for l in lembretes])

@app.route('/api/marcar_lembrete_lido/<int:id>', methods=['POST'])
def marcar_lembrete_lido(id):
    conn = conectar()
    conn.execute('UPDATE Lembrete SET lido = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/api/dias_com_interacao')
def dias_com_interacao():
    conn = conectar()
    datas = conn.execute("SELECT DISTINCT date(data_hora) FROM Mensagem").fetchall()
    conn.close()
    return jsonify([d[0] for d in datas if d[0]])

@app.route('/api/interacoes_dia/<data>')
def interacoes_dia(data):
    conn = conectar()
    clientes = conn.execute("SELECT DISTINCT c.id, c.nome FROM Mensagem m JOIN Cliente c ON m.cliente_id = c.id WHERE date(m.data_hora) = ?", (data,)).fetchall()
    conn.close()
    return jsonify([{'id': c[0], 'nome': c[1]} for c in clientes])

@app.route('/get_contatos/<int:cliente_id>')
def get_contatos(cliente_id):
    conn = conectar()
    contatos = conn.execute('SELECT nome, email, telefone FROM Contato WHERE cliente_id = ?', (cliente_id,)).fetchall()
    conn.close()
    return jsonify([{'nome': c[0], 'email': c[1], 'telefone': c[2]} for c in contatos])

@app.route('/api/cliente_tags/<int:cliente_id>')
def api_cliente_tags(cliente_id):
    conn = conectar()
    vagas_bd = conn.execute('''
        SELECT v.nome, s.nome, cv.taxa FROM Cliente_Vaga cv 
        JOIN Vaga v ON cv.vaga_id = v.id LEFT JOIN Status s ON cv.status_id = s.id 
        WHERE cv.cliente_id = ?
    ''', (cliente_id,)).fetchall()
    
    tags_vagas = []
    for v_nome, s_nome, taxa in vagas_bd:
        partes = [p for p in (s_nome, f"{taxa}%" if taxa else None) if p]
        tags_vagas.append({'texto': f"{v_nome} ({' - '.join(partes)})" if partes else v_nome, 'status': s_nome.upper() if s_nome else ''})
            
    sels = conn.execute('SELECT s.nome FROM Selecionadora s JOIN Cliente_Selecionadora cs ON s.id = cs.selecionadora_id WHERE cs.cliente_id = ?', (cliente_id,)).fetchall()
    conn.close()
    return jsonify({'status': '', 'vagas': tags_vagas, 'selecionadoras': [s[0] for s in sels]})

# ==========================================
# EXPORTAÇÃO
# ==========================================
@app.route('/exportar_relatorio')
def exportar_relatorio():
    conn = conectar()
    dados = conn.execute('''
        SELECT IFNULL(p.nome, 'Sem Pasta'), c.nome, IFNULL(v.nome, 'Sem Vaga'), IFNULL(st.nome, ''), cv.taxa,
               (SELECT GROUP_CONCAT(sel.nome, ', ') FROM Selecionadora sel JOIN Cliente_Selecionadora cs ON sel.id = cs.selecionadora_id WHERE cs.cliente_id = c.id),
               (SELECT GROUP_CONCAT(ct.nome, ', ') FROM Contato ct WHERE ct.cliente_id = c.id),
               (SELECT GROUP_CONCAT(ct.email, ', ') FROM Contato ct WHERE ct.cliente_id = c.id),
               (SELECT GROUP_CONCAT(ct.telefone, ', ') FROM Contato ct WHERE ct.cliente_id = c.id)
        FROM Cliente c
        LEFT JOIN Pasta p ON c.pasta_id = p.id
        LEFT JOIN Cliente_Vaga cv ON c.id = cv.cliente_id
        LEFT JOIN Vaga v ON cv.vaga_id = v.id
        LEFT JOIN Status st ON cv.status_id = st.id
        ORDER BY p.nome ASC, c.nome ASC, v.nome ASC
    ''').fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['PASTA', 'EMPRESA', 'VAGA', 'STATUS', 'TAXA', 'SELECIONADORA', 'C-NOME', 'C-EMAIL', 'C-TELEFONE'])
    
    for linha in dados:
        linha_formatada = [str(item) if item is not None else '' for item in linha]
        if linha_formatada[4]: linha_formatada[4] += '%'
        writer.writerow(["'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value for value in linha_formatada])
    
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=relatorio_clientes_{datetime.now().strftime('%d_%m_%Y')}.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    return response

@app.get('/backup/banco')
def baixar_backup():
    # SQLite backup API produces a consistent snapshot even during concurrent writes.
    # The private temporary file is removed before the response is sent.
    with tempfile.TemporaryDirectory(prefix='radar-download-') as directory:
        snapshot = Path(directory) / 'dados.db'
        with closing(sqlite3.connect(Path(BANCO_PATH).resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination, pages=256, sleep=0.05)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    abort(500, 'Não foi possível gerar um backup válido.')
        content = io.BytesIO(snapshot.read_bytes())
    name = 'RADAR_banco_' + datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.db'
    response = send_file(content, mimetype='application/octet-stream', as_attachment=True,
                         download_name=name, conditional=False, max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    return response


from security import install_security
install_security(app)

if __name__ == '__main__':
    criar_tabelas()
    print(" * Rodando localmente em http://127.0.0.1:5000")
    app.run()
