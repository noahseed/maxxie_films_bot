import unittest
from unittest.mock import Mock

from bot import Bot, clear_commands
from catalogue import Catalogue
from telegram_api import TelegramError


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, {2}, -100123)
        self.store.add({'file_id': 'file', 'file_unique_id': 'unique'}, 'video', 'Un film')
        self.member = {'status': 'member'}
        def call(method, **params):
            if method == 'getChatMember':
                if isinstance(self.member, Exception):
                    raise self.member
                return self.member
            return True
        self.api.call.side_effect = call

    def tearDown(self):
        self.store.db.close()

    def callback(self, data, user=2):
        self.bot.handle({'callback_query': {'id': 'q', 'from': {'id': user}, 'data': data,
            'message': {'chat': {'id': user, 'type': 'private'}}}})

    def sent_films(self):
        return [c for c in self.api.call.call_args_list if c.args[0] in ('sendVideo', 'sendDocument')]

    def test_membership_required_for_every_status_and_download_route(self):
        for member, allowed in [({'status': 'member'}, True), ({'status': 'creator'}, True),
                ({'status': 'administrator'}, True), ({'status': 'restricted', 'is_member': True}, True),
                ({'status': 'left'}, False), ({'status': 'kicked'}, False),
                ({'status': 'restricted', 'is_member': False}, False), ({}, False)]:
            for route in ('film:1', 'rejoindre:1', '/film 1'):
                with self.subTest(member=member, route=route):
                    self.member = member
                    self.api.reset_mock()
                    if route.startswith('/'):
                        self.bot.handle({'message': {'chat': {'id': 2, 'type': 'private'},
                            'from': {'id': 2}, 'text': route}})
                    else:
                        self.callback(route)
                    self.assertEqual(bool(self.sent_films()), allowed)
                    self.api.call.assert_any_call('getChatMember', chat_id=-100123, user_id=2)

    def test_join_button_rechecks_and_leaving_blocks_next_download(self):
        for status, expected in [('left', 0), ('left', 0), ('member', 1), ('left', 1)]:
            self.member = {'status': status}
            self.callback('rejoindre:1')
            self.assertEqual(len(self.sent_films()), expected)
        markup = self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertEqual(markup[0][0]['url'], 'https://t.me/maxxie_films')
        self.assertEqual(markup[1][0]['callback_data'], 'rejoindre:1')

    def test_telegram_failure_blocks_send_and_offers_retry(self):
        self.member = TelegramError(403)
        self.callback('film:1')
        self.assertEqual(self.sent_films(), [])
        self.assertIn('indisponible', self.api.call.call_args.kwargs['text'])
        self.assertEqual(self.api.call.call_args.kwargs['reply_markup']['inline_keyboard'][0][0]['callback_data'], 'rejoindre:1')

    def test_menu_and_search_use_buttons_without_slash_instructions(self):
        self.callback('menu')
        response = self.api.call.call_args.kwargs
        self.assertNotIn('/', response['text'])
        rows = response['reply_markup']['inline_keyboard']
        self.assertEqual([b['callback_data'] for b in rows[0]], ['catalogue', 'aide'])
        self.assertEqual(rows[1][0]['callback_data'], 'recherche')
        self.callback('recherche')
        self.bot.handle({'message': {'chat': {'id': 2, 'type': 'private'},
            'from': {'id': 2}, 'text': 'Un film'}})
        self.assertEqual(self.api.call.call_args.kwargs['reply_markup']['inline_keyboard'][0][0]['callback_data'], 'film:1')

    def test_non_admin_cannot_use_administration_buttons(self):
        for action in ('publier:1', 'retirer:1', 'confirmer_retrait:1'):
            self.callback(action)
        self.assertIsNotNone(self.store.get(1))
        self.assertEqual(self.sent_films(), [])
        self.callback('catalogue')
        self.assertNotIn('retirer:', str(self.api.call.call_args.kwargs))

    def test_admin_removal_requires_confirmation(self):
        self.callback('retirer:1', 1)
        self.assertIsNotNone(self.store.get(1))
        self.callback('confirmer_retrait:1', 1)
        self.assertIsNone(self.store.get(1))

    def test_command_lists_are_removed_for_default_and_private_scopes(self):
        clear_commands(self.api)
        self.assertEqual(self.api.call.call_count, 4)
        self.api.call.assert_any_call('deleteMyCommands', scope={'type': 'default'}, language_code='')
        self.api.call.assert_any_call('deleteMyCommands', scope={'type': 'all_private_chats'}, language_code='fr')


if __name__ == '__main__':
    unittest.main()
