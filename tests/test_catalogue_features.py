from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from bot import Bot
from catalogue import Catalogue
from posters import TMDBPosters
from monitor import problems


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.store=Catalogue(':memory:')
        self.api=Mock()
        self.api.call.return_value={'status':'member'}
        self.bot=Bot(self.api,self.store,{1},set(),-100123,notify_chat_id=1)
        self.fid=self.add('Matrix 1999',50,'m')
        self.store.queue_posters(-100123)
        self.store.queue_synopses(-100123)
        self.store.synopsis_status(-100123,50,'done','Matrix 1999\n\nRésumé enregistré.')

    def add(self,title,message,unique):
        fid=self.store.add({'file_id':unique,'file_unique_id':unique},'video',title)
        self.store.link_channel(-100123,fid,message)
        return fid

    def tearDown(self):
        self.store.db.close()

    def callback(self,data,user=1):
        self.bot.handle({'callback_query':{'id':'q','from':{'id':user},'data':data,
            'message':{'chat':{'id':user,'type':'private'}}}})

    def message(self,text,user=1,**extra):
        self.bot.handle({'message':{'chat':{'id':user,'type':'private'},'from':{'id':user},'text':text,**extra}})

    def test_admin_button_is_hidden_from_subscribers(self):
        self.callback('menu',2)
        self.assertNotIn("'callback_data': 'admin'",str(self.api.call.call_args))
        self.callback('menu',1)
        self.assertIn("'callback_data': 'admin'",str(self.api.call.call_args))

    def test_forged_admin_buttons_are_rejected(self):
        for data in ('admin',f'adminfilm:{self.fid}',f'adminedit:delete:{self.fid}','adminconfirm:delete:fake'):
            self.callback(data,2)
            self.assertIn('réservée',self.api.call.call_args.kwargs['text'])
        self.assertIsNotNone(self.store.get(self.fid))
        self.assertFalse(any(call.args[0]=='deleteMessages' for call in self.api.call.call_args_list))

    def test_title_edit_preserves_synopsis_and_updates_search(self):
        self.callback(f'adminedit:title:{self.fid}')
        self.message('Matrix - 2000')
        self.assertEqual(self.store.get(self.fid)[2],'Matrix - 2000')
        edits=[call for call in self.api.call.call_args_list if call.args[0]=='editMessageCaption']
        self.assertEqual(edits[-1].kwargs['caption'],'Matrix - 2000\n\nRésumé enregistré.')
        self.assertEqual(self.store.search_channel(-100123,'Matrix 2000')[0][0],self.fid)

    def test_manual_synopsis_is_used_in_cards(self):
        self.callback(f'adminedit:synopsis:{self.fid}')
        self.message('Synopsis fourni par l’administrateur.')
        self.callback(f'fiche:{self.fid}',2)
        self.assertIn('Synopsis fourni',self.api.call.call_args.kwargs['text'])

    def test_admin_photo_is_kept_for_subsequent_cards(self):
        self.callback(f'adminedit:cover:{self.fid}')
        self.message('',photo=[{'file_id':'telegram-photo'}])
        edits=[call for call in self.api.call.call_args_list if call.args[0]=='editMessageMedia']
        self.assertEqual(edits[-1].kwargs['media']['cover'],'telegram-photo')
        self.callback(f'fiche:{self.fid}',2)
        self.assertEqual(self.api.call.call_args.args[0],'sendPhoto')
        self.assertEqual(self.api.call.call_args.kwargs['photo'],'telegram-photo')

    def test_delete_requires_bound_confirmation_and_purges_related_data(self):
        self.store.save_metadata(self.fid,{'tmdb_id':603})
        self.callback(f'adminedit:delete:{self.fid}')
        token=self.bot.feature_sessions[1]['token']
        self.callback('adminconfirm:delete:wrong')
        self.assertIsNotNone(self.store.get(self.fid))
        self.api.call.side_effect=lambda method,**kw: {'status':'member'} if method=='getChatMember' else True
        self.callback('adminconfirm:delete:'+token)
        self.assertIsNone(self.store.get(self.fid))
        self.assertIsNone(self.store.video_message(-100123,50))
        self.assertEqual(self.store.metadata(self.fid),{})

    def test_navigation_cancels_admin_input(self):
        self.callback(f'adminedit:title:{self.fid}')
        self.callback('menu')
        self.message('Ne pas renommer')
        self.assertEqual(self.store.get(self.fid)[2],'Matrix 1999')

    def test_id_command_cancels_pending_admin_edit(self):
        self.callback(f'adminedit:title:{self.fid}')
        self.message('/id')
        self.assertNotIn(1,self.bot.feature_sessions)
        self.message('Ne pas renommer')
        self.assertEqual(self.store.get(self.fid)[2],'Matrix 1999')

    def test_expired_admin_input_does_not_modify_film(self):
        self.callback(f'adminedit:title:{self.fid}')
        self.bot.feature_sessions[1]['time']=0
        with patch('catalogue_ui.time.monotonic',return_value=901):
            self.message('Ne pas renommer')
        self.assertEqual(self.store.get(self.fid)[2],'Matrix 1999')

    def test_report_includes_correct_film_and_is_rate_limited(self):
        self.callback(f'signal:{self.fid}:video',2)
        self.message('La vidéo ne fonctionne pas.',2)
        notices=[call for call in self.api.call.call_args_list if call.args[0]=='sendMessage' and '🚩 Signalement' in call.kwargs.get('text','')]
        self.assertEqual(len(notices),1)
        self.assertEqual(notices[0].kwargs['chat_id'],1)
        self.assertEqual(notices[0].kwargs['reply_markup']['inline_keyboard'][0][0]['url'],'https://t.me/c/123/50')
        self.callback(f'signal:{self.fid}:video',2)
        self.message('Encore.',2)
        self.assertIn('minute',self.api.call.call_args.kwargs['text'])

    def test_random_avoids_last_ten_and_filters_by_year_and_genre(self):
        other=self.add('Alien 1979',51,'a')
        self.store.save_metadata(self.fid,{'year':'1999','genres':['Science-Fiction']})
        self.store.save_metadata(other,{'year':'1979','genres':['Horreur']})
        first=self.store.choose_random(-100123,2)
        second=self.store.choose_random(-100123,2)
        self.assertNotEqual(first[0],second[0])
        self.assertEqual(self.store.choose_random(-100123,2,genre='Horreur',year='1979')[0],other)
        self.assertIsNone(self.store.choose_random(-100123,2,genre='Horreur',year='1999'))

    def test_cached_card_uses_no_external_metadata_request(self):
        self.store.save_metadata(self.fid,{'photo_id':'saved-photo','tmdb_id':603,'confirmed':True})
        self.bot.posters=Mock()
        self.bot.poster_executor=Mock()
        self.callback(f'fiche:{self.fid}',2)
        self.bot.poster_executor.submit.assert_not_called()
        self.assertEqual(self.api.call.call_args.kwargs['photo'],'saved-photo')

    def test_reference_requires_confirmation_before_editing_channel(self):
        future=Future()
        self.bot.posters=Mock()
        self.bot.poster_executor=Mock()
        self.bot.poster_executor.submit.return_value=future
        self.callback(f'adminedit:reference:{self.fid}')
        self.message('https://www.imdb.com/title/tt0133093/')
        future.set_result({'tmdb_id':603,'imdb_id':'tt0133093','year':'1999',
            'genres':['Science-Fiction'],'resolved_title':'Matrix','overview':'Résumé exact.','poster_file':''})
        self.api.reset_mock()
        self.api.call.return_value={'status':'member'}
        self.bot.poll_features()
        self.assertFalse(any(call.args[0]=='editMessageCaption' for call in self.api.call.call_args_list))
        token=self.bot.feature_sessions[1]['token']
        self.callback('adminconfirm:reference:'+token)
        self.assertTrue(self.store.metadata(self.fid)['confirmed'])
        self.assertEqual(self.store.channel_synopsis(-100123,self.fid),'Résumé exact.')

    def test_reference_from_another_session_is_discarded(self):
        future=Future()
        self.bot.posters=Mock()
        self.bot.poster_executor=Mock(return_value=None)
        self.bot.poster_executor.submit.return_value=future
        self.callback(f'adminedit:reference:{self.fid}')
        self.message('https://www.imdb.com/title/tt0133093/')
        self.callback('menu')
        future.set_result({'tmdb_id':603})
        self.bot.poll_features()
        self.assertNotIn(1,self.bot.feature_sessions)

    def test_manual_cover_is_preserved_during_metadata_enrichment(self):
        self.store.save_metadata(self.fid,{'manual_cover':True,'poster_file':'manual.jpg','photo_id':'manual-photo'})
        self.bot.cache_bundle(self.fid,{'tmdb_id':603,'poster_file':'automatic.jpg'})
        self.assertEqual(self.store.metadata(self.fid)['poster_file'],'manual.jpg')
        self.assertEqual(self.store.metadata(self.fid)['photo_id'],'manual-photo')

    def test_ten_distinct_draws_before_repetition(self):
        for index in range(9):
            self.add(f'Film {index}',60+index,f'other{index}')
        draws=[self.store.choose_random(-100123,2)[0] for _ in range(10)]
        self.assertEqual(len(set(draws)),10)
        self.assertNotEqual(self.store.choose_random(-100123,2)[0],draws[-1])

    def test_filter_pages_are_bounded(self):
        for index in range(25):
            fid=self.add(f'Film {index}',60+index,f'year{index}')
            self.store.save_metadata(fid,{'year':str(1900+index)})
        self.callback('filtre:year',2)
        rows=self.api.call.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertLessEqual(len(rows),22)
        self.assertIn('filterpage:year:1',str(rows))

    def test_empty_filtered_draw_offers_reset(self):
        self.bot.random_filters[2]={'genre':'Introuvable'}
        self.callback('hasard',2)
        self.assertIn('filtre:reset',str(self.api.call.call_args.kwargs))

    def test_photo_identifier_is_saved_for_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'poster.jpg'
            image.write_bytes(b'\xff\xd8\xffimage')
            self.api.call.return_value={'photo':[{'file_id':'reusable-photo'}]}
            self.bot.send_random(2,(self.fid,'Matrix 1999',50),{'path':image})
        self.assertEqual(self.store.metadata(self.fid)['photo_id'],'reusable-photo')

    def test_confirmed_mapping_is_not_replaced_by_stale_background_result(self):
        self.store.save_metadata(self.fid,{'tmdb_id':603,'confirmed':True})
        self.bot.cache_bundle(self.fid,{'tmdb_id':999,'year':'2020','poster_file':'wrong.jpg'})
        self.assertEqual(self.store.metadata(self.fid)['tmdb_id'],603)
        self.assertNotIn('poster_file',self.store.metadata(self.fid))

    def test_alerts_are_deduplicated(self):
        self.bot.technical_alert('failure','Une panne.')
        self.bot.technical_alert('failure','Une panne.')
        self.assertEqual(self.api.call.call_count,1)


class MetadataAndMonitorTests(unittest.TestCase):
    def test_reference_rejects_untrusted_urls(self):
        client=TMDBPosters('token','/tmp/unused')
        client._get=Mock()
        for url in ('http://imdb.com/title/tt123/','https://evil.example/movie/1','https://imdb.com.evil.example/title/tt123/'):
            with self.assertRaises(ValueError):
                client.resolve(url)
        client._get.assert_not_called()

    def test_confirmed_reference_uses_exact_details(self):
        client=TMDBPosters('token','/tmp/unused')
        client.details=Mock(return_value={'id':603,'title':'Matrix','release_date':'1999-01-01','genres':[{'name':'Science-Fiction'}],'overview':'Résumé.'})
        client.lookup=Mock()
        client.download_movie=Mock(return_value=None)
        bundle=client.bundle('Titre approximatif',603)
        client.lookup.assert_not_called()
        self.assertEqual(bundle['year'],'1999')
        self.assertEqual(bundle['genres'],['Science-Fiction'])

    def test_monitor_detects_failure_and_stale_backup(self):
        run=Mock()
        run.side_effect=[Mock(returncode=1),Mock(returncode=0),Mock(returncode=0,stdout='exit-code')]
        with tempfile.TemporaryDirectory() as directory:
            issues=problems(run,Path(directory),100000)
        self.assertEqual(len(issues),3)
