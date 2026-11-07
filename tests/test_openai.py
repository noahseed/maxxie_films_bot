from concurrent.futures import Future
import json
import unittest
from unittest.mock import Mock, patch

from bot import Bot
from catalogue import Catalogue
from openai_api import CinemaAI, OpenAIError


class OpenAIClientTests(unittest.TestCase):
    @patch('openai_api.http.client.HTTPSConnection')
    def test_responses_request_is_stateless_bounded_and_parsed(self, factory):
        response = factory.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(
                {'answer': 'Essaie Matrix.', 'titles': ['Matrix']})}]}]}).encode()
        answer, titles = CinemaAI('test-secret').answer('Un film de science-fiction ?')
        self.assertEqual((answer, titles), ('Essaie Matrix.', ['Matrix']))
        args = factory.return_value.request.call_args
        self.assertEqual(args.args[:2], ('POST', '/v1/responses'))
        payload = json.loads(args.args[2])
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'], 600)
        self.assertEqual(payload['text']['format']['type'], 'json_schema')
        self.assertNotIn('tools', payload)
        factory.return_value.close.assert_called_once()

    @patch('openai_api.http.client.HTTPSConnection')
    def test_network_errors_hide_secret_and_are_not_retried(self, factory):
        factory.return_value.request.side_effect = OSError('test-secret')
        with self.assertRaises(OpenAIError) as caught:
            CinemaAI('test-secret').answer('Bonjour')
        self.assertNotIn('test-secret', str(caught.exception))
        self.assertEqual(factory.return_value.request.call_count, 1)

    @patch('openai_api.http.client.HTTPSConnection')
    def test_quota_error_is_safe(self, factory):
        response = factory.return_value.getresponse.return_value
        response.status = 429
        response.read.return_value = b'{"error":"private-message"}'
        with self.assertRaises(OpenAIError) as caught:
            CinemaAI('test-secret').answer('Bonjour')
        self.assertEqual(caught.exception.code, 429)
        self.assertNotIn('private-message', str(caught.exception))


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.api.call.return_value = {'status': 'member'}
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, set(), -100123, ai=Mock())
        self.bot.ai_executor.shutdown()
        self.future = Future()
        self.bot.ai_executor = Mock()
        self.bot.ai_executor.submit.return_value = self.future

    def tearDown(self):
        self.store.db.close()

    def callback(self, data):
        self.bot.handle({'callback_query': {'id': 'q', 'from': {'id': 2}, 'data': data,
            'message': {'chat': {'id': 2, 'type': 'private'}}}})

    def message(self, text):
        self.bot.handle({'message': {'chat': {'id': 2, 'type': 'private'},
            'from': {'id': 2}, 'text': text, 'message_id': 10}})

    def test_generation_does_not_block_and_only_verified_channel_links_are_added(self):
        film_id = self.store.add({'file_id': 'f', 'file_unique_id': 'f'}, 'video', 'Matrix 1999 VF')
        self.store.link_channel(-100123, film_id, 50)
        self.callback('assistant')
        self.message('Un film de science-fiction ?')
        self.assertFalse(self.future.done())
        self.assertIn('prépare', self.api.call.call_args.kwargs['text'])
        self.future.set_result(('Essaie Matrix.', ['Matrix', 'Un titre inexistant']))
        self.bot.poll_ai()
        response = self.api.call.call_args.kwargs
        self.assertEqual(response['reply_markup']['inline_keyboard'][0][0]['url'], 'https://t.me/c/123/50')
        self.assertEqual(len(response['reply_markup']['inline_keyboard']), 2)

    def test_menu_cancels_delivery_of_pending_answer(self):
        self.callback('assistant')
        self.message('Bonjour')
        self.callback('menu')
        self.api.reset_mock()
        self.future.set_result(('Réponse tardive', []))
        self.bot.poll_ai()
        self.api.call.assert_not_called()

    def test_contact_and_ordinary_search_never_call_openai(self):
        self.message('Matrix')
        self.callback('contact')
        self.assertEqual(self.bot.ai_executor.submit.call_count, 0)

    def test_non_member_cannot_start_assistant(self):
        self.api.call.return_value = {'status': 'left'}
        self.callback('assistant')
        self.assertNotIn(2, self.bot.ai_sessions)
        self.bot.ai_executor.submit.assert_not_called()

    def test_subscriber_can_chat_without_being_on_an_access_list(self):
        self.callback('assistant')
        self.assertIn(2, self.bot.ai_sessions)
        self.message('Quels films me conseilles-tu ?')
        self.bot.ai_executor.submit.assert_called_once()
        self.future.set_result(('Quel genre de films aimes-tu ?', []))
        self.bot.poll_ai()
        self.assertEqual(self.api.call.call_args.kwargs['chat_id'], 2)
        self.assertIn('Quel genre', self.api.call.call_args.kwargs['text'])

    def test_daily_limits_are_reserved_before_generation(self):
        self.assertTrue(self.store.reserve_ai(2, per_user=1, total=2))
        self.assertFalse(self.store.reserve_ai(2, per_user=1, total=2))
        self.assertTrue(self.store.reserve_ai(3, per_user=1, total=2))
        self.assertFalse(self.store.reserve_ai(4, per_user=1, total=2))

    def test_api_failure_is_reported_without_crashing(self):
        self.callback('assistant')
        self.message('Bonjour')
        self.future.set_exception(OpenAIError(429))
        with self.assertLogs('maxxie-films', level='WARNING'):
            self.bot.poll_ai()
        self.assertIn('indisponible', self.api.call.call_args.kwargs['text'])

    def test_user_leaving_channel_during_generation_does_not_receive_answer(self):
        self.callback('assistant')
        self.message('Bonjour')
        self.future.set_result(('Réponse privée', []))
        self.api.call.return_value = {'status': 'left'}
        self.bot.poll_ai()
        self.assertIn('pour utiliser le bot', self.api.call.call_args.kwargs['text'])


if __name__ == '__main__':
    unittest.main()
