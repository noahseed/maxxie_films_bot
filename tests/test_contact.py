import unittest
from unittest.mock import Mock, patch

from bot import Bot
from catalogue import Catalogue
from telegram_api import TelegramError


class ContactTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.api.call.return_value = {'status': 'member', 'message_id': 99}
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, {2}, -100123, notify_chat_id=1)
        for user in (1, 2):
            self.store.remember_visitor(user)

    def tearDown(self):
        self.store.db.close()

    def callback(self, data, user=2):
        self.bot.handle({'callback_query': {'id': 'q', 'from': {'id': user}, 'data': data,
            'message': {'chat': {'id': user, 'type': 'private'}}}})

    def message(self, user=2, **fields):
        self.bot.handle({'message': {'chat': {'id': user, 'type': 'private'},
            'from': {'id': user, 'first_name': 'Alice', 'username': 'alice'}, 'message_id': 42, **fields}})

    def copies(self):
        return [c for c in self.api.call.call_args_list if c.args[0] == 'copyMessage']

    def test_contact_button_and_message_are_delivered_privately(self):
        self.callback('menu')
        self.assertIn('contact', str(self.api.call.call_args.kwargs['reply_markup']))
        self.callback('contact')
        self.message(text='Bonjour !')
        self.api.call.assert_any_call('copyMessage', chat_id=1, from_chat_id=2, message_id=42)
        headers = [c.kwargs['text'] for c in self.api.call.call_args_list
                   if c.args[0] == 'sendMessage' and c.kwargs['chat_id'] == 1]
        self.assertIn('Alice', headers[0])
        self.assertIn('@alice', headers[0])
        self.assertIn('Identifiant : 2', headers[0])
        self.assertIn('transmis', self.api.call.call_args.kwargs['text'])

    def test_admin_video_and_following_album_item_are_not_published_in_contact_mode(self):
        self.callback('contact', 1)
        for number in (1, 2):
            self.message(1, video={'file_id': str(number), 'file_unique_id': str(number), 'file_name': 'Film.mp4'})
        self.assertEqual(len(self.copies()), 2)
        self.assertEqual(self.store.search(), [])
        self.assertFalse(any(c.args[0] == 'sendVideo' for c in self.api.call.call_args_list))

    def test_cancel_returns_to_search_instead_of_forwarding(self):
        self.callback('contact')
        self.callback('menu')
        self.message(text='Un film')
        self.assertEqual(self.copies(), [])
        self.assertIn('Aucun film', self.api.call.call_args.kwargs['text'])

    def test_non_member_cannot_start_or_continue_contact(self):
        self.callback('contact')
        self.api.call.return_value = {'status': 'left'}
        self.message(text='Bonjour')
        self.assertEqual(self.copies(), [])
        self.assertFalse(self.store.contact_pending(2))
        self.callback('contact')
        self.assertFalse(self.store.contact_pending(2))

    def test_contact_error_does_not_claim_success(self):
        self.callback('contact')
        def call(method, **params):
            if method == 'copyMessage':
                raise TelegramError(403)
            return {'status': 'member'}
        self.api.call.side_effect = call
        with self.assertLogs('maxxie-films', level='WARNING'):
            self.message(text='Bonjour')
        self.assertIn('n’a pas pu être confirmée', self.api.call.call_args.kwargs['text'])
        self.assertEqual(len(self.copies()), 1)

    def test_removed_film_command_does_not_open_or_send_film(self):
        self.store.add({'file_id': 'file', 'file_unique_id': 'unique'}, 'video', 'Film')
        self.store.link_channel(-100123, 1, 50)
        self.message(text='/film 1')
        self.assertFalse(any(c.args[0] in ('sendMessage', 'sendVideo', 'sendDocument', 'copyMessage')
                             for c in self.api.call.call_args_list))

    def test_contact_expires_after_inactivity(self):
        with patch('catalogue.time.time', return_value=1000):
            self.store.request_contact(2)
        with patch('catalogue.time.time', return_value=1901):
            self.assertFalse(self.store.contact_pending(2))


if __name__ == '__main__':
    unittest.main()
