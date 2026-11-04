import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

from bot import Bot
from catalogue import Catalogue
from telegram_api import TelegramError


def message(user_id=3, text='/start', **profile):
    return {'message': {'chat': {'id': user_id, 'type': 'private'},
                        'from': {'id': user_id, **profile}, 'text': text}}


class VisitorTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.api.call.return_value = {'status': 'member'}
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, {2}, -100123, notify_chat_id=1)

    def tearDown(self):
        self.store.db.close()

    def notices(self):
        return [c for c in self.api.call.call_args_list
                if c.args[0] == 'sendMessage' and c.kwargs['chat_id'] == 1]

    def test_first_visitor_is_reported_once_even_before_access_is_granted(self):
        update = message(first_name='Alice', last_name='Dupont', username='alice')
        self.bot.handle(update)
        self.bot.handle(update)
        self.assertEqual(len(self.notices()), 1)
        text = self.notices()[0].kwargs['text']
        for part in ('Alice Dupont', '@alice', 'Identifiant : 3'):
            self.assertIn(part, text)
        self.assertEqual(self.api.call.call_args.kwargs['chat_id'], 3)

    def test_new_user_with_no_username_is_supported(self):
        self.bot.handle(message())
        self.assertIn('Non renseigné', self.notices()[0].kwargs['text'])

    def test_restarting_keeps_known_visitors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalogue.sqlite3'
            store = Catalogue(path)
            bot = Bot(self.api, store, {1}, {2}, -100123, notify_chat_id=1)
            bot.handle(message())
            store.db.close()
            store = Catalogue(path)
            try:
                bot = Bot(self.api, store, {1}, {2}, -100123, notify_chat_id=1)
                bot.handle(message())
                self.assertEqual(len(self.notices()), 1)
            finally:
                store.db.close()

    def test_notification_failure_does_not_interrupt_visitor_or_repeat(self):
        def call(method, **params):
            if method == 'sendMessage' and params['chat_id'] == 1:
                raise TelegramError(403)
            return {'status': 'member'}
        self.api.call.side_effect = call
        with self.assertLogs('maxxie-films', level='WARNING'):
            self.bot.handle(message())
        self.bot.handle(message())
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(self.api.call.call_args.kwargs['chat_id'], 3)

    def test_channel_posts_do_not_trigger_visitor_notifications(self):
        self.bot.handle({'channel_post': {'chat': {'id': -100123, 'type': 'channel'}, 'message_id': 1}})
        self.api.call.assert_not_called()

    def test_removed_catalogue_buttons_and_pages_only_open_menu(self):
        self.store.add({'file_id': 'file', 'file_unique_id': 'unique'}, 'video', 'Un film')
        for data in ('catalogue', 'page:1'):
            self.bot.handle({'callback_query': {'id': 'q', 'from': {'id': 2}, 'data': data,
                'message': {'chat': {'id': 2, 'type': 'private'}}}})
            response = self.api.call.call_args.kwargs
            self.assertNotIn('catalogue', str(response['reply_markup']))
            self.assertNotIn('film:', str(response['reply_markup']))
            self.assertNotIn('catalogue', response['text'].lower())


if __name__ == '__main__':
    unittest.main()
