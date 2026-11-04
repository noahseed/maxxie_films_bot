"""Configuration initiale sur le VPS, sans afficher le jeton."""
from getpass import getpass
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telegram_api import Telegram, TelegramError
from bot import user_ids


def main():
    if os.geteuid() != 0:
        raise SystemExit("Exécute ce script avec sudo.")
    target = Path('/etc/maxxie-films-bot.env')
    if target.exists():
        raise SystemExit('La configuration existe déjà ; aucune modification effectuée.')
    token = getpass('Jeton de @maxxie_films_bot (saisie masquée) : ').strip()
    try:
        api = Telegram(token)
        identity = api.call('getMe')
        if identity.get('username', '').lower() != 'maxxie_films_bot':
            raise SystemExit('Le jeton ne correspond pas à @maxxie_films_bot.')
        if api.call('getWebhookInfo').get('url'):
            raise SystemExit('Un webhook existe déjà ; configuration annulée.')
        admins = user_ids(input('Identifiants numériques des administrateurs (virgules) : '))
        allowed = user_ids(input('Identifiants des autres utilisateurs autorisés (facultatif) : '))
        if not admins:
            raise ValueError('Au moins un administrateur est nécessaire')
    except (TelegramError, ValueError) as error:
        raise SystemExit(str(error)) from None
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(f'BOT_TOKEN={token}\nBOT_USERNAME=maxxie_films_bot\n'
                     f"ADMIN_USER_IDS={','.join(map(str, sorted(admins)))}\n"
                     f"ALLOWED_USER_IDS={','.join(map(str, sorted(allowed)))}\n"
                     'DATABASE_PATH=/var/lib/maxxie-films-bot/catalogue.sqlite3\n')
    print('Configuration enregistrée. Démarrage : sudo systemctl enable --now maxxie-films-bot')


if __name__ == '__main__':
    main()
