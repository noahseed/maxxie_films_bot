#!/bin/sh
# À exécuter sur le VPS depuis une copie de ce dépôt.
set -eu
cd "$(dirname "$0")/.."
if [ "$(id -u)" -ne 0 ]; then
    echo "Exécute ce script avec sudo." >&2
    exit 1
fi
if ! id maxxie-films-bot >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin maxxie-films-bot
fi
apt-get install -y postgresql python3-psycopg
install -d -m 755 /opt/maxxie-films-bot
install -m 644 database.py migrate_postgres.py bot.py catalogue.py search.py telegram_api.py openai_api.py posters.py backups.py deploy/setup_postgres.py deploy/configure.py deploy/configure_openai.py deploy/configure_posters.py /opt/maxxie-films-bot/
install -d -m 700 /var/backups/maxxie-films-bot
install -m 644 deploy/maxxie-films-bot.service deploy/maxxie-films-backup.service deploy/maxxie-films-backup.timer /etc/systemd/system/
systemctl enable --now postgresql
python3 /opt/maxxie-films-bot/setup_postgres.py
systemctl daemon-reload
systemctl enable --now maxxie-films-backup.timer
echo 'Fichiers installés. Le service n’a pas été démarré.'
echo 'Configurer : sudo python3 /opt/maxxie-films-bot/configure.py'
