"""Client Telegram avec connexions réutilisées, sans secrets dans les erreurs."""
import http.client
import json
import logging
import re
import socket
import time
import secrets
from pathlib import Path

LOG = logging.getLogger('maxxie-films')
READ_METHODS = frozenset({'getMe', 'getChat', 'getChatMember', 'getWebhookInfo',
                          'getMyCommands', 'getUpdates'})


class TelegramError(Exception):
    def __init__(self, code, retry_after=None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"Telegram : erreur {code}")


def connect_ipv4(address, timeout, source_address=None):
    """Éviter les délais intermittents IPv6 sans modifier le réseau du VPS."""
    host, port = address
    last_error = None
    for family, kind, protocol, _, target in socket.getaddrinfo(
            host, port, socket.AF_INET, socket.SOCK_STREAM):
        connection = socket.socket(family, kind, protocol)
        connection.settimeout(timeout)
        try:
            if source_address:
                connection.bind(source_address)
            connection.connect(target)
            return connection
        except OSError as error:
            last_error = error
            connection.close()
    raise last_error or OSError('Aucune adresse IPv4 disponible')


class Telegram:
    def __init__(self, token):
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise ValueError("Format du jeton Telegram invalide")
        self._path = f"/bot{token}/"
        self._connection = None
        self._last_used = 0

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def call(self, method, **params):
        upload = params.pop('_upload', None)
        upload_field = params.pop('_upload_field', 'photo')
        if upload_field not in ('photo', 'cover'):
            raise ValueError('Champ de fichier invalide')
        if upload is None:
            request_body = json.dumps(params).encode('utf-8')
            headers = {'Content-Type': 'application/json'}
        else:
            boundary = 'maxxie-' + secrets.token_hex(16)
            chunks = []
            for key, value in params.items():
                value = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{upload_field}"; filename="poster.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode(),
                           upload, f'\r\n--{boundary}--\r\n'.encode()])
            request_body = b''.join(chunks)
            headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary}
        started = time.monotonic()
        read_timeout = params.get('timeout', 30) + 5 if method == 'getUpdates' else 8
        # Seules les lectures peuvent être retentées. Un envoi incertain
        # ne doit jamais être répété implicitement.
        for attempt in range(2):
            if self._connection is not None and time.monotonic() - self._last_used > 20:
                self.close()
            if self._connection is None:
                self._connection = http.client.HTTPSConnection('api.telegram.org', timeout=3)
                self._connection._create_connection = connect_ipv4
            connection = self._connection
            try:
                if connection.sock is None:
                    connection.connect()
                connection.sock.settimeout(read_timeout)
                connection.request('POST', self._path + method,
                                   request_body, headers)
                response = connection.getresponse()
                body = response.read()
                status = response.status
                self._last_used = time.monotonic()
                if response.will_close:
                    self.close()
                result = json.loads(body)
            except (OSError, http.client.HTTPException, ValueError):
                self.close()
                if method in READ_METHODS and attempt == 0:
                    continue
                LOG.warning('Appel %s en échec après %.2fs.', method, time.monotonic() - started)
                raise TelegramError(0) from None
            elapsed = time.monotonic() - started
            if method != 'getUpdates' and elapsed > 1:
                LOG.warning('Appel %s lent : %.2fs.', method, elapsed)
            if not isinstance(result, dict):
                self.close()
                raise TelegramError(0)
            if not result.get('ok'):
                raise TelegramError(result.get('error_code', status),
                                    result.get('parameters', {}).get('retry_after'))
            if 'result' not in result:
                self.close()
                raise TelegramError(0)
            return result['result']

    def send_photo(self, chat_id, path, caption, message_id):
        with Path(path).open('rb') as stream:
            body = stream.read(5_000_001)
        if len(body) > 5_000_000 or not body.startswith(b'\xff\xd8\xff'):
            raise ValueError('Fichier de jaquette invalide')
        return self.call('sendPhoto', chat_id=chat_id, caption=caption[:1024],
                         reply_parameters={'message_id': message_id}, _upload=body)

    def edit_video_cover(self, chat_id, message_id, media, path):
        if media.get('type') != 'video' or not media.get('media'):
            raise ValueError('Référence vidéo invalide')
        with Path(path).open('rb') as stream:
            body = stream.read(5_000_001)
        if len(body) > 5_000_000 or not body.startswith(b'\xff\xd8\xff'):
            raise ValueError('Fichier de couverture invalide')
        updated = dict(media, cover='attach://cover')
        return self.call('editMessageMedia', chat_id=chat_id, message_id=message_id,
                         media=updated, _upload=body, _upload_field='cover')
