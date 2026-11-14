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
        self.store.link_channel(-100123, 1, 50)
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
            for route in ('film:1', 'rejoindre:1'):
                with self.subTest(member=member, route=route):
                    self.member = member
                    self.api.reset_mock()
                    if route.startswith('/'):
                        self.bot.handle({'message': {'chat': {'id': 2, 'type': 'private'},
                            'from': {'id': 2}, 'text': route}})
                    else:
                        self.callback(route)
                    self.assertEqual(self.sent_films(), [])
                    response = self.api.call.call_args.kwargs
                    self.assertEqual('https://t.me/c/123/50' in str(response), allowed)
                    self.api.call.assert_any_call('getChatMember', chat_id=-100123, user_id=2)

    def test_join_button_rechecks_and_leaving_blocks_next_use(self):
        for status, expected in [('left', False), ('left', False), ('member', True), ('left', False)]:
            self.member = {'status': status}
            self.callback('abonnement')
            response = self.api.call.call_args.kwargs
            self.assertEqual('recherche' in str(response['reply_markup']), expected)
        markup = self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertEqual(markup[0][0]['url'], 'https://t.me/maxxie_films')
        self.assertEqual(markup[2][0]['callback_data'], 'abonnement')

    def test_telegram_failure_blocks_send_and_offers_retry(self):
        self.member = TelegramError(403)
        self.callback('film:1')
        self.assertEqual(self.sent_films(), [])
        self.assertIn('indisponible', self.api.call.call_args.kwargs['text'])
        self.assertEqual(self.api.call.call_args.kwargs['reply_markup']['inline_keyboard'][0][0]['callback_data'], 'abonnement')

    def test_menu_and_search_use_buttons_without_slash_instructions(self):
        self.callback('menu')
        response = self.api.call.call_args.kwargs
        self.assertNotIn('/', response['text'])
        rows = response['reply_markup']['inline_keyboard']
        self.assertEqual([b['callback_data'] for b in rows[0]], ['recherche', 'regles'])
        self.callback('recherche')
        self.bot.handle({'message': {'chat': {'id': 2, 'type': 'private'},
            'from': {'id': 2}, 'text': 'Un film'}})
        self.assertEqual(self.api.call.call_args.kwargs['reply_markup']['inline_keyboard'][0][0]['url'], 'https://t.me/c/123/50')

    def test_help_button_and_slash_aliases_list_available_commands(self):
        for action in ('aide', '/aide', '/help'):
            if action.startswith('/'):
                self.bot.handle({'message': {'chat': {'id': 2, 'type': 'private'},
                    'from': {'id': 2}, 'text': action}})
            else:
                self.callback(action)
            response = self.api.call.call_args.kwargs
            for command in ('/start', '/aide', '/help', '/recherche', '/id'):
                self.assertIn(command, response['text'])
            for removed in ('/film', '/catalogue', '/publier', '/supprimer'):
                self.assertNotIn(removed, response['text'])
            self.assertEqual(response['reply_markup']['inline_keyboard'][3][2],
                             {'text': '❓ Aide', 'callback_data': 'aide'})

    def test_random_button_uses_only_channel_films(self):
        other = self.store.add({'file_id': 'other', 'file_unique_id': 'other'}, 'video', 'Autre canal')
        self.store.link_channel(-100999, other, 99)
        self.callback('menu')
        row = self.api.call.call_args.kwargs['reply_markup']['inline_keyboard'][1]
        self.assertEqual(row[0]['url'], 'https://t.me/maxxie_films')
        self.assertEqual(row[1]['callback_data'], 'hasard')
        self.callback('hasard')
        response = self.api.call.call_args.kwargs
        self.assertIn('Un film', response['text'])
        self.assertEqual(response['reply_markup']['inline_keyboard'][0][0]['url'], 'https://t.me/c/123/50')
        self.assertEqual(response['reply_markup']['inline_keyboard'][1][0]['callback_data'], 'hasard')

    def test_random_displays_saved_synopsis_under_title(self):
        self.store.queue_synopses(-100123)
        self.store.synopsis_status(-100123, 50, 'done', 'Un film\n\nUn résumé du film.')
        self.callback('hasard')
        response = self.api.call.call_args.kwargs
        self.assertIn('🎬 Un film\n\nUn résumé du film.', response['text'])
        self.store.synopsis_status(-100123, 50, 'not_found')
        self.callback('hasard')
        self.assertIn('Synopsis indisponible', self.api.call.call_args.kwargs['text'])

    def test_random_handles_empty_catalogue_and_requires_membership(self):
        self.store.remove(1)
        self.callback('hasard')
        self.assertIn('Aucun film', self.api.call.call_args.kwargs['text'])
        self.member = {'status': 'left'}
        self.callback('hasard')
        self.assertIn('pour utiliser le bot', self.api.call.call_args.kwargs['text'])

    def test_non_admin_cannot_use_administration_buttons(self):
        for action in ('publier:1', 'retirer:1', 'confirmer_retrait:1'):
            self.callback(action)
        self.assertIsNotNone(self.store.get(1))
        self.assertEqual(self.sent_films(), [])
        self.bot.list_films(2, 'Un film')
        self.assertNotIn('retirer:', str(self.api.call.call_args.kwargs))

    def test_admin_actions_are_disabled_even_from_old_buttons_and_commands(self):
        for action in ('publier:1', 'retirer:1', 'confirmer_retrait:1'):
            self.callback(action, 1)
        for command in ('/publier 1', '/supprimer 1'):
            self.bot.handle({'message': {'chat': {'id': 1, 'type': 'private'},
                'from': {'id': 1}, 'text': command}})
        self.assertIsNotNone(self.store.get(1))
        self.assertEqual(self.sent_films(), [])
        self.bot.list_films(1, 'Un film')
        response = self.api.call.call_args.kwargs
        self.assertNotIn('retirer:', str(response))
        self.assertNotIn('publier:', str(response))
        self.assertEqual(response['reply_markup']['inline_keyboard'][0][0]['url'], 'https://t.me/c/123/50')

    def test_non_member_cannot_use_menu_search_help_id_or_send_media(self):
        self.member = {'status': 'left'}
        for user in (1, 2):
            for command in ('/start', '/id', '/recherche Un film', 'Un film'):
                self.bot.handle({'message': {'chat': {'id': user, 'type': 'private'},
                    'from': {'id': user}, 'text': command}})
                self.assertIn('pour utiliser le bot', self.api.call.call_args.kwargs['text'])
            for action in ('menu', 'aide', 'recherche'):
                self.callback(action, user)
                self.assertIn('pour utiliser le bot', self.api.call.call_args.kwargs['text'])
            self.bot.handle({'message': {'chat': {'id': user, 'type': 'private'},
                'from': {'id': user}, 'video': {'file_id': 'new', 'file_unique_id': 'new', 'file_name': 'Nouveau.mp4'}}})
            self.assertEqual(self.store.search('Nouveau'), [])
        self.assertEqual(self.sent_films(), [])

    def test_search_only_lists_films_published_in_this_channel(self):
        other = self.store.add({'file_id': 'two', 'file_unique_id': 'two'}, 'video', 'Autre film')
        self.store.link_channel(-100999, other, 60)
        self.store.add({'file_id': 'three', 'file_unique_id': 'three'}, 'video', 'Film non publié')
        self.bot.list_films(2, 'film')
        buttons = self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertEqual(len(buttons), 3)
        self.assertEqual(buttons[0][0]['url'], 'https://t.me/c/123/50')

    def test_channel_search_matches_accents_and_literal_wildcards(self):
        film_id = self.store.add({'file_id': 'summer', 'file_unique_id': 'summer'}, 'video', 'Été 100%')
        self.store.link_channel(-100123, film_id, 70)
        self.assertEqual(self.store.search_channel(-100123, 'ete'), [(film_id, 'Été 100%', 70)])
        self.assertEqual(self.store.search_channel(-100123, '%'), [(film_id, 'Été 100%', 70)])

    def test_command_lists_are_removed_for_default_and_private_scopes(self):
        clear_commands(self.api)
        self.assertEqual(self.api.call.call_count, 4)
        self.api.call.assert_any_call('deleteMyCommands', scope={'type': 'default'}, language_code='')
        self.api.call.assert_any_call('deleteMyCommands', scope={'type': 'all_private_chats'}, language_code='fr')


if __name__ == '__main__':
    unittest.main()
