import unittest
from unittest.mock import Mock
from bot import Bot
from catalogue import Catalogue


def message(user=1, **fields):
    return {'message': {'chat': {'id': user, 'type': 'private'}, 'from': {'id': user}, **fields}}


class BotTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.store = Catalogue(':memory:')
        self.bot = Bot(self.api, self.store, {1}, {2}, -100123)
        self.api.call.side_effect = lambda method, **params: (
            {'status': 'member'} if method == 'getChatMember' else {'message_id': 100})
        self.media = {'file_id': 'file', 'file_unique_id': 'unique'}

    def tearDown(self):
        self.store.db.close()

    def test_admin_adds_and_reader_receives(self):
        self.store.add(self.media, 'video', 'Un film')
        self.bot.handle(message(2, text='/film 1'))
        self.api.call.assert_called_with('sendVideo', chat_id=2, video='file', caption='Un film')

    def test_reader_cannot_add_or_remove(self):
        self.bot.handle(message(2, video=self.media, caption='Un film'))
        self.assertEqual(self.store.search(), [])
        self.store.add(self.media, 'video', 'Un film')
        self.bot.handle(message(2, text='/supprimer 1'))
        self.assertIsNotNone(self.store.get(1))

    def test_unknown_user_cannot_download_even_with_callback(self):
        self.store.add(self.media, 'video', 'Un film')
        self.bot.handle({'callback_query': {'id': 'q', 'from': {'id': 3}, 'data': 'film:1',
            'message': {'chat': {'id': 3, 'type': 'private'}}}})
        self.assertFalse(any(call.args[0] == 'sendVideo' for call in self.api.call.call_args_list))

    def test_normalized_search_duplicates_and_literal_wildcards(self):
        first = self.store.add(self.media, 'video', 'Été 100%')
        self.assertEqual(len(self.store.search('ete')), 1)
        self.assertEqual(len(self.store.search('%')), 1)
        self.assertEqual(self.store.add(self.media, 'video', 'Hiver'), first)
        self.assertEqual(len(self.store.search()), 1)
        self.assertEqual(self.store.search('%'), [])

    def test_offset_is_persisted(self):
        self.store.acknowledge(42)
        self.assertEqual(self.store.offset(), 43)

    def test_groups_are_ignored(self):
        update = message(video=self.media, caption='Un film')
        update['message']['chat']['type'] = 'supergroup'
        self.bot.handle(update)
        self.assertEqual(self.store.search(), [])
        self.api.call.assert_not_called()

    def test_document_and_missing_caption(self):
        self.bot.channel_id = None
        media = {**self.media, 'mime_type': 'video/x-matroska'}
        self.bot.handle(message(document=media))
        self.assertEqual(self.store.search(), [])
        self.bot.handle(message(document=media, caption='Film MKV'))
        self.bot.channel_id = -100123
        self.bot.handle(message(2, text='/film 1'))
        self.api.call.assert_called_with('sendDocument', chat_id=2, document='file', caption='Film MKV')

    def test_pagination(self):
        for number in range(12):
            self.store.add({'file_id': str(number), 'file_unique_id': str(number)}, 'video', str(number))
        self.bot.handle(message(2, text='/catalogue'))
        keyboard = self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertEqual(len(keyboard), 12)
        self.assertEqual(keyboard[-2][0]['callback_data'], 'page:1')


if __name__ == '__main__':
    unittest.main()
