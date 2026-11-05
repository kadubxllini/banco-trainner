"""Create a disposable local fixture for CI; never use production data."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
target = ROOT / 'banco_de_dados' / 'dados.db'
if target.exists():
    raise SystemExit('Fixture creation refused: database already exists.')

import app

app.criar_tabelas()
with app.conectar() as conn:
    for table, name in [('Vaga', 'Vaga de demonstração'), ('Status', 'Em análise'),
                        ('Selecionadora', 'Equipe de demonstração'), ('Cliente', 'Empresa de demonstração')]:
        conn.execute(f'INSERT INTO {table} (nome) VALUES (?)', (name,))
    conn.commit()
print('Synthetic test database created.')
