import os
import shutil
from datetime import datetime

def realizar_backup(limite=10):
    # Configurações de pastas
    pasta_origem = "banco_de_dados"
    arquivo_db = "dados.db"
    pasta_backup = "backups"
    
    caminho_db = os.path.join(pasta_origem, arquivo_db)
    
    if not os.path.exists(caminho_db):
        return

    # Cria pasta de backup se não existir
    if not os.path.exists(pasta_backup):
        os.makedirs(pasta_backup)

    # Gera o nome com data e hora
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_backup = f"backup_{data_hora}.db"
    shutil.copy2(caminho_db, os.path.join(pasta_backup, nome_backup))

    # --- Lógica para apagar os antigos ---
    arquivos = [os.path.join(pasta_backup, f) for f in os.listdir(pasta_backup) if f.endswith('.db')]
    arquivos.sort(key=os.path.getmtime)

    while len(arquivos) > limite:
        arquivo_antigo = arquivos.pop(0)
        os.remove(arquivo_antigo)

if __name__ == "__main__":
    realizar_backup(limite=5)