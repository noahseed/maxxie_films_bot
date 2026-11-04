"""Sauvegarde cohérente de SQLite, de la configuration et du code du bot."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tarfile
import tempfile
import time


def make_backup(database, config, code, units, destination, keep=14):
    database, config, code, units, destination = map(Path, (database, config, code, units, destination))
    if keep < 1 or destination.is_symlink():
        raise ValueError('Paramètres de sauvegarde invalides')
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.chmod(0o700)
    sources = {'config/maxxie-films-bot.env': config}
    for name in ('bot.py', 'catalogue.py', 'search.py', 'telegram_api.py', 'configure.py', 'backups.py'):
        sources['code/' + name] = code / name
    for name in ('maxxie-films-bot.service', 'maxxie-films-backup.service', 'maxxie-films-backup.timer'):
        sources['systemd/' + name] = units / name
    for path in (database, *sources.values()):
        if not path.is_file():
            raise FileNotFoundError('Un fichier nécessaire à la sauvegarde est absent')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    final = destination / f'maxxie-films-{stamp}-{secrets.token_hex(3)}.tar.gz'
    fd, temporary = tempfile.mkstemp(prefix='.backup-', suffix='.partial', dir=destination)
    os.close(fd)
    temporary = Path(temporary)
    try:
        with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=destination) as scratch:
            snapshot = Path(scratch) / 'catalogue.sqlite3'
            snapshot.touch(mode=0o600)
            started = time.monotonic()
            def progress(*_):
                if time.monotonic() - started > 60:
                    raise TimeoutError('Délai de sauvegarde SQLite dépassé')
            with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(snapshot)) as target:
                    source.backup(target, pages=128, progress=progress)
                    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('La copie SQLite est invalide')
            sources['data/catalogue.sqlite3'] = snapshot
            manifest = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sources.items()}
            manifest_path = Path(scratch) / 'manifest.json'
            manifest_path.write_text(json.dumps(manifest, indent=2))
            with tarfile.open(temporary, 'w:gz') as archive:
                for name, path in sources.items():
                    archive.add(path, arcname=name, recursive=False)
                archive.add(manifest_path, arcname='manifest.json')
            with tarfile.open(temporary, 'r:gz') as archive:
                for name, expected in manifest.items():
                    with archive.extractfile(name) as stream:
                        if hashlib.sha256(stream.read()).hexdigest() != expected:
                            raise ValueError('Archive de sauvegarde invalide')
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        temporary.replace(final)
        for old in sorted(destination.glob('maxxie-films-*.tar.gz'), reverse=True)[keep:]:
            old.unlink()
        return final
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='/var/lib/maxxie-films-bot/catalogue.sqlite3')
    parser.add_argument('--config', default='/etc/maxxie-films-bot.env')
    parser.add_argument('--code', default='/opt/maxxie-films-bot')
    parser.add_argument('--units', default='/etc/systemd/system')
    parser.add_argument('--destination', default='/var/backups/maxxie-films-bot')
    parser.add_argument('--keep', type=int, default=14)
    args = parser.parse_args()
    os.umask(0o077)
    archive = make_backup(args.database, args.config, args.code, args.units, args.destination, args.keep)
    print(f'Sauvegarde créée et vérifiée : {archive.name}')


if __name__ == '__main__':
    main()
