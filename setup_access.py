"""Create/reset an account without putting a password in source files."""
import argparse
import getpass
from app import app
from security import create_access

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Senha: ')
    create_access(app, args.email, password)
    print('Acesso configurado. Sessões anteriores encerradas.')
