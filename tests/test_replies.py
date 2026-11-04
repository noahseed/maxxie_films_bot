import unittest
from unittest.mock import Mock, patch
from bot import Bot
from catalogue import Catalogue
from telegram_api import TelegramError


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.api.call.return_value = {'status': 'member', 'message_id': 99}
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, {2, 3}, -100123, notify_chat_id=1)
        for user in (1, 2, 3):
            self.store.remember_visitor(user)
        self.token = self.store.create_contact_thread(1, 2)

    def tearDown(self):
        self.store.db.close()

    def callback(self, data, user=1):
        self.bot.handle({'callback_query': {'id': 'q', 'from': {'id': user}, 'data': data,
            'message': {'chat': {'id': user, 'type': 'private'}}}})

    def message(self, **fields):
        self.bot.handle({'message': {'chat': {'id': 1, 'type': 'private'},
            'from': {'id': 1}, 'message_id': 77, **fields}})

    def copies(self):
        return [c for c in self.api.call.call_args_list if c.args[0] == 'copyMessage']

    def test_owner_button_and_reply_use_recorded_recipient(self):
        self.callback('repondre:' + self.token)
        self.message(text='Bonjour Alice')
        self.api.call.assert_any_call('copyMessage', chat_id=2, from_chat_id=1, message_id=77)
        self.assertIn('Réponse transmise', self.api.call.call_args.kwargs['text'])

    def test_other_user_or_forged_token_cannot_select_a_recipient(self):
        self.callback('repondre:' + self.token, 3)
        self.assertIsNone(self.store.reply_target(3))
        self.callback('repondre:2')
        self.assertIsNone(self.store.reply_target(1))
        self.assertEqual(self.copies(), [])

    def test_reply_video_is_not_published_and_menu_cancels_reply_mode(self):
        self.callback('repondre:' + self.token)
        self.message(video={'file_id': 'v', 'file_unique_id': 'v', 'file_name': 'Video.mp4'})
        self.assertEqual(len(self.copies()), 1)
        self.assertEqual(self.store.search(), [])
        self.callback('menu')
        self.assertIsNone(self.store.reply_target(1))

    def test_expired_thread_is_not_usable(self):
        with patch('catalogue.time.time', return_value=1):
            token = self.store.create_contact_thread(1, 2)
        self.callback('repondre:' + token)
        self.assertIsNone(self.store.reply_target(1))

    def test_recipient_that_left_channel_does_not_receive_reply(self):
        self.callback('repondre:' + self.token)
        self.api.call.side_effect = lambda method, **params: (
            {'status': 'left' if params['user_id'] == 2 else 'member'}
            if method == 'getChatMember' else True)
        self.message(text='Bonjour')
        self.assertEqual(self.copies(), [])
        self.assertIn('doit rejoindre', self.api.call.call_args.kwargs['text'])

    def test_send_failure_is_not_reported_as_success(self):
        self.callback('repondre:' + self.token)
        def call(method, **params):
            if method == 'copyMessage':
                raise TelegramError(403)
            return {'status': 'member'}
        self.api.call.side_effect = call
        with self.assertLogs('maxxie-films', level='WARNING'):
            self.message(text='Bonjour')
        self.assertIn('n’a pas pu être confirmée', self.api.call.call_args.kwargs['text'])
        self.assertEqual(len(self.copies()), 1)


if __name__ == '__main__':
    unittest.main()
