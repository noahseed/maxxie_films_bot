import unittest
from unittest.mock import Mock

from bot import Bot, verify_channel, film_title
from catalogue import Catalogue


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, {2}, -100123)
        self.media = {'file_id': 'file', 'file_unique_id': 'unique'}

    def tearDown(self):
        self.store.db.close()

    def post(self, **fields):
        return {'chat': {'id': -100123, 'type': 'channel'},
                'message_id': 50, 'video': self.media, 'caption': 'Un film', **fields}

    def test_index_and_edit_without_posting_messages(self):
        self.bot.handle({'channel_post': self.post()})
        self.bot.handle({'edited_channel_post': self.post(caption='Nouveau titre')})
        self.assertEqual(self.store.search(), [(1, 'Nouveau titre')])
        self.assertEqual(self.store.channel_message(-100123, 1), 50)
        self.api.call.assert_not_called()

    def test_other_channel_is_ignored(self):
        self.bot.handle({'channel_post': self.post(chat={'id': -100999, 'type': 'channel'})})
        self.assertEqual(self.store.search(), [])

    def test_filename_is_used_and_published_automatically_once(self):
        self.api.call.side_effect = lambda method, **kw: (
            {'status': 'creator'} if method == 'getChatMember' else {'message_id': 80})
        update = {'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'},
            'video': {**self.media, 'file_name': 'Mon Film.MP4'}, 'caption': 'Autre légende'}}
        self.bot.handle(update)
        self.bot.handle(update)
        sends = [c for c in self.api.call.call_args_list if c.args[0] == 'sendVideo']
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0].kwargs, {'chat_id': -100123, 'video': 'file', 'caption': 'Mon Film'})
        self.assertEqual(self.store.search(), [(1, 'Mon Film')])

    def test_title_removes_only_final_mp4_suffix(self):
        self.assertEqual(film_title({}, {'file_name': 'Film.mp4.version.mp4'}), 'Film.mp4.version')
        self.assertEqual(film_title({}, {'file_name': 'Film.mkv'}), 'Film.mkv')
        self.assertEqual(film_title({'caption': 'Titre de secours'}, {}), 'Titre de secours')

    def test_document_filename_is_published_without_caption(self):
        self.api.call.side_effect = lambda method, **kw: (
            {'status': 'creator'} if method == 'getChatMember' else {'message_id': 80})
        self.bot.handle({'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'},
            'document': {**self.media, 'mime_type': 'video/mp4', 'file_name': 'Un film.mp4'}}})
        sends = [c for c in self.api.call.call_args_list if c.args[0] == 'sendDocument']
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0].kwargs['caption'], 'Un film')

    def test_video_without_name_or_caption_is_not_published(self):
        self.bot.handle({'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'},
                                     'video': self.media}})
        self.assertEqual(self.store.search(), [])
        self.assertEqual(self.api.call.call_args.args[0], 'sendMessage')

    def test_admin_can_index_forwarded_history_without_republishing(self):
        self.bot.handle({'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'},
            'video': self.media, 'caption': 'Ancien film',
            'forward_origin': {'type': 'channel', 'chat': {'id': -100123}, 'message_id': 20}}})
        self.assertEqual(self.store.channel_message(-100123, 1), 20)
        self.assertEqual(self.api.call.call_count, 1)
        self.assertEqual(self.api.call.call_args.args[0], 'sendMessage')

    def test_publish_checks_channel_rights_and_prevents_duplicate(self):
        self.store.add(self.media, 'video', 'Un film')
        self.api.call.side_effect = lambda method, **kw: (
            {'status': 'creator'} if method == 'getChatMember' else {'message_id': 80})
        self.bot.publish(1, '1')
        self.bot.publish(1, '1')
        sends = [c for c in self.api.call.call_args_list if c.args[0] == 'sendVideo']
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0].kwargs['chat_id'], -100123)
        notice = self.api.call.call_args.kwargs
        self.assertIn('Un film', notice['text'])
        self.assertEqual(notice['reply_markup']['inline_keyboard'][0][0]['url'],
                         'https://t.me/c/123/80')

    def test_duplicate_upload_preserves_published_title_and_links_to_original(self):
        film_id = self.store.add(self.media, 'video', 'Titre original')
        self.store.link_channel(-100123, film_id, 42)
        self.bot.handle({'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'},
            'video': {**self.media, 'file_name': 'Nouveau nom.mp4'}}})
        self.assertEqual(self.store.get(film_id)[2], 'Titre original')
        self.assertEqual(self.api.call.call_count, 1)
        notice = self.api.call.call_args
        self.assertEqual(notice.args[0], 'sendMessage')
        self.assertIn('Titre original', notice.kwargs['text'])
        self.assertEqual(notice.kwargs['reply_markup']['inline_keyboard'][0][0]['url'],
                         'https://t.me/c/123/42')

    def test_duplicate_document_without_title_is_recognized(self):
        film_id = self.store.add(self.media, 'video', 'Film connu')
        self.store.link_channel(-100123, film_id, 42)
        self.bot.handle({'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'},
            'document': {**self.media, 'mime_type': 'video/mp4'}}})
        self.assertIn('déjà disponible', self.api.call.call_args.kwargs['text'])

    def test_same_title_different_file_is_not_treated_as_exact_duplicate(self):
        film_id = self.store.add(self.media, 'video', 'Un film')
        self.store.link_channel(-100123, film_id, 42)
        self.assertIsNone(self.store.published_file(-100123, 'another-file'))
        self.assertIsNone(self.store.published_file(-100999, self.media['file_unique_id']))

    def test_admin_without_channel_rights_cannot_publish(self):
        self.store.add(self.media, 'video', 'Un film')
        self.api.call.return_value = {'status': 'member'}
        self.bot.publish(1, '1')
        self.assertFalse(any(c.args[0] == 'sendVideo' for c in self.api.call.call_args_list))

    def test_reader_cannot_publish(self):
        self.store.add(self.media, 'video', 'Un film')
        self.bot.handle({'message': {'from': {'id': 2}, 'chat': {'id': 2, 'type': 'private'},
                                     'text': '/publier 1'}})
        self.api.call.assert_not_called()

    def test_verification_rejects_groups_and_missing_rights(self):
        self.api.call.return_value = {'id': -100123, 'type': 'supergroup'}
        with self.assertRaises(ValueError):
            verify_channel(self.api, 123, '@maxxie_films')
        self.api.call.side_effect = [{'id': -100123, 'type': 'channel'},
                                     {'status': 'administrator', 'can_post_messages': False}]
        with self.assertRaises(ValueError):
            verify_channel(self.api, 123, '@maxxie_films')

    def test_verification_returns_numeric_id(self):
        self.api.call.side_effect = [{'id': -100123, 'type': 'channel'},
                                     {'status': 'administrator', 'can_post_messages': True}]
        self.assertEqual(verify_channel(self.api, 123, '@maxxie_films'), -100123)


if __name__ == '__main__':
    unittest.main()
