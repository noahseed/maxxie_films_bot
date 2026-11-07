"""Créer le rôle et la base locale dédiés au bot (sudo, sans mot de passe réseau)."""
import os
import subprocess


def setup():
    if os.geteuid() != 0:
        raise SystemExit('Exécute ce script avec sudo.')
    def exists(query):
        return subprocess.check_output(['runuser', '-u', 'postgres', '--', 'psql', '-XAt',
            '-v', 'ON_ERROR_STOP=1', '-c', query], text=True).strip() == '1'
    if not exists("SELECT 1 FROM pg_roles WHERE rolname='maxxie-films-bot'"):
        subprocess.run(['runuser', '-u', 'postgres', '--', 'createuser', '--no-superuser',
            '--no-createdb', '--no-createrole', 'maxxie-films-bot'], check=True)
    if not exists("SELECT 1 FROM pg_database WHERE datname='maxxie_films'"):
        subprocess.run(['runuser', '-u', 'postgres', '--', 'createdb',
            '--owner=maxxie-films-bot', 'maxxie_films'], check=True)
    print('Base PostgreSQL locale maxxie_films prête.')


if __name__ == '__main__':
    setup()
