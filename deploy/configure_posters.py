"""Configurer le jeton TMDB pour les jaquettes du bot films."""
from getpass import getpass
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from posters import TMDBPosters, PosterError


def main():
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise SystemExit('Exécute ce script avec sudo dans un terminal interactif.')
    target = Path('/etc/maxxie-films-tmdb.env')
    if target.exists():
        raise SystemExit('La configuration TMDB existe déjà ; aucune modification effectuée.')
    token = getpass('API Read Access Token TMDB (saisie masquée) : ').strip()
    try:
        client = TMDBPosters(token, '/var/lib/maxxie-films-bot/posters')
        client._get('api.themoviedb.org', '/3/configuration')
    except (ValueError, PosterError):
        raise SystemExit('Vérification TMDB impossible. Aucun fichier créé.') from None
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(f'TMDB_READ_TOKEN={token}\n')
    print('Jeton TMDB vérifié. Activer : sudo systemctl restart maxxie-films-bot')


if __name__ == '__main__':
    main()
