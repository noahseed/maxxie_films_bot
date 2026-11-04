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
install -d -m 755 /opt/maxxie-films-bot
install -m 644 bot.py catalogue.py telegram_api.py deploy/configure.py /opt/maxxie-films-bot/
install -m 644 deploy/maxxie-films-bot.service /etc/systemd/system/
systemctl daemon-reload
echo 'Fichiers installés. Le service n’a pas été démarré.'
echo 'Configurer : sudo python3 /opt/maxxie-films-bot/configure.py'
