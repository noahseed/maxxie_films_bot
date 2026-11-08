"""Fiches, filtres, signalements et administration privée par boutons."""
from pathlib import Path
import time
import secrets

from catalogue import normalize
from telegram_api import TelegramError
from posters import PosterError

HOME = {'text': '🏠 Accueil', 'callback_data': 'menu'}
HELP = {'text': '❓ Aide', 'callback_data': 'aide'}


def bounded_caption(title, overview):
    text = title + ('\n\n' + overview if overview else '')
    if len(text.encode('utf-16-le')) // 2 > 1024:
        text = text.encode('utf-16-le')[:2046].decode('utf-16-le', errors='ignore').rstrip() + '…'
    return text


class CatalogueUI:
    def init_catalogue_ui(self):
        self.feature_sessions = {}
        self.feature_jobs = {}
        self.random_filters = {}
        self.metadata_job = None

    def feature_prompt(self, chat_id, text, rows=None):
        self.send(chat_id, text, reply_markup={'inline_keyboard': (rows or []) + [[HOME, HELP]]})

    def valid_film(self, film_id):
        film = self.catalogue.get(film_id)
        message = self.catalogue.channel_message(self.channel_id, film_id)
        return (film_id, film[2], message) if film and message else None

    def session(self, chat_id, action, film_id=None, **extra):
        self.feature_sessions[chat_id] = dict(action=action, film_id=film_id, time=time.monotonic(), **extra)

    def handle_feature_callback(self, chat_id, data):
        if data.startswith('admin') and chat_id not in self.admins:
            self.feature_prompt(chat_id, 'Cette fonction est réservée aux administrateurs.')
            return True
        if data == 'admin':
            self.session(chat_id, 'admin_search')
            self.feature_prompt(chat_id, '🛠 Administration du catalogue\n\nEnvoie le titre du film à gérer.',
                [[{'text':'📚 Parcourir les films','callback_data':'adminpage:0'}]])
        elif data.startswith('adminpage:'):
            try:
                page = max(0, int(data.split(':')[1]))
            except ValueError:
                return True
            if page > 10000:
                return True
            rows = self.catalogue.db.execute('''SELECT f.id,f.title FROM films f JOIN channel_films c ON c.film_id=f.id
                WHERE c.channel_id=? ORDER BY f.id DESC LIMIT 9 OFFSET ?''', (self.channel_id,page*8)).fetchall()
            keyboard = [[{'text':title[:64], 'callback_data':f'adminfilm:{film_id}'}] for film_id,title in rows[:8]]
            nav=[]
            if page:
                nav.append({'text':'⬅️ Précédent','callback_data':f'adminpage:{page-1}'})
            if len(rows)>8:
                nav.append({'text':'Suivant ➡️','callback_data':f'adminpage:{page+1}'})
            self.feature_prompt(chat_id,'Choisis le film à gérer.',keyboard + ([nav] if nav else []))
        elif data.startswith('adminfilm:'):
            film = self.parse_film(data)
            if film:
                fid,title,_ = film
                self.feature_prompt(chat_id, '🛠 ' + title, [
                    [{'text':'✏️ Corriger le titre','callback_data':f'adminedit:title:{fid}'}],
                    [{'text':'🔗 Associer IMDb / TMDB','callback_data':f'adminedit:reference:{fid}'}],
                    [{'text':'🖼 Remplacer la jaquette','callback_data':f'adminedit:cover:{fid}'}],
                    [{'text':'📝 Modifier le synopsis','callback_data':f'adminedit:synopsis:{fid}'}],
                    [{'text':'🗑 Supprimer le film','callback_data':f'adminedit:delete:{fid}'}]])
            else:
                self.feature_prompt(chat_id,'Ce film n’est plus disponible.')
        elif data.startswith('adminedit:'):
            film = self.parse_film(data)
            action = data.split(':')[1] if len(data.split(':'))==3 else ''
            if not film or action not in ('title','reference','cover','synopsis','delete'):
                self.feature_prompt(chat_id,'Action indisponible.')
                return True
            fid,title,_=film
            self.session(chat_id,action,fid)
            if action=='delete':
                token=secrets.token_hex(8)
                self.session(chat_id,'delete',fid,token=token)
                self.feature_prompt(chat_id, f'Supprimer définitivement « {title} » du canal et du catalogue ?',
                    [[{'text':'🗑 Confirmer la suppression','callback_data':f'adminconfirm:delete:{token}'}]])
            else:
                prompts={'title':'Envoie le nouveau titre, avec l’année (200 caractères maximum).',
                    'reference':'Envoie le lien IMDb ou TMDB exact. Tu confirmeras la fiche avant son application.',
                    'cover':'Envoie la nouvelle jaquette comme photo Telegram (pas comme fichier).',
                    'synopsis':'Envoie le synopsis à afficher sous le titre.'}
                self.feature_prompt(chat_id,title+'\n\n'+prompts[action])
        elif data.startswith('adminconfirm:'):
            session=self.feature_sessions.get(chat_id,{})
            parts=data.split(':')
            if len(parts)!=3 or session.get('token')!=parts[2] or time.monotonic()-session.get('time',0)>900:
                self.feature_prompt(chat_id,'Cette confirmation a expiré.')
                return True
            film=self.valid_film(session['film_id'])
            if not film:
                self.feature_prompt(chat_id,'Ce film n’est plus disponible.')
                return True
            if parts[1]=='delete' and session['action']=='delete':
                result=self.api.call('deleteMessages',chat_id=self.channel_id,message_ids=[film[2]])
                if result is not True:
                    raise TelegramError(0)
                self.catalogue.purge_film(film[0])
                self.feature_prompt(chat_id,'Film supprimé du canal et du catalogue.')
            elif parts[1]=='reference' and session['action']=='reference_confirm':
                bundle=session['bundle']
                metadata = dict(bundle, confirmed=True)
                metadata.pop('photo_id',None)
                self.apply_cover_and_caption(film, bundle)
                self.catalogue.save_metadata(film[0],dict(metadata,photo_id=''))
                self.feature_prompt(chat_id,'Correspondance enregistrée ; jaquette et synopsis disponibles appliqués.')
            self.feature_sessions.pop(chat_id,None)
        elif data.startswith('fiche:'):
            film=self.parse_film(data)
            if film:
                self.show_card(chat_id,film)
            else:
                self.feature_prompt(chat_id,'Ce film n’est plus disponible dans le canal.')
        elif data == 'filtres':
            self.feature_prompt(chat_id,'🎲 Filtrer les prochains tirages :',[
                [{'text':'🎭 Genre','callback_data':'filtre:genre'}, {'text':'📅 Année','callback_data':'filtre:year'}],
                [{'text':'Tous les films','callback_data':'filtre:reset'}],
                [{'text':'🎲 Tirer un film','callback_data':'hasard'}]])
        elif data.startswith('filterpage:'):
            parts=data.split(':')
            if len(parts)==3 and parts[1] in ('genre','year') and parts[2].isdigit():
                self.show_filter_page(chat_id,parts[1],int(parts[2]))
        elif data.startswith('filtre:'):
            parts=data.split(':')
            if parts[1]=='reset':
                self.random_filters.pop(chat_id,None)
                self.feature_prompt(chat_id,'Filtres effacés.',[[{'text':'🎲 Tirer un film','callback_data':'hasard'}]])
            elif parts[1] in ('genre','year'):
                genres,years=self.catalogue.filter_values(self.channel_id)
                values=genres if parts[1]=='genre' else years
                if len(parts)==3 and parts[2].isdigit() and int(parts[2])<len(values):
                    self.random_filters.setdefault(chat_id,{})[parts[1]]=values[int(parts[2])]
                    selected=self.random_filters[chat_id]
                    self.feature_prompt(chat_id,'Filtres : '+', '.join(selected.values()),[
                        [{'text':'🎲 Tirer un film','callback_data':'hasard'}, {'text':'Modifier','callback_data':'filtres'}]])
                else:
                    self.show_filter_page(chat_id,parts[1])
        elif data.startswith('report:'):
            film=self.parse_film(data)
            if film:
                self.feature_prompt(chat_id,'Quel problème souhaites-tu signaler pour « '+film[1]+' » ?',[
                    [{'text':label,'callback_data':f'signal:{film[0]}:{reason}'}] for label,reason in
                    [('Vidéo inaccessible','video'),('Mauvaise jaquette','poster'),('Titre ou synopsis incorrect','title'),('Autre problème','other')]])
        elif data.startswith('signal:'):
            parts=data.split(':')
            if len(parts)==3 and parts[1].isdigit() and self.valid_film(int(parts[1])) and parts[2] in ('video','poster','title','other'):
                self.session(chat_id,'report',int(parts[1]),reason=parts[2])
                self.feature_prompt(chat_id,'Décris le problème en quelques mots (1 000 caractères maximum). Il sera transmis en privé à l’administrateur.')
        else:
            return False
        return True

    def show_filter_page(self,chat_id,kind,page=0):
        genres,years=self.catalogue.filter_values(self.channel_id)
        values=genres if kind=='genre' else years
        page=max(0,min(page,max(0,(len(values)-1)//20)))
        keyboard=[[{'text':value,'callback_data':f'filtre:{kind}:{index}'}]
                  for index,value in enumerate(values) if page*20<=index<(page+1)*20]
        nav=[]
        if page:
            nav.append({'text':'⬅️ Précédent','callback_data':f'filterpage:{kind}:{page-1}'})
        if len(values)>(page+1)*20:
            nav.append({'text':'Suivant ➡️','callback_data':f'filterpage:{kind}:{page+1}'})
        if nav:
            keyboard.append(nav)
        self.feature_prompt(chat_id,'Choisis une valeur (les filtres se cumulent).' if values else
            'Aucune valeur disponible pour le moment. Les fiches sont en cours de préparation.',keyboard)

    def parse_film(self,data):
        value=data.rsplit(':',1)[-1]
        return self.valid_film(int(value)) if value.isdigit() and len(value)<16 else None

    def show_card(self,chat_id,film):
        data=self.catalogue.metadata(film[0])
        poster={'path':data['poster_file']} if data.get('poster_file') and Path(data['poster_file']).is_file() else None
        if data.get('photo_id') or poster or not self.posters or (data.get('checked') and not data.get('poster_file')):
            self.send_random(chat_id,film,poster,random=False)
        elif chat_id not in self.feature_jobs and len(self.feature_jobs)<2:
            self.feature_jobs[chat_id]=(self.poster_executor.submit(self.posters.bundle,film[1],data.get('tmdb_id')),film,'card')
        else:
            self.send_random(chat_id,film,random=False)

    def handle_feature_message(self, chat_id, message):
        session=self.feature_sessions.get(chat_id)
        if not session or time.monotonic()-session['time']>900:
            self.feature_sessions.pop(chat_id,None)
            return False
        action=session['action']
        text=message.get('text','').strip()
        if action!='report' and chat_id not in self.admins:
            self.feature_sessions.pop(chat_id,None)
            return False
        if action=='admin_search':
            rows=self.catalogue.search_channel(self.channel_id,text[:200]) if text else []
            self.feature_prompt(chat_id,'Choisis un film.' if rows else 'Aucun film trouvé. Envoie un autre titre.',[
                [{'text':title[:64],'callback_data':f'adminfilm:{fid}'}] for fid,title,_ in rows[:10]])
            return True
        film=self.valid_film(session.get('film_id'))
        if not film:
            self.feature_sessions.pop(chat_id,None)
            self.feature_prompt(chat_id,'Ce film n’est plus disponible.')
            return True
        if action=='report':
            if not text or len(text)>1000:
                self.feature_prompt(chat_id,'Écris une description de 1 000 caractères maximum.')
                return True
            if not self.notify_chat_id:
                self.feature_prompt(chat_id,'Les signalements sont momentanément indisponibles.')
                return True
            token=self.catalogue.record_report(chat_id,film[0],session['reason'])
            if not token:
                self.feature_prompt(chat_id,'Attends une minute avant un nouveau signalement.')
                return True
            self.send(self.notify_chat_id,f'🚩 Signalement — {film[1]}\nUtilisateur : {chat_id}\nMotif : {session["reason"]}\n\n{text}',
                reply_markup={'inline_keyboard':[[{'text':'Voir la publication','url':self.film_link(film[2])}],
                    [{'text':'Gérer ce film','callback_data':f'adminfilm:{film[0]}'}]]})
            with self.catalogue.db:
                self.catalogue.db.execute("UPDATE film_reports SET status='sent' WHERE token=?",(token,))
            self.feature_prompt(chat_id,'Merci, ton signalement a été transmis à l’administrateur.')
        elif action in ('title','synopsis'):
            if not text or len(text)>(200 if action=='title' else 3000):
                self.feature_prompt(chat_id,'Texte vide ou trop long. Réessaie.')
                return True
            title=' '.join(text.split()) if action=='title' else film[1]
            overview=self.catalogue.channel_synopsis(self.channel_id,film[0]) or ''
            if action=='synopsis':
                overview=text
            caption=bounded_caption(title,overview)
            try:
                self.api.call('editMessageCaption',chat_id=self.channel_id,message_id=film[2],caption=caption)
            except TelegramError as error:
                if error.reason!='not_modified':
                    raise
            with self.catalogue.db:
                self.catalogue.db.execute('UPDATE films SET title=?,search_title=? WHERE id=?',(title,normalize(title),film[0]))
                self.catalogue.db.execute('UPDATE poster_jobs SET title=? WHERE channel_id=? AND message_id=?',(title,self.channel_id,film[2]))
                self.catalogue.queue_synopses(self.channel_id)
                self.catalogue.synopsis_status(self.channel_id,film[2],'done' if overview else 'not_found',caption)
            self.feature_prompt(chat_id,'Publication et catalogue mis à jour.')
        elif action=='reference':
            if not self.posters:
                self.feature_prompt(chat_id,'La recherche de fiches est indisponible.')
                return True
            if chat_id in self.feature_jobs or len(self.feature_jobs)>=2:
                self.feature_prompt(chat_id,'Une fiche est en préparation. Réessaie dans un instant.')
                return True
            self.feature_jobs[chat_id]=(self.poster_executor.submit(self.reference_bundle,text),film,'reference')
            return True
        elif action=='cover':
            photos=message.get('photo',[])
            if not photos or not isinstance(photos[-1].get('file_id'),str):
                self.feature_prompt(chat_id,'Envoie la jaquette comme photo Telegram.')
                return True
            media=self.catalogue.video_message(self.channel_id,film[2])
            if not media:
                self.feature_prompt(chat_id,'Cette publication ne dispose pas d’une référence vidéo modifiable.')
                return True
            photo=photos[-1]['file_id']
            self.api.call('editMessageMedia',chat_id=self.channel_id,message_id=film[2],media=dict(media,cover=photo))
            self.catalogue.poster_status(self.channel_id,film[2],'covered')
            self.catalogue.save_metadata(film[0],{'photo_id':photo,'manual_cover':True})
            self.feature_prompt(chat_id,'Jaquette remplacée dans le canal et les fiches du bot.')
        else:
            self.feature_prompt(chat_id,'Utilise les boutons pour confirmer ou reviens à l’accueil.')
            return True
        self.feature_sessions.pop(chat_id,None)
        return True

    def reference_bundle(self,text):
        movie=self.posters.resolve(text)
        return self.posters.bundle(movie['title'],movie['id']) if movie else None

    def apply_cover_and_caption(self,film,bundle):
        overview=bundle.get('overview') or self.catalogue.channel_synopsis(self.channel_id,film[0]) or ''
        caption=bounded_caption(film[1],overview)
        media=self.catalogue.video_message(self.channel_id,film[2])
        path=bundle.get('poster_file')
        try:
            if media and path:
                media=dict(media,caption=caption)
                media.pop('caption_entities',None)
                self.api.edit_video_cover(self.channel_id,film[2],media,path)
                self.catalogue.poster_status(self.channel_id,film[2],'covered')
            else:
                self.api.call('editMessageCaption',chat_id=self.channel_id,message_id=film[2],caption=caption)
        except TelegramError as error:
            if error.reason!='not_modified':
                raise
        self.catalogue.queue_synopses(self.channel_id)
        self.catalogue.synopsis_status(self.channel_id,film[2],'done' if overview else 'not_found',caption)

    def poll_features(self):
        self.feature_sessions={uid:s for uid,s in self.feature_sessions.items() if time.monotonic()-s['time']<900}
        for chat_id,(future,film,purpose) in list(self.feature_jobs.items()):
            if not future.done():
                continue
            del self.feature_jobs[chat_id]
            if not self.valid_film(film[0]) or not self.check_membership(chat_id):
                continue
            if purpose=='reference' and (chat_id not in self.admins or self.feature_sessions.get(chat_id,{}).get('action')!='reference' or self.feature_sessions.get(chat_id,{}).get('film_id')!=film[0]):
                continue
            try:
                bundle=future.result()
            except (PosterError,OSError,ValueError,TypeError):
                bundle=None
            if purpose=='reference':
                if not bundle:
                    self.feature_prompt(chat_id,'Référence introuvable. Envoie un lien IMDb ou TMDB de film.')
                else:
                    token=secrets.token_hex(8)
                    self.session(chat_id,'reference_confirm',film[0],bundle=bundle,token=token)
                    self.feature_prompt(chat_id,f'Associer « {film[1]} » à « {bundle["resolved_title"]} » ({bundle["year"]}) ?\nLa jaquette et le synopsis disponibles seront appliqués.',
                        [[{'text':'✅ Confirmer cette fiche','callback_data':f'adminconfirm:reference:{token}'}]])
            else:
                if bundle:
                    self.cache_bundle(film[0],bundle)
                else:
                    self.catalogue.save_metadata(film[0],{'checked':True})
                self.show_card(chat_id,film)

    def cache_bundle(self,film_id,bundle):
        old=self.catalogue.metadata(film_id)
        if old.get('confirmed') and old.get('tmdb_id') != bundle.get('tmdb_id'):
            return old
        values=dict(bundle,checked=True)
        if old.get('manual_cover'):
            values.pop('poster_file',None)
        return self.catalogue.save_metadata(film_id,values)

    def technical_alert(self,key,text):
        if self.notify_chat_id and self.catalogue.reserve_alert(key):
            try:
                self.send(self.notify_chat_id,'⚠️ Maxxie Films — '+text)
            except TelegramError:
                pass

    def poll_metadata(self):
        if not self.posters:
            return
        if self.metadata_job:
            future, film = self.metadata_job
            if not future.done():
                return
            self.metadata_job = None
            if self.valid_film(film[0]):
                try:
                    bundle = future.result()
                    if bundle:
                        self.cache_bundle(film[0],bundle)
                    else:
                        self.catalogue.save_metadata(film[0],{'checked':True})
                except (PosterError,OSError,ValueError,TypeError):
                    self.catalogue.save_metadata(film[0],{'checked':True})
        if self.feature_jobs or self.random_jobs or self.poster_job or self.synopsis_job:
            return
        rows=self.catalogue.db.execute('''SELECT f.id,f.title,c.message_id FROM films f JOIN channel_films c
            ON c.film_id=f.id WHERE c.channel_id=? ORDER BY f.id DESC''',(self.channel_id,)).fetchall()
        for film in rows:
            data=self.catalogue.metadata(film[0])
            if not data.get('checked'):
                self.metadata_job=(self.poster_executor.submit(self.posters.bundle,film[1],data.get('tmdb_id')),film)
                break
