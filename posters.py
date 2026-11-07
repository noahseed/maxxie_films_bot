"""Recherche TMDB et téléchargement borné des jaquettes JPEG."""
from difflib import SequenceMatcher
import hashlib
import http.client
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode

from search import words
from telegram_api import connect_ipv4

MAX_POSTER_BYTES = 5_000_000


class PosterError(Exception):
    def __init__(self, code=0):
        self.code = code
        super().__init__(f'Jaquette indisponible (code {code})')


def movie_query(title):
    cleaned = re.sub(r'(?i)\.(mp4|mkv|avi)$', '', title).replace('.', ' ').replace('_', ' ')
    years = list(re.finditer(r'\b(?:19|20)\d{2}\b', cleaned))
    year = ''
    if years and cleaned[:years[-1].start()].strip(' -[('):
        match = years[-1]
        year, cleaned = match.group(), cleaned[:match.start()]
    cleaned = re.split(r'(?i)\b(?:2160p|1080p|720p|4k|vf|vff|vfi|vostfr|multi|bluray|brrip|webrip|web[ -]?dl|x26[45]|h26[45])\b', cleaned)[0]
    return cleaned.strip(' -[()]'), year


def select_movie(results, query, year, require_poster=True):
    expected = ' '.join(words(query))
    candidates = []
    for film in results:
        if not isinstance(film, dict) or not isinstance(film.get('id'), int) or film['id'] <= 0:
            continue
        if year and str(film.get('release_date', ''))[:4] != year:
            continue
        if require_poster and not re.fullmatch(r'/[A-Za-z0-9_-]+\.jpg', film.get('poster_path') or ''):
            continue
        score = max((SequenceMatcher(None, expected, ' '.join(words(film.get(key) or '')),
                                     autojunk=False).ratio() for key in ('title', 'original_title')), default=0)
        if score >= 0.93:
            candidates.append((score, film))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.03
                          and candidates[0][1]['id'] != candidates[1][1]['id']):
        return None
    return candidates[0][1]


class TMDBPosters:
    def __init__(self, token, directory):
        if not token or any(c.isspace() for c in token):
            raise ValueError('Jeton TMDB invalide')
        self._token, self.directory = token, Path(directory)

    def _get(self, host, path, image=False):
        connection = http.client.HTTPSConnection(host, timeout=3)
        connection._create_connection = connect_ipv4
        headers = {'Accept': 'image/jpeg' if image else 'application/json'}
        if not image:
            headers['Authorization'] = 'Bearer ' + self._token
        try:
            connection.connect()
            connection.sock.settimeout(8)
            connection.request('GET', path, headers=headers)
            response = connection.getresponse()
            maximum = MAX_POSTER_BYTES if image else 1_000_000
            body = response.read(maximum + 1)
            if response.status != 200:
                raise PosterError(response.status)
            if len(body) > maximum or (image and (not body.startswith(b'\xff\xd8\xff') or
                    response.getheader('Content-Type', '').split(';')[0] != 'image/jpeg')):
                raise PosterError()
            return body
        except (OSError, http.client.HTTPException):
            raise PosterError() from None
        finally:
            connection.close()

    def lookup(self, title, require_poster=False):
        query, year = movie_query(title)
        if not query:
            return None
        params = {'query': query, 'language': 'fr-FR', 'include_adult': 'false'}
        if year:
            params['primary_release_year'] = year
        try:
            result = json.loads(self._get('api.themoviedb.org', '/3/search/movie?' + urlencode(params)))
            movie = select_movie(result.get('results', []), query, year, require_poster)
        except (ValueError, AttributeError, TypeError):
            raise PosterError() from None
        return movie

    def synopsis(self, title):
        movie = self.lookup(title)
        if not movie or not isinstance(movie.get('overview'), str) or not movie['overview'].strip():
            return None
        return {'id': movie['id'], 'overview': movie['overview'].strip()}

    def download(self, title):
        movie = self.lookup(title, require_poster=True)
        if not movie:
            return None
        query, _ = movie_query(title)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        image_path = movie['poster_path']
        digest = hashlib.sha256(image_path.encode()).hexdigest()[:16]
        target = self.directory / f'{movie["id"]}-{digest}.jpg'
        valid_cache = target.is_file() and 0 < target.stat().st_size <= MAX_POSTER_BYTES
        if valid_cache:
            with target.open('rb') as stream:
                valid_cache = stream.read(3) == b'\xff\xd8\xff'
        if not valid_cache:
            body = self._get('image.tmdb.org', '/t/p/w500' + image_path, image=True)
            with tempfile.NamedTemporaryFile(dir=self.directory, prefix='.poster-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(body)
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        for old in sorted(self.directory.glob('*.jpg'), key=lambda path: path.stat().st_mtime, reverse=True)[500:]:
            if old != target:
                old.unlink()
        return {'path': target, 'title': movie.get('title') or query, 'id': movie['id']}
