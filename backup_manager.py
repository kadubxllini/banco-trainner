import os
import shutil
from datetime import datetime

def realizar_backup(limite=10):
    """Cria um backup do banco de dados e apaga os mais antigos se passar do limite."""
    caminho_db = os.path.join("banco_de_dados", "dados.db")
    pasta_backup = "backups"
    
    # Se o banco principal não existe ainda, não tem o que fazer
    if not os.path.exists(caminho_db):
        return

    # Cria a pasta de backups se ela não existir (o exist_ok=True evita erro se já existir)
    os.makedirs(pasta_backup, exist_ok=True)

    # Copia o arquivo com a data e hora atual no nome
    data_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_novo_backup = os.path.join(pasta_backup, f"backup_{data_hora}.db")
    shutil.copy2(caminho_db, caminho_novo_backup)

    # Lista os backups e ordena pela data de modificação (do mais antigo pro mais novo)
    arquivos = [os.path.join(pasta_backup, f) for f in os.listdir(pasta_backup) if f.endswith('.db')]
    arquivos.sort(key=os.path.getmtime)

    # Fatiamento da lista: pega os arquivos que estão sobrando no início da fila e apaga
    for arquivo_antigo in arquivos[:-limite]:
        os.remove(arquivo_antigo)

if __name__ == "__main__":
    realizar_backup(limite=5)