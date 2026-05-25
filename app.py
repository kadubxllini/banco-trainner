from flask import Flask, render_template, request, redirect, jsonify
from werkzeug.utils import secure_filename
from collections import defaultdict
from datetime import datetime, timedelta
import sqlite3
import os
import logging
from flask import cli
import csv
import io
from flask import Flask, render_template, request, redirect, jsonify, make_response

# Desativa o banner de inicialização ("Serving Flask app", "Debug mode")
cli.show_server_banner = lambda *args: None

# Desativa as mensagens padrão do terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
BANCO_DIR = 'banco_de_dados'
BANCO_PATH = os.path.join(BANCO_DIR, 'dados.db')
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- FUNÇÕES DE BANCO DE DADOS ---
def conectar():
    """Garante a criação das pastas e retorna a conexão com o SQLite."""
    os.makedirs(BANCO_DIR, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
    return sqlite3.connect(BANCO_PATH)

def criar_tabelas():
    """Cria todas as tabelas e relacionamentos necessários se não existirem."""
    conn = conectar()
    
    tabelas_sql = [
        'CREATE TABLE IF NOT EXISTS Pasta (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, parent_id INTEGER, FOREIGN KEY (parent_id) REFERENCES Pasta(id) ON DELETE CASCADE)',
        'CREATE TABLE IF NOT EXISTS Vaga (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS Status (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS Selecionadora (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL)',
        '''CREATE TABLE IF NOT EXISTS Lembrete (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mensagem_id INTEGER,
            texto TEXT NOT NULL,
            data_criacao DATETIME DEFAULT (datetime('now', 'localtime')),
            data_alerta DATETIME NOT NULL,
            lido INTEGER DEFAULT 0,
            FOREIGN KEY (mensagem_id) REFERENCES Mensagem(id) ON DELETE CASCADE
        )''',
        '''CREATE TABLE IF NOT EXISTS Cliente (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nome TEXT NOT NULL, 
            pasta_id INTEGER,
            urgencia TEXT NOT NULL DEFAULT 'BAIXA',
            FOREIGN KEY (pasta_id) REFERENCES Pasta(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS Cliente_Vaga (
            cliente_id INTEGER,
            vaga_id INTEGER,
            status_id INTEGER,
            PRIMARY KEY (cliente_id, vaga_id),
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE,
            FOREIGN KEY (vaga_id) REFERENCES Vaga(id) ON DELETE CASCADE,
            FOREIGN KEY (status_id) REFERENCES Status(id)
        )''',
        '''CREATE TABLE IF NOT EXISTS Cliente_Selecionadora (
            cliente_id INTEGER,
            selecionadora_id INTEGER,
            PRIMARY KEY (cliente_id, selecionadora_id),
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE,
            FOREIGN KEY (selecionadora_id) REFERENCES Selecionadora(id) ON DELETE CASCADE
        )''',
        '''CREATE TABLE IF NOT EXISTS Mensagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            texto TEXT,
            arquivo_path TEXT,
            tipo TEXT,
            data_hora DATETIME DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE
        )''',
        '''CREATE TABLE IF NOT EXISTS Contato (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            nome TEXT,
            email TEXT,
            telefone TEXT,
            FOREIGN KEY (cliente_id) REFERENCES Cliente(id) ON DELETE CASCADE
        )'''
    ]
    
    for sql in tabelas_sql:
        conn.execute(sql)
        
    # Garante que a coluna urgencia exista em bancos antigos (Evita erro de OperationalError)
    try:
        conn.execute('ALTER TABLE Cliente ADD COLUMN urgencia TEXT NOT NULL DEFAULT "BAIXA"')
    except sqlite3.OperationalError:
        pass
    # Atualiza tabela antiga de Pasta para aceitar subpastas
    try:
        conn.execute('ALTER TABLE Pasta ADD COLUMN parent_id INTEGER REFERENCES Pasta(id) ON DELETE CASCADE')
    except sqlite3.OperationalError:
        pass
    # Atualiza a tabela Cliente_Vaga antiga para aceitar o status por vaga
    try:
        conn.execute('ALTER TABLE Cliente_Vaga ADD COLUMN status_id INTEGER REFERENCES Status(id)')
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute('ALTER TABLE Cliente_Vaga ADD COLUMN taxa REAL')
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

# --- ROTA PRINCIPAL ---
@app.route('/')
def index():
    conn = conectar()
    
    # 1. Pastas: Ordenadas por ID decrescente (mais novas no topo)
    todas_pastas = conn.execute('SELECT id, nome, parent_id FROM Pasta ORDER BY id DESC').fetchall()
    
    pastas_principais = []
    subpastas = defaultdict(list)
    pastas_dict = {p[0]: p[1] for p in todas_pastas}
    pastas_formatadas = [] 
    
    for p in todas_pastas:
        p_id, p_nome, p_parent = p
        if p_parent:
            subpastas[p_parent].append(p)
            nome_mae = pastas_dict.get(p_parent, "Desconhecida")
            pastas_formatadas.append((p_id, f"{nome_mae} > {p_nome}"))
        else:
            pastas_principais.append(p)
            pastas_formatadas.append((p_id, p_nome))

    # 2. Dados base
    vagas = conn.execute('SELECT id, nome FROM Vaga ORDER BY nome ASC').fetchall()
    status_lista = conn.execute('SELECT id, nome FROM Status ORDER BY id ASC').fetchall()
    selecionadoras = conn.execute('SELECT id, nome FROM Selecionadora ORDER BY nome ASC').fetchall()
    
    # 3. Clientes: MUDANÇA AQUI -> ORDER BY id DESC (mais novos no topo)
    todas_clientes = conn.execute('SELECT id, nome, urgencia, pasta_id, status_id FROM Cliente ORDER BY id DESC').fetchall()
    
    sem_pasta = []
    por_pasta = defaultdict(list)
    
    for cli in todas_clientes:
        e_id, nome, urgencia, pasta_id, status_id = cli
        cli_data = (e_id, nome, urgencia, status_id)
        
        if pasta_id:
            por_pasta[pasta_id].append(cli_data)
        else:
            sem_pasta.append(cli_data)
            
    # 4. Relacionamentos e Contatos
    vpe = defaultdict(list)
    spe = defaultdict(list)
    cpe = defaultdict(list)
    
    for e_id, v_id, st_id, taxa in conn.execute('SELECT cliente_id, vaga_id, status_id, taxa FROM Cliente_Vaga').fetchall():
        vpe[e_id].append(f"{v_id}:{st_id or ''}:{taxa or ''}")

    for e_id, s_id in conn.execute('SELECT cliente_id, selecionadora_id FROM Cliente_Selecionadora').fetchall():
        spe[e_id].append(s_id)

    contatos_bd = conn.execute('SELECT cliente_id, nome, email, telefone FROM Contato').fetchall()
    for c in contatos_bd:
        cpe[c[0]].append({'nome': c[1] or '', 'email': c[2] or '', 'telefone': c[3] or ''})

    atrasados_db = conn.execute('''
        SELECT DISTINCT m.cliente_id FROM Lembrete l
        JOIN Mensagem m ON l.mensagem_id = m.id
        WHERE l.lido = 0 AND l.data_alerta <= datetime('now', 'localtime')
    ''').fetchall()
    atrasados = [c[0] for c in atrasados_db]
    pendentes_db = conn.execute('''
        SELECT DISTINCT m.cliente_id FROM Lembrete l
        JOIN Mensagem m ON l.mensagem_id = m.id
        WHERE l.lido = 0 AND l.data_alerta > datetime('now', 'localtime')
    ''').fetchall()
    pendentes = [c[0] for c in pendentes_db]

    conn.close()
    
    return render_template(
        'index.html',
        pastas=pastas_formatadas,
        pastas_principais=pastas_principais,
        subpastas=subpastas,
        clientes_sem_pasta=sem_pasta,
        clientes_por_pasta=por_pasta,
        vagas=vagas,
        status_lista=status_lista,
        selecionadoras=selecionadoras,
        vpe=vpe,
        spe=spe,
        cpe=cpe,
        clientes_atrasados=atrasados,
        clientes_pendentes=pendentes
    )

# --- ROTAS DO CALENDÁRIO ---
@app.route('/api/dias_com_interacao')
def dias_com_interacao():
    conn = conectar()
    datas = conn.execute("SELECT DISTINCT date(data_hora) FROM Mensagem").fetchall()
    conn.close()
    return jsonify([d[0] for d in datas if d[0]])

@app.route('/api/interacoes_dia/<data>')
def interacoes_dia(data):
    conn = conectar()
    query = '''
        SELECT DISTINCT e.id, e.nome 
        FROM Mensagem m
        JOIN Cliente e ON m.cliente_id = e.id
        WHERE date(m.data_hora) = ?
    '''
    clientes = conn.execute(query, (data,)).fetchall()
    conn.close()
    return jsonify([{'id': e[0], 'nome': e[1]} for e in clientes])

# --- ROTAS DO CHAT E MENSAGENS ---
@app.route('/get_mensagens/<int:cliente_id>')
def get_mensagens(cliente_id):
    conn = conectar()
    # Adicionamos o 'id' no SELECT
    mensagens = conn.execute('''
        SELECT m.id, m.texto, m.arquivo_path, m.tipo, strftime('%d/%m/%Y %H:%M', m.data_hora),
               (SELECT COUNT(*) FROM Lembrete WHERE mensagem_id = m.id) as tem_lembrete
        FROM Mensagem m WHERE cliente_id = ? ORDER BY data_hora ASC
    ''', (cliente_id,)).fetchall()
    conn.close()
    return jsonify([{'id': m[0], 'texto': m[1], 'path': m[2], 'tipo': m[3], 'data': m[4], 'tem_lembrete': m[5] > 0} for m in mensagens])

@app.route('/get_arquivos/<int:cliente_id>')
def get_arquivos(cliente_id):
    conn = conectar()
    # Busca apenas mensagens que possuem caminho de arquivo (anexos)
    arquivos = conn.execute('''
        SELECT texto, arquivo_path, tipo, strftime('%d/%m/%Y %H:%M', data_hora) 
        FROM Mensagem 
        WHERE cliente_id = ? AND arquivo_path IS NOT NULL 
        ORDER BY data_hora DESC
    ''', (cliente_id,)).fetchall()
    conn.close()
    
    return jsonify([{'texto': m[0], 'path': m[1], 'tipo': m[2], 'data': m[3]} for m in arquivos])

@app.route('/api/pesquisar_mensagens')
def pesquisar_mensagens():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    
    conn = conectar()
    # Adicionamos m.id aqui também
    resultados = conn.execute('''
        SELECT m.id, m.texto, e.id, e.nome, strftime('%d/%m/%Y %H:%M', m.data_hora) 
        FROM Mensagem m
        JOIN Cliente e ON m.cliente_id = e.id
        WHERE m.texto LIKE ?
        ORDER BY m.data_hora DESC
        LIMIT 50
    ''', (f'%{q}%',)).fetchall()
    conn.close()
    
    return jsonify([{'msg_id': r[0], 'texto': r[1], 'cliente_id': r[2], 'cliente_nome': r[3], 'data': r[4]} for r in resultados])

@app.route('/enviar_mensagem', methods=['POST'])
def enviar_mensagem():
    cliente_id = request.form.get('cliente_id')
    texto = request.form.get('texto')
    arquivos = request.files.getlist('arquivo')  # Captura a lista de arquivos
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = conectar()

    # Se houver texto, salva primeiro
    if texto and texto.strip():
        conn.execute('INSERT INTO Mensagem (cliente_id, texto, tipo, data_hora) VALUES (?, ?, ?, ?)', 
                     (cliente_id, texto, 'texto', agora))

    # Salva cada arquivo enviado
    for arquivo in arquivos:
        if arquivo and arquivo.filename:
            nome_seguro = secure_filename(arquivo.filename)
            filename = f"{int(datetime.now().timestamp())}_{nome_seguro}"
            arquivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            _, ext = os.path.splitext(filename)
            tipo = 'imagem' if ext.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp'] else 'arquivo'
            path = f"uploads/{filename}"
            conn.execute('INSERT INTO Mensagem (cliente_id, arquivo_path, tipo, data_hora) VALUES (?, ?, ?, ?)', 
                         (cliente_id, path, tipo, agora))

    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/editar_mensagem/<int:id>', methods=['POST'])
def editar_mensagem(id):
    novo_texto = request.form.get('texto')
    if novo_texto is not None:
        conn = conectar()
        conn.execute('UPDATE Mensagem SET texto = ? WHERE id = ?', (novo_texto, id))
        conn.commit()
        conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/excluir_mensagem/<int:id>', methods=['POST'])
def excluir_mensagem(id):
    conn = conectar()
    
    # Busca se tem arquivo para apagar da pasta uploads
    msg = conn.execute('SELECT arquivo_path FROM Mensagem WHERE id = ?', (id,)).fetchone()
    if msg and msg[0]:
        caminho_arquivo = os.path.join('static', msg[0])
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
            
    conn.execute('DELETE FROM Mensagem WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/exportar_relatorio')
def exportar_relatorio():
    conn = conectar()
    
    # Nova consulta: Cria uma linha para cada Vaga vinculada ao cliente
    query = '''
        SELECT 
            IFNULL(p.nome, 'Sem Pasta') as pasta,
            e.nome as empresa,
            IFNULL(v.nome, 'Sem Vaga') as vaga,
            IFNULL(st.nome, '') as status,
            cv.taxa as taxa,
            (SELECT GROUP_CONCAT(sel.nome, ', ') FROM Selecionadora sel JOIN Cliente_Selecionadora cs ON sel.id = cs.selecionadora_id WHERE cs.cliente_id = e.id) as selecionadoras,
            (SELECT GROUP_CONCAT(c.nome, ', ') FROM Contato c WHERE c.cliente_id = e.id) as c_nome,
            (SELECT GROUP_CONCAT(c.email, ', ') FROM Contato c WHERE c.cliente_id = e.id) as c_email,
            (SELECT GROUP_CONCAT(c.telefone, ', ') FROM Contato c WHERE c.cliente_id = e.id) as c_tel
        FROM Cliente e
        LEFT JOIN Pasta p ON e.pasta_id = p.id
        LEFT JOIN Cliente_Vaga cv ON e.id = cv.cliente_id
        LEFT JOIN Vaga v ON cv.vaga_id = v.id
        LEFT JOIN Status st ON cv.status_id = st.id
        ORDER BY pasta ASC, empresa ASC, vaga ASC
    '''
    dados = conn.execute(query).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';') # Ponto e vírgula para o Excel BR
    
    # Cabeçalho com as novas colunas
    writer.writerow(['PASTA', 'EMPRESA', 'VAGA', 'STATUS', 'TAXA', 'SELECIONADORA', 'C-NOME', 'C-EMAIL', 'C-TELEFONE'])
    
    for linha in dados:
        # Troca valores nulos (None) do banco de dados por um texto vazio para não ficar escrito "None" no Excel
        linha_formatada = [str(item) if item is not None else '' for item in linha]
        
        # Se existir uma taxa na vaga (posição 4 do array), coloca o símbolo de % do lado dela
        if linha_formatada[4]:
            linha_formatada[4] = f"{linha_formatada[4]}%"
            
        writer.writerow(linha_formatada)
    
    output.seek(0)
    conteudo = "\ufeff" + output.getvalue() # Adiciona o BOM para o Excel ler acentos direito
    
    response = make_response(conteudo)
    response.headers["Content-Disposition"] = f"attachment; filename=relatorio_clientes_{datetime.now().strftime('%d_%m_%Y')}.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    return response

# --- ROTAS DE EMPRESA ---
@app.route('/salvar', methods=['POST'])
def salvar():
    nome = request.form.get('nome_cliente', '').strip()
    p_id = request.form.get('pasta_id') or None
    urgencia = 'BAIXA'
    v_ids = request.form.getlist('vagas_ids')
    s_ids = request.form.getlist('selecionadoras_ids')
    
    if nome:
        conn = conectar()
        existe = conn.execute('SELECT id FROM Cliente WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone()
        if existe:
            conn.close()
            return redirect('/') 
            
        cursor = conn.cursor()
        cursor.execute('INSERT INTO Cliente (nome, pasta_id, urgencia) VALUES (?, ?, ?)', (nome, p_id, urgencia))
        e_id = cursor.lastrowid
        
        # Inserção das vagas pegando o status de cada uma
        if v_ids: 
            vagas_dados = []
            for v_id in v_ids:
                st_id = request.form.get(f'status_vaga_{v_id}') or None
                taxa = request.form.get(f'taxa_vaga_{v_id}') or None
                if taxa == '': taxa = None
                vagas_dados.append((e_id, v_id, st_id, taxa))
            cursor.executemany('INSERT INTO Cliente_Vaga (cliente_id, vaga_id, status_id, taxa) VALUES (?, ?, ?, ?)', vagas_dados)
            
        if s_ids: cursor.executemany('INSERT INTO Cliente_Selecionadora (cliente_id, selecionadora_id) VALUES (?, ?)', [(e_id, s) for s in s_ids])
            
        conn.commit()
        conn.close()
    return redirect('/')

@app.route('/editar/<int:id>', methods=['POST'])
def editar(id):
    nome = request.form.get('nome_cliente', '').strip()
    p_id = request.form.get('pasta_id') or None
    urgencia = 'BAIXA'
    v_ids = request.form.getlist('vagas_ids')
    s_ids = request.form.getlist('selecionadoras_ids')
    nomes_contato = request.form.getlist('contato_nome[]')
    emails_contato = request.form.getlist('contato_email[]')
    tels_contato = request.form.getlist('contato_telefone[]')
    
    conn = conectar()
    existe = conn.execute('SELECT id FROM Cliente WHERE LOWER(nome) = LOWER(?) AND id != ?', (nome, id)).fetchone()
    if existe:
        conn.close()
        return redirect('/') 

    conn.execute('UPDATE Cliente SET nome = ?, pasta_id = ?, urgencia = ? WHERE id = ?', (nome, p_id, urgencia, id))
    
    # Limpa e reinsere Vagas com Status
    conn.execute('DELETE FROM Cliente_Vaga WHERE cliente_id = ?', (id,))
    conn.execute('DELETE FROM Cliente_Vaga WHERE cliente_id = ?', (id,))
    if v_ids: 
        vagas_dados = []
        for v_id in v_ids:
            st_id = request.form.get(f'status_vaga_{v_id}') or None
            taxa = request.form.get(f'taxa_vaga_{v_id}') or None
            if taxa == '': taxa = None
            vagas_dados.append((id, v_id, st_id, taxa))
        conn.executemany('INSERT INTO Cliente_Vaga (cliente_id, vaga_id, status_id, taxa) VALUES (?, ?, ?, ?)', vagas_dados)
    
    conn.execute('DELETE FROM Cliente_Selecionadora WHERE cliente_id = ?', (id,))
    if s_ids: conn.executemany('INSERT INTO Cliente_Selecionadora (cliente_id, selecionadora_id) VALUES (?, ?)', [(id, s) for s in s_ids])

    conn.execute('DELETE FROM Contato WHERE cliente_id = ?', (id,))
    for n, e, t in zip(nomes_contato, emails_contato, tels_contato):
        if n.strip() or e.strip() or t.strip():
            conn.execute('INSERT INTO Contato (cliente_id, nome, email, telefone) VALUES (?, ?, ?, ?)', (id, n, e, t))
        
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/excluir/<int:id>')
def excluir(id):
    conn = conectar()
    conn.execute('DELETE FROM Cliente WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

# --- ROTAS DE PASTA ---
@app.route('/salvar_pasta', methods=['POST'])
def salvar_pasta():
    nome = request.form.get('nome_pasta', '').strip()
    parent_id = request.form.get('parent_id') or None
    
    if nome:
        conn = conectar()
        
        # Se for uma pasta principal (parent_id é None), verifica nomes duplicados
        if not parent_id:
            existe = conn.execute('SELECT id FROM Pasta WHERE LOWER(nome) = LOWER(?) AND parent_id IS NULL', (nome,)).fetchone()
            if existe:
                conn.close()
                return redirect('/') # Nome já existe, cancela a criação

        conn.execute('INSERT INTO Pasta (nome, parent_id) VALUES (?, ?)', (nome, parent_id))
        conn.commit()
        conn.close()
    return redirect('/')

@app.route('/editar_pasta/<int:id>', methods=['POST'])
def editar_pasta(id):
    nome = request.form.get('nome_pasta', '').strip()
    parent_id = request.form.get('parent_id') or None
    
    # Impede que a pasta seja colocada dentro dela mesma
    if str(parent_id) == str(id): 
        parent_id = None
        
    if nome:
        conn = conectar()
        
        # Se estiver editando para ser uma pasta principal, verifica se já existe OUTRA com esse nome
        if not parent_id:
            existe = conn.execute('SELECT id FROM Pasta WHERE LOWER(nome) = LOWER(?) AND parent_id IS NULL AND id != ?', (nome, id)).fetchone()
            if existe:
                conn.close()
                return redirect('/') # Nome já existe, cancela a edição

        conn.execute('UPDATE Pasta SET nome = ?, parent_id = ? WHERE id = ?', (nome, parent_id, id))
        conn.commit()
        conn.close()
    return redirect('/')

@app.route('/excluir_pasta/<int:id>')
def excluir_pasta(id):
    conn = conectar()
    
    # 1. Tira as empresas apenas da pasta principal que vai ser apagada (joga pra "Sem pasta")
    conn.execute('UPDATE Cliente SET pasta_id = NULL WHERE pasta_id = ?', (id,))
    
    # 2. Promove as subpastas: tira o vínculo delas com a pasta mãe, transformando-as em pastas principais
    conn.execute('UPDATE Pasta SET parent_id = NULL WHERE parent_id = ?', (id,))
    
    # 3. Deleta apenas a pasta principal
    conn.execute('DELETE FROM Pasta WHERE id = ?', (id,))
    
    conn.commit()
    conn.close()
    return redirect('/')

# --- ROTAS DE VAGAS ---
@app.route('/salvar_vaga', methods=['POST'])
def salvar_vaga():
    nome = request.form.get('nome_vaga', '').strip()
    if nome:
        conn = conectar()
        if not conn.execute('SELECT id FROM Vaga WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone():
            conn.execute('INSERT INTO Vaga (nome) VALUES (?)', (nome,))
            conn.commit()
        conn.close()
    return redirect('/')

@app.route('/editar_vaga/<int:id>', methods=['POST'])
def editar_vaga(id):
    novo_nome = request.form.get('nome_vaga', '').strip()
    if novo_nome:
        conn = conectar()
        if not conn.execute('SELECT id FROM Vaga WHERE LOWER(nome) = LOWER(?) AND id != ?', (novo_nome, id)).fetchone():
            conn.execute('UPDATE Vaga SET nome = ? WHERE id = ?', (novo_nome, id))
            conn.commit()
        conn.close()
    return redirect('/')

@app.route('/excluir_vaga/<int:id>')
def excluir_vaga(id):
    conn = conectar()
    conn.execute('DELETE FROM Vaga WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

# --- ROTAS DE STATUS ---
@app.route('/salvar_status', methods=['POST'])
def salvar_status():
    nome = request.form.get('nome_status', '').strip()
    if nome:
        conn = conectar()
        if not conn.execute('SELECT id FROM Status WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone():
            conn.execute('INSERT INTO Status (nome) VALUES (?)', (nome,))
            conn.commit()
        conn.close()
    return redirect('/')

@app.route('/editar_status/<int:id>', methods=['POST'])
def editar_status(id):
    novo_nome = request.form.get('nome_status', '').strip()
    if novo_nome:
        conn = conectar()
        if not conn.execute('SELECT id FROM Status WHERE LOWER(nome) = LOWER(?) AND id != ?', (novo_nome, id)).fetchone():
            conn.execute('UPDATE Status SET nome = ? WHERE id = ?', (novo_nome, id))
            conn.commit()
        conn.close()
    return redirect('/')

@app.route('/excluir_status/<int:id>')
def excluir_status(id):
    conn = conectar()
    conn.execute('UPDATE Cliente SET status_id = NULL WHERE status_id = ?', (id,))
    conn.execute('DELETE FROM Status WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

# --- ROTAS DE SELECIONADORAS ---
@app.route('/salvar_selecionadora', methods=['POST'])
def salvar_selecionadora():
    nome = request.form.get('nome_selecionadora', '').strip()
    if nome:
        conn = conectar()
        if not conn.execute('SELECT id FROM Selecionadora WHERE LOWER(nome) = LOWER(?)', (nome,)).fetchone():
            conn.execute('INSERT INTO Selecionadora (nome) VALUES (?)', (nome,))
            conn.commit()
        conn.close()
    return redirect('/')

@app.route('/editar_selecionadora/<int:id>', methods=['POST'])
def editar_selecionadora(id):
    novo_nome = request.form.get('nome_selecionadora', '').strip()
    if novo_nome:
        conn = conectar()
        if not conn.execute('SELECT id FROM Selecionadora WHERE LOWER(nome) = LOWER(?) AND id != ?', (novo_nome, id)).fetchone():
            conn.execute('UPDATE Selecionadora SET nome = ? WHERE id = ?', (novo_nome, id))
            conn.commit()
        conn.close()
    return redirect('/')

@app.route('/excluir_selecionadora/<int:id>')
def excluir_selecionadora(id):
    conn = conectar()
    conn.execute('DELETE FROM Selecionadora WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect('/')

# --- ROTAS DE BUSCA PARA O CHAT ---
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
        SELECT v.nome, s.nome, cv.taxa 
        FROM Cliente_Vaga cv 
        JOIN Vaga v ON cv.vaga_id = v.id 
        LEFT JOIN Status s ON cv.status_id = s.id 
        WHERE cv.cliente_id = ?
    ''', (cliente_id,)).fetchall()
    
    tags_vagas = []
    for v_nome, s_nome, taxa in vagas_bd:
        # Formata o texto dependendo se tem status, taxa ou ambos
        partes_status = []
        if s_nome: partes_status.append(s_nome)
        if taxa is not None: partes_status.append(f"{taxa}%")
        
        texto_final = f"{v_nome} ({' - '.join(partes_status)})" if partes_status else v_nome
        
        tags_vagas.append({
            'texto': texto_final, 
            'status': s_nome.upper() if s_nome else ''
        })
            
    sels = conn.execute('SELECT s.nome FROM Selecionadora s JOIN Cliente_Selecionadora es ON s.id = es.selecionadora_id WHERE es.cliente_id = ?', (cliente_id,)).fetchall()
    conn.close()
    
    return jsonify({
        'status': '', 
        'vagas': tags_vagas,
        'selecionadoras': [s[0] for s in sels]
    })

# --- ROTAS DE LEMBRETES ---
@app.route('/api/criar_lembrete', methods=['POST'])
def criar_lembrete():
    texto = request.form.get('texto')
    mensagem_id = request.form.get('mensagem_id')
    data_alerta_html = request.form.get('data_alerta') 
    
    data_alerta = data_alerta_html.replace('T', ' ') + ':00'
    
    conn = conectar()
    
    # Adicionamos o "AND lido = 0" para barrar apenas se tiver um pendente
    existe = conn.execute('SELECT id FROM Lembrete WHERE mensagem_id = ? AND lido = 0', (mensagem_id,)).fetchone()
    
    if existe:
        conn.close()
        return jsonify({'status': 'erro', 'mensagem': 'Essa mensagem já possui um lembrete pendente!'})
        
    # Se não tiver nenhum pendente (mesmo que tenha concluídos), cria o novo
    conn.execute('INSERT INTO Lembrete (mensagem_id, texto, data_alerta) VALUES (?, ?, ?)', (mensagem_id, texto, data_alerta))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'sucesso'})

@app.route('/api/lembrete_pendente')
def lembrete_pendente():
    conn = conectar()
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    res = conn.execute('''
        SELECT l.id, l.texto, c.nome 
        FROM Lembrete l
        JOIN Mensagem m ON l.mensagem_id = m.id
        JOIN Cliente c ON m.cliente_id = c.id
        WHERE l.lido = 0 AND l.data_alerta <= ? 
        ORDER BY l.data_alerta ASC LIMIT 1
    ''', (agora,)).fetchone()
    conn.close()
    return jsonify({'id': res[0], 'texto': res[1], 'empresa': res[2]}) if res else jsonify(None)


@app.route('/api/lista_lembretes')
def lista_lembretes():
    conn = conectar()
    # Removido o "lido = 0" para manter o histórico
    lembretes = conn.execute('''
        SELECT l.id, l.texto, strftime('%d/%m/%Y %H:%M', l.data_alerta),
               l.lido, c.nome,
               CASE WHEN l.data_alerta <= datetime('now', 'localtime') AND l.lido = 0 THEN 1 ELSE 0 END as vencido
        FROM Lembrete l
        JOIN Mensagem m ON l.mensagem_id = m.id
        JOIN Cliente c ON m.cliente_id = c.id
        ORDER BY l.lido ASC, l.data_alerta DESC
    ''').fetchall()
    conn.close()
    return jsonify([{'id': l[0], 'texto': l[1], 'data': l[2], 'lido': bool(l[3]), 'empresa': l[4], 'vencido': bool(l[5])} for l in lembretes])

@app.route('/api/marcar_lembrete_lido/<int:id>', methods=['POST'])
def marcar_lembrete_lido(id):
    """Marca o lembrete como concluído"""
    conn = conectar()
    conn.execute('UPDATE Lembrete SET lido = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})



@app.route('/resgatar_limbo')
def resgatar_limbo():
    conn = conectar()
    
    # Procura subpastas cuja pasta mãe não existe mais e transforma em pasta principal
    conn.execute('''
        UPDATE Pasta 
        SET parent_id = NULL 
        WHERE parent_id IS NOT NULL 
        AND parent_id NOT IN (SELECT id FROM Pasta)
    ''')
    
    conn.commit()
    conn.close()
    return redirect('/')

if __name__ == '__main__':
    criar_tabelas()
    print(" * Running on http://127.0.0.1:5000")
    app.run()