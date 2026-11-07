from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from bot import Bot
from catalogue import Catalogue
from posters import TMDBPosters, PosterError, movie_query, select_movie
from telegram_api import Telegram, TelegramError


def movie(number=1, year='1999', title='Matrix'):
    return {'id': number, 'title': title, 'original_title': title,
            'release_date': year + '-03-31', 'poster_path': '/Abc123.jpg'}


class PosterDownloadTests(unittest.TestCase):
    def test_filename_cleanup_and_release_year(self):
        self.assertEqual(movie_query('Matrix.1999.1080p.VF.x264.mp4'), ('Matrix', '1999'))
        self.assertEqual(movie_query('Alien - 1979 [VOSTFR].mkv'), ('Alien', '1979'))

    def test_ambiguous_remakes_wrong_year_and_unrelated_titles_are_rejected(self):
        self.assertIsNone(select_movie([movie(1, '1999'), movie(2, '2020')], 'Matrix', ''))
        self.assertEqual(select_movie([movie(1, '1999'), movie(2, '2020')], 'Matrix', '1999')['id'], 1)
        self.assertIsNone(select_movie([movie()], 'Alien', '1999'))
        self.assertIsNone(select_movie([movie()], 'Matrix', '2000'))

    def test_unsafe_poster_path_is_rejected(self):
        result = movie()
        result['poster_path'] = '/../../config.env'
        self.assertIsNone(select_movie([result], 'Matrix', '1999'))

    def test_jpeg_is_downloaded_to_private_cache_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TMDBPosters('secret', directory)
            metadata = json.dumps({'results': [movie()]}).encode()
            client._get = Mock(side_effect=[metadata, b'\xff\xd8\xffimage', metadata])
            first = client.download('Matrix 1999 VF')
            self.assertTrue(first['path'].is_file())
            self.assertEqual(first['path'].read_bytes(), b'\xff\xd8\xffimage')
            self.assertEqual(first['path'].stat().st_mode & 0o777, 0o600)
            self.assertEqual(client.download('Matrix 1999 VF')['path'], first['path'])
            self.assertEqual(client._get.call_count, 3)

    @patch('posters.http.client.HTTPSConnection')
    def test_image_download_has_no_tmdb_secret_in_headers(self, factory):
        response = factory.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = b'\xff\xd8\xffimage'
        response.getheader.return_value = 'image/jpeg'
        client = TMDBPosters('secret', '/tmp/unused')
        client._get('image.tmdb.org', '/t/p/w500/Abc.jpg', image=True)
        self.assertNotIn('Authorization', factory.return_value.request.call_args.kwargs['headers'])

    @patch('posters.http.client.HTTPSConnection')
    def test_html_is_not_saved_as_a_poster(self, factory):
        response = factory.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = b'<html>error</html>'
        response.getheader.return_value = 'text/html'
        with self.assertRaises(PosterError):
            TMDBPosters('secret', '/tmp/unused')._get('image.tmdb.org', '/t/p/w500/a.jpg', image=True)


class PosterQueueTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.store = Catalogue(':memory:')
        self.provider = Mock()
        self.bot = Bot(self.api, self.store, {1}, {2}, -100123, posters=self.provider)
        self.bot.poll_synopses = Mock()
        self.bot.poster_executor.shutdown()
        self.future = Future()
        self.bot.poster_executor = Mock()
        self.bot.poster_executor.submit.return_value = self.future
        self.film_id = self.store.add({'file_id': 'f', 'file_unique_id': 'f'}, 'video', 'Matrix 1999')
        self.store.link_channel(-100123, self.film_id, 50)
        self.store.queue_posters(-100123)

    def tearDown(self):
        self.store.db.close()

    def status(self):
        return self.store.db.execute('SELECT status FROM poster_jobs').fetchone()[0]

    def test_cover_edits_existing_video_and_is_not_queued_again(self):
        self.bot.poll_posters()
        self.future.set_result({'path': Path('/tmp/poster.jpg'), 'title': 'Matrix', 'id': 1})
        self.bot.poll_posters()
        self.api.edit_video_cover.assert_called_once()
        self.api.send_photo.assert_not_called()
        self.assertEqual(self.api.edit_video_cover.call_args.args[0], -100123)
        self.assertEqual(self.api.edit_video_cover.call_args.args[1], 50)
        self.assertEqual(self.status(), 'covered')
        self.store.queue_posters(-100123)
        self.assertIsNone(self.store.next_poster(-100123))

    def test_uncertain_telegram_send_is_not_retried(self):
        self.bot.poll_posters()
        self.api.edit_video_cover.side_effect = TelegramError(0)
        self.future.set_result({'path': Path('/tmp/poster.jpg'), 'title': 'Matrix', 'id': 1})
        with self.assertLogs('maxxie-films', level='WARNING'):
            self.bot.poll_posters()
        self.assertEqual(self.status(), 'cover_uncertain')
        self.store.queue_posters(-100123)
        self.assertIsNone(self.store.next_poster(-100123))

    def test_already_applied_cover_is_recognized_as_success(self):
        self.bot.poll_posters()
        self.api.edit_video_cover.side_effect = TelegramError(400, reason='not_modified')
        self.future.set_result({'path': Path('/tmp/poster.jpg'), 'title': 'Matrix', 'id': 1})
        self.bot.poll_posters()
        self.assertEqual(self.status(), 'covered')

    def test_rate_limit_is_respected_without_losing_the_job(self):
        self.bot.poll_posters()
        self.api.edit_video_cover.side_effect = TelegramError(429, retry_after=30)
        self.future.set_result({'path': Path('/tmp/poster.jpg'), 'title': 'Matrix', 'id': 1})
        with self.assertLogs('maxxie-films', level='WARNING'):
            self.bot.poll_posters()
        self.assertEqual(self.status(), 'queued')
        self.bot.poll_posters()
        self.assertEqual(self.bot.poster_executor.submit.call_count, 1)

    def test_no_match_does_not_send_any_photo(self):
        self.bot.poll_posters()
        self.future.set_result(None)
        self.bot.poll_posters()
        self.api.send_photo.assert_not_called()
        self.api.edit_video_cover.assert_not_called()
        self.assertEqual(self.status(), 'not_found')

    def test_deleted_reference_does_not_receive_a_photo(self):
        self.bot.poll_posters()
        self.store.remove(self.film_id)
        self.future.set_result({'path': Path('/tmp/poster.jpg'), 'title': 'Matrix', 'id': 1})
        self.bot.poll_posters()
        self.api.send_photo.assert_not_called()
        self.api.edit_video_cover.assert_not_called()

    def test_caption_entities_and_original_video_are_preserved(self):
        entities = [{'type': 'bold', 'offset': 0, 'length': 6}]
        self.store.remember_video(-100123, {'message_id': 50,
            'video': {'file_id': 'original-video', 'duration': 120},
            'caption': 'Matrix\nLégende complète', 'caption_entities': entities})
        self.bot.poll_posters()
        self.future.set_result({'path': Path('/tmp/poster.jpg'), 'title': 'Matrix', 'id': 1})
        self.bot.poll_posters()
        media = self.api.edit_video_cover.call_args.args[2]
        self.assertEqual(media['media'], 'original-video')
        self.assertEqual(media['caption'], 'Matrix\nLégende complète')
        self.assertEqual(media['caption_entities'], entities)
        self.assertEqual(media['duration'], 120)

    def test_old_comment_jobs_are_migrated_to_video_covers(self):
        self.store.poster_status(-100123, 50, 'sent')
        self.store.queue_posters(-100123)
        self.assertEqual(self.status(), 'queued')
        self.assertEqual(self.store.video_message(-100123, 50)['caption'], 'Matrix 1999')

    def test_document_is_not_converted_to_video(self):
        document_id = self.store.add({'file_id': 'd', 'file_unique_id': 'd'}, 'document', 'Document')
        self.store.link_channel(-100123, document_id, 51)
        self.store.poster_status(-100123, 50, 'covered')
        self.store.queue_posters(-100123)
        self.assertIsNone(self.store.next_poster(-100123))


class PhotoUploadTests(unittest.TestCase):
    @patch('telegram_api.http.client.HTTPSConnection')
    def test_cover_edits_message_without_new_photo_or_video_upload(self, factory):
        response = factory.return_value.getresponse.return_value
        response.will_close = False
        response.read.return_value = b'{"ok":true,"result":{"message_id":50}}'
        with tempfile.TemporaryDirectory() as directory:
            photo = Path(directory) / 'poster.jpg'
            photo.write_bytes(b'\xff\xd8\xffimage')
            Telegram('123:secret').edit_video_cover(-100123, 50,
                {'type': 'video', 'media': 'original-video', 'caption': 'Titre'}, photo)
        request = factory.return_value.request.call_args
        self.assertEqual(request.args[1], '/bot123:secret/editMessageMedia')
        self.assertIn(b'name="cover"; filename="poster.jpg"', request.args[2])
        self.assertIn(b'attach://cover', request.args[2])
        self.assertIn(b'original-video', request.args[2])
        self.assertNotIn(b'name="photo"', request.args[2])
        self.assertNotIn(b'reply_parameters', request.args[2])
        factory.return_value.sock.settimeout.assert_called_with(30)

    @patch('telegram_api.http.client.HTTPSConnection')
    def test_photo_upload_is_multipart_and_preserves_video_reply(self, factory):
        response = factory.return_value.getresponse.return_value
        response.will_close = False
        response.read.return_value = b'{"ok":true,"result":{"message_id":51}}'
        with tempfile.TemporaryDirectory() as directory:
            photo = Path(directory) / 'poster.jpg'
            photo.write_bytes(b'\xff\xd8\xffimage')
            Telegram('123:secret').send_photo(-100123, photo, 'Matrix', 50)
        request = factory.return_value.request.call_args
        self.assertEqual(request.args[1], '/bot123:secret/sendPhoto')
        self.assertTrue(request.args[3]['Content-Type'].startswith('multipart/form-data; boundary='))
        self.assertIn(b'\xff\xd8\xffimage', request.args[2])
        self.assertIn(b'{"message_id": 50}', request.args[2])
        self.assertEqual(factory.return_value.request.call_count, 1)


if __name__ == '__main__':
    unittest.main()
