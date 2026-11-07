"""Ajouter une clé OpenAI dédiée : sudo python3 configure_openai.py."""
from getpass import getpass
import http.client
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telegram_api import connect_ipv4


def main():
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise SystemExit('Exécute ce script avec sudo dans un terminal interactif.')
    target = Path('/etc/maxxie-films-openai.env')
    if target.exists():
        raise SystemExit('La configuration OpenAI existe déjà ; aucune modification effectuée.')
    key = getpass('Nouvelle clé OpenAI dédiée au bot films (saisie masquée) : ').strip()
    if not key or any(char.isspace() for char in key):
        raise SystemExit('Clé invalide.')
    model = input('Modèle [gpt-4.1-mini] : ').strip() or 'gpt-4.1-mini'
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', model):
        raise SystemExit('Nom de modèle invalide.')
    connection = http.client.HTTPSConnection('api.openai.com', timeout=8)
    connection._create_connection = connect_ipv4
    try:
        connection.request('GET', '/v1/models/' + model, headers={'Authorization': 'Bearer ' + key})
        response = connection.getresponse()
        response.read()
        if response.status != 200:
            raise SystemExit(f'Vérification OpenAI refusée (code {response.status}). Aucun fichier créé.')
    except (OSError, http.client.HTTPException):
        raise SystemExit('Connexion à OpenAI impossible. Aucun fichier créé.') from None
    finally:
        connection.close()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(f'OPENAI_API_KEY={key}\nOPENAI_MODEL={model}\n'
                     'OPENAI_DAILY_USER_LIMIT=20\nOPENAI_DAILY_TOTAL_LIMIT=100\n')
    print('Clé dédiée vérifiée et enregistrée. Pour activer : sudo systemctl restart maxxie-films-bot')


if __name__ == '__main__':
    main()
