"""Assistant cinéma via Responses API ; aucun journal de texte ou de clé."""
import http.client
import json

from telegram_api import connect_ipv4


class OpenAIError(Exception):
    def __init__(self, code=0):
        self.code = code
        super().__init__(f'OpenAI indisponible (code {code})')


class CinemaAI:
    def __init__(self, key, model='gpt-4.1-mini'):
        if not key or any(c.isspace() for c in key):
            raise ValueError('Clé OpenAI invalide')
        self._key, self.model = key, model

    def answer(self, question, history=()):
        schema = {'type': 'object', 'properties': {
            'answer': {'type': 'string'},
            'titles': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['answer', 'titles'], 'additionalProperties': False}
        payload = {'model': self.model, 'store': False, 'max_output_tokens': 600,
            'instructions': 'Tu es un assistant cinéma francophone. Réponds brièvement sur les films, '
                'leurs acteurs, genres et recommandations. Reste dans le domaine du cinéma. '
                'Ne prétends jamais connaître la disponibilité d’un film dans le canal Telegram, '
                'ne crée aucun lien ni aucune commande. Le bot cherchera lui-même les films. '
                'Donne dans titles au plus cinq titres précis pertinents à rechercher. '
                'Si aucun titre précis ne convient, utilise une liste vide. '
                'Ne demande ni identifiants ni secrets. Réponds en texte simple.',
            'input': list(history)[-4:] + [{'role': 'user', 'content': question[:2000]}],
            'text': {'format': {'type': 'json_schema', 'name': 'cinema_answer',
                                'strict': True, 'schema': schema}}}
        connection = http.client.HTTPSConnection('api.openai.com', timeout=3)
        connection._create_connection = connect_ipv4
        try:
            connection.connect()
            connection.sock.settimeout(25)
            connection.request('POST', '/v1/responses', json.dumps(payload).encode(),
                {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self._key})
            response = connection.getresponse()
            body = response.read(2_000_000)
            if response.status != 200:
                raise OpenAIError(response.status)
            result = json.loads(body)
            if result.get('status') != 'completed':
                raise OpenAIError()
            output = ''.join(part.get('text', '') for item in result.get('output', [])
                if item.get('type') == 'message' for part in item.get('content', [])
                if part.get('type') == 'output_text')
            content = json.loads(output)
            if not isinstance(content.get('answer'), str) or not content['answer'].strip():
                raise OpenAIError()
            titles = content.get('titles', [])
            if not isinstance(titles, list) or any(not isinstance(title, str) for title in titles):
                raise OpenAIError()
            return content['answer'].strip()[:3500], [title[:200] for title in titles[:5]]
        except (OSError, http.client.HTTPException, ValueError, TypeError, AttributeError):
            raise OpenAIError() from None
        finally:
            connection.close()
