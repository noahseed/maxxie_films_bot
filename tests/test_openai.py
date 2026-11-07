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
                {'answer': 'Essaie Matrix.', 'film_ids': [1, 999]})}]}]}).encode()
        answer, titles = CinemaAI('test-secret').answer('Un film de science-fiction ?', catalogue=[{'id': 1, 'title': 'Matrix'}])
        self.assertEqual((answer, titles), ('Essaie Matrix.', [1]))
        args = factory.return_value.request.call_args
        self.assertEqual(args.args[:2], ('POST', '/v1/responses'))
        payload = json.loads(args.args[2])
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'], 600)
        self.assertEqual(payload['text']['format']['type'], 'json_schema')
        self.assertEqual(payload['text']['format']['schema']['properties']['film_ids']['items']['type'], 'integer')
        self.assertIn('Matrix', payload['input'][0]['content'])
        self.assertNotIn('file_id', payload['input'][0]['content'])
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
        self.api.reset_mock()
        self.message('Un film de science-fiction ?')
        self.assertFalse(self.future.done())
        self.assertFalse(any(call.args[0] in ('sendMessage', 'sendChatAction')
                             for call in self.api.call.call_args_list))
        self.future.set_result(('Essaie Matrix.', [film_id, 999999]))
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

    def test_ai_receives_only_the_current_channels_indexed_catalogue(self):
        first = self.store.add({'file_id': 'secret-file', 'file_unique_id': 'a'}, 'video', 'Alien 1979')
        second = self.store.add({'file_id': 'other-file', 'file_unique_id': 'b'}, 'video', 'Autre canal')
        self.store.add({'file_id': 'private-file', 'file_unique_id': 'c'}, 'video', 'Non publié')
        self.store.link_channel(-100123, first, 50)
        self.store.link_channel(-100999, second, 60)
        self.callback('assistant')
        self.message('Que me conseilles-tu ?')
        args = self.bot.ai_executor.submit.call_args.args
        self.assertEqual(args[3], [{'id': first, 'title': 'Alien 1979'}])
        self.assertFalse(args[4])
        self.assertNotIn('secret-file', str(args))
        self.assertNotIn('Autre canal', str(args))

    def test_removed_film_does_not_get_a_link_and_model_urls_are_removed(self):
        film_id = self.store.add({'file_id': 'f', 'file_unique_id': 'f'}, 'video', 'Matrix')
        self.store.link_channel(-100123, film_id, 50)
        self.callback('assistant')
        self.message('Matrix ?')
        self.store.remove(film_id)
        self.future.set_result(('Voir Matrix https://t.me/invente/999', [film_id, 999]))
        self.bot.poll_ai()
        response = self.api.call.call_args.kwargs
        self.assertNotIn('https://', response['text'])
        self.assertEqual(response['reply_markup']['inline_keyboard'], [[{'text': '❓ Aide', 'callback_data': 'aide'}]])

    def test_catalogue_context_has_a_bound_and_marks_partial_catalogues(self):
        for number, title in enumerate(('Ancien Matrix', 'Nouveau Alien', 'Nouveau film'), 1):
            film_id = self.store.add({'file_id': str(number), 'file_unique_id': str(number)}, 'video', title)
            self.store.link_channel(-100123, film_id, number * 10)
        rows, partial = self.store.ai_catalogue(-100123, 'Matrix', limit=2)
        self.assertTrue(partial)
        self.assertEqual(len(rows), 2)
        self.assertIn('Ancien Matrix', [row[1] for row in rows])

    def test_empty_catalogue_is_sent_as_empty_without_made_up_links(self):
        self.callback('assistant')
        self.message('Parlons de cinéma')
        self.assertEqual(self.bot.ai_executor.submit.call_args.args[3], [])
        self.future.set_result(('Parlons de cinéma.', [999]))
        self.bot.poll_ai()
        self.assertEqual(len(self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']), 1)

    def test_contact_and_explicit_search_never_call_openai(self):
        self.bot.notify_chat_id = 1
        self.callback('recherche')
        self.message('Matrix')
        self.callback('contact')
        self.message('Bonjour administrateur')
        self.bot.ai_executor.submit.assert_not_called()

    def test_default_text_uses_ai_without_activation(self):
        self.message('Bonjour')
        self.bot.ai_executor.submit.assert_called_once()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM ai_usage').fetchone()[0], 1)

    def test_menu_has_no_ai_button_and_does_not_generate(self):
        self.callback('menu')
        buttons = self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertFalse(any(button.get('callback_data') == 'assistant'
                             for row in buttons for button in row))
        self.bot.ai_executor.submit.assert_not_called()

    def test_menu_returns_from_search_to_default_ai(self):
        self.callback('recherche')
        self.callback('menu')
        self.message('Matrix')
        self.bot.ai_executor.submit.assert_called_once()

    def test_commands_do_not_generate_but_next_text_uses_ai(self):
        self.message('/id')
        self.bot.ai_executor.submit.assert_not_called()
        self.message('Matrix')
        self.bot.ai_executor.submit.assert_called_once()

    def test_expired_history_starts_fresh_automatically(self):
        self.bot.ai_sessions[2] = {'time': 0, 'history': [{'role': 'user', 'content': 'Ancien'}]}
        with patch('bot.time.monotonic', return_value=901):
            self.message('Bonjour')
        self.bot.ai_executor.submit.assert_called_once()
        self.assertEqual(self.bot.ai_executor.submit.call_args.args[2], [])

    def test_non_member_cannot_start_assistant(self):
        self.api.call.return_value = {'status': 'left'}
        self.callback('assistant')
        self.assertNotIn(2, self.bot.ai_sessions)
        self.bot.ai_executor.submit.assert_not_called()

    def test_subscriber_can_chat_without_being_on_an_access_list(self):
        self.callback('assistant')
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
