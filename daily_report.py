"""Daily business activity, committed atomically with the operation it describes."""
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

CUIABA = timezone(timedelta(hours=-4))
TABLES = ('Cliente', 'Cliente_Vaga', 'Cliente_Selecionadora', 'Mensagem',
          'Contato', 'Lembrete', 'Pasta', 'Vaga', 'Status', 'Selecionadora')
LABELS = {'Cliente': 'Empresa', 'Cliente_Vaga': 'Vaga da empresa',
          'Cliente_Selecionadora': 'Selecionadora da empresa', 'Mensagem': 'Mensagem',
          'Contato': 'Contato', 'Lembrete': 'Lembrete', 'Pasta': 'Pasta',
          'Vaga': 'Vaga', 'Status': 'Etapa', 'Selecionadora': 'Selecionadora'}
FIELDS = {'nome': 'Nome', 'texto': 'Texto', 'email': 'E-mail', 'telefone': 'Telefone',
          'urgencia': 'Prioridade', 'taxa': 'Taxa (%)', 'data_alerta': 'Agendado para',
          'arquivo_path': 'Arquivo', 'tipo': 'Tipo', 'lido': 'Concluído',
          'pasta_id': 'Pasta', 'parent_id': 'Pasta superior', 'vaga_id': 'Vaga',
          'status_id': 'Etapa', 'selecionadora_id': 'Selecionadora',
          'mensagem_id': 'Mensagem vinculada'}
REFERENCES = {'pasta_id': 'Pasta', 'parent_id': 'Pasta', 'vaga_id': 'Vaga',
              'status_id': 'Status', 'selecionadora_id': 'Selecionadora'}


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def ensure_schema(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='MovimentoDiario'").fetchone():
        return
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS MovimentoDiario (
            id INTEGER PRIMARY KEY AUTOINCREMENT, momento_utc TEXT NOT NULL,
            categoria TEXT NOT NULL, empresa_id INTEGER, empresa TEXT NOT NULL,
            resumo TEXT NOT NULL, detalhes TEXT NOT NULL,
            antes TEXT, depois TEXT
        );
        CREATE INDEX IF NOT EXISTS movimento_momento ON MovimentoDiario(momento_utc, id);
        CREATE TABLE IF NOT EXISTS RelatorioInicio (id INTEGER PRIMARY KEY CHECK(id=1), momento_utc TEXT NOT NULL);
    ''')
    conn.execute('INSERT OR IGNORE INTO RelatorioInicio VALUES (1, ?)', (utc_now(),))
    sqlite3.Connection.commit(conn)


def snapshot(conn):
    """Small local business DB: an in-memory comparison also ignores form rewrites.

    The write lock is acquired before this read so concurrent requests cannot
    attribute each other's changes. Auth tables and the accumulated report are
    never scanned or copied. Only actual differences become historical rows.
    """
    result = {}
    for table in TABLES:
        cursor = conn.execute(f'SELECT * FROM {table}')
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor]
        if table == 'Contato':
            # The editor rebuilds contacts with new ids even when unchanged.
            counts = Counter()
            data = {}
            for row in rows:
                row.pop('id')
                content = tuple(row.items())
                counts[content] += 1
                data[(content, counts[content])] = row
            result[table] = data
        else:
            result[table] = {
                (r['cliente_id'], r['vaga_id']) if table == 'Cliente_Vaga' else
                (r['cliente_id'], r['selecionadora_id']) if table == 'Cliente_Selecionadora' else r['id']: r
                for r in rows
            }
    return result


def name(state, table, key):
    row = state[table].get(key)
    return row['nome'] if row else (f'Cadastro removido (#{key})' if key else 'Não definido')


def field_value(state, field, value):
    if field in REFERENCES:
        return name(state, REFERENCES[field], value)
    if field == 'mensagem_id':
        row = state['Mensagem'].get(value, {})
        return row.get('texto') or row.get('arquivo_path') or f'Mensagem #{value}'
    if field == 'lido':
        return 'Sim' if value else 'Não'
    if field == 'data_alerta' and value:
        try:
            return datetime.fromisoformat(value).strftime('%d/%m/%Y às %H:%M')
        except ValueError:
            pass
    if field == 'arquivo_path' and value:
        return re.sub(r'^[0-9a-f]{32}_', '', value.rsplit('/', 1)[-1])
    return str(value) if value not in (None, '') else 'Não informado'


def differences(before, after):
    for table in TABLES:
        for key in dict.fromkeys([*before[table], *after[table]]):
            old, new = before[table].get(key), after[table].get(key)
            if old == new:
                continue
            row = new or old
            state = after if new else before
            company_id = row.get('cliente_id')
            if table == 'Cliente':
                company_id = row['id']
            if table == 'Lembrete':
                message = state['Mensagem'].get(row['mensagem_id']) or before['Mensagem'].get(row['mensagem_id'], {})
                company_id = message.get('cliente_id')
            company = name(state, 'Cliente', company_id) if company_id else ''
            subject = LABELS[table]
            if table == 'Mensagem' and row.get('arquivo_path'):
                subject = 'Anexo'
            if table in ('Cliente_Vaga', 'Cliente_Selecionadora'):
                field = 'vaga_id' if table == 'Cliente_Vaga' else 'selecionadora_id'
                subject = ('Vaga: ' if field == 'vaga_id' else 'Selecionadora: ') + field_value(state, field, row[field])
                action = 'Vinculada' if not old else 'Desvinculada' if not new else 'Atualizada'
            else:
                feminine = table in ('Cliente', 'Pasta', 'Vaga', 'Status', 'Selecionadora')
                action = ('Criada' if feminine else 'Criado') if not old else ('Excluída' if feminine else 'Excluído') if not new else ('Atualizada' if feminine else 'Atualizado')
                if table == 'Mensagem':
                    feminine = subject == 'Mensagem'
                    action = ('Enviada' if feminine else 'Enviado') if not old else ('Excluída' if feminine else 'Excluído') if not new else ('Editada' if feminine else 'Editado')
                elif table == 'Lembrete' and old and new and not old['lido'] and new['lido']:
                    action = 'Concluído'
            details = []
            for field, label in FIELDS.items():
                if field not in row:
                    continue
                previous = old.get(field) if old else None
                current = new.get(field) if new else None
                if old and new and previous == current:
                    continue
                if not (old and new) and row[field] in (None, ''):
                    continue
                if table == 'Mensagem' and field == 'tipo' and row[field] == 'texto':
                    continue
                if old and new:
                    text = f'{field_value(before, field, previous)} → {field_value(after, field, current)}'
                else:
                    text = field_value(state, field, row[field])
                details.append({'campo': label, 'valor': text})
            yield (LABELS[table] if subject != 'Anexo' else 'Anexo', company_id, company,
                   f'{subject} · {action.lower()}', json.dumps(details, ensure_ascii=False),
                   json.dumps(old, ensure_ascii=False) if old else None,
                   json.dumps(new, ensure_ascii=False) if new else None)


class MovementConnection(sqlite3.Connection):
    report_before = None

    def begin_report(self):
        self.execute('BEGIN IMMEDIATE')
        self.report_before = snapshot(self)

    def commit(self):
        if self.report_before is not None:
            after = snapshot(self)
            changes = list(differences(self.report_before, after))
            moment = utc_now()
            self.executemany('''INSERT INTO MovimentoDiario
                (momento_utc,categoria,empresa_id,empresa,resumo,detalhes,antes,depois)
                VALUES (?,?,?,?,?,?,?,?)''', [(moment, *change) for change in changes])
            super().commit()
            self.report_before = None
        else:
            super().commit()


def day_bounds(start, end):
    first = datetime.strptime(start, '%Y-%m-%d').replace(tzinfo=CUIABA)
    last = datetime.strptime(end, '%Y-%m-%d').replace(tzinfo=CUIABA)
    if first > last or (last-first).days > 365:
        raise ValueError('Selecione um período de até 366 dias, com o início antes do fim.')
    serialize = lambda value: value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    return serialize(first), serialize(last + timedelta(days=1))


def local_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(CUIABA)
