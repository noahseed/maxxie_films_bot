from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from bot import Bot, synopsis_caption
from catalogue import Catalogue
from posters import TMDBPosters
from telegram_api import TelegramError


class SynopsisTests(unittest.TestCase):
    def setUp(self):
        self.store = Catalogue(':memory:')
        self.api = Mock()
        self.provider = Mock()
        self.bot = Bot(self.api, self.store, {1}, set(), -100123, posters=self.provider)
        self.bot.poster_executor.shutdown()
        self.future = Future()
        self.bot.poster_executor = Mock()
        self.bot.poster_executor.submit.return_value = self.future
        self.film = self.store.add({'file_id': 'f', 'file_unique_id': 'u'}, 'video', 'Matrix 1999')
        self.store.link_channel(-100123, self.film, 50)
        self.store.queue_posters(-100123)

    def tearDown(self):
        self.store.db.close()

    def test_caption_changes_only_caption_and_is_idempotent(self):
        self.bot.poll_synopses()
        self.future.set_result({'id': 603, 'overview': 'Un programmeur découvre la vérité.'})
        self.bot.poll_synopses()
        args = self.api.call.call_args
        self.assertEqual(args.args[0], 'editMessageCaption')
        self.assertTrue(args.kwargs['caption'].startswith('Matrix 1999\n\nUn programmeur'))
        self.assertNotIn('TMDB', args.kwargs['caption'])
        self.assertNotIn('http', args.kwargs['caption'])
        self.assertEqual(self.store.get(self.film)[2], 'Matrix 1999')
        self.assertEqual(self.store.video_message(-100123, 50)['caption'], args.kwargs['caption'])
        self.assertIsNone(self.store.next_synopsis(-100123))

    def test_missing_synopsis_leaves_post_unchanged(self):
        self.bot.poll_synopses()
        self.future.set_result(None)
        self.bot.poll_synopses()
        self.api.call.assert_not_called()
        self.assertIsNone(self.store.next_synopsis(-100123))

    def test_random_sends_poster_with_synopsis_and_buttons(self):
        self.store.queue_synopses(-100123)
        self.store.synopsis_status(-100123, 50, 'done', 'Matrix 1999\n\nRésumé du film. ' + 'Long résumé. ' * 150)
        self.api.call.return_value = {'status': 'member'}
        with tempfile.TemporaryDirectory() as directory:
            poster = Path(directory) / 'poster.jpg'
            poster.write_bytes(b'\xff\xd8\xffimage')
            self.bot.show_random(2)
            self.api.call.assert_not_called()
            self.future.set_result({'path': poster})
            self.bot.poll_random()
        args = self.api.call.call_args
        self.assertEqual(args.args[0], 'sendPhoto')
        self.assertIn('Matrix 1999\n\nRésumé du film.', args.kwargs['caption'])
        self.assertLessEqual(len(args.kwargs['caption'].encode('utf-16-le')) // 2, 1024)
        self.assertEqual(args.kwargs['reply_markup']['inline_keyboard'][0][0]['url'], 'https://t.me/c/123/50')

    def test_random_without_matched_poster_falls_back_to_text(self):
        self.api.call.return_value = {'status': 'member'}
        self.bot.show_random(2)
        self.future.set_result(None)
        self.bot.poll_random()
        self.assertEqual(self.api.call.call_args.args[0], 'sendMessage')
        self.assertIn('Matrix 1999', self.api.call.call_args.kwargs['text'])

    def test_caption_fits_telegram_utf16_limit(self):
        caption = synopsis_caption('🎬' * 100, 'Résumé 😀 ' * 500, 603)
        self.assertLessEqual(len(caption.encode('utf-16-le')) // 2, 1024)
        self.assertTrue(caption.endswith('…'))

    def test_synopsis_does_not_require_a_poster(self):
        client = TMDBPosters('secret', '/tmp/unused')
        client._get = Mock(return_value=json.dumps({'results': [{'id': 603, 'title': 'Matrix',
            'release_date': '1999-01-01', 'overview': 'Résumé français.', 'poster_path': None}]}).encode())
        self.assertEqual(client.synopsis('Matrix 1999'), {'id': 603, 'overview': 'Résumé français.'})
        self.assertIn('language=fr-FR', client._get.call_args.args[1])
