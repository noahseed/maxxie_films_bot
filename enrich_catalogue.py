"""Enrichir le catalogue sans modifier les publications Telegram."""
import json
import os
from pathlib import Path
import time
from catalogue import Catalogue
from posters import TMDBPosters, PosterError



def enrich(store, provider, channel, confirmed=None):
    counts={'enriched':0,'not_found':0,'failed':0}
    rows=store.db.execute('''SELECT f.id,f.title,c.message_id FROM films f JOIN channel_films c
        ON c.film_id=f.id WHERE c.channel_id=? ORDER BY c.message_id''',(channel,)).fetchall()
    for film_id,title,message in rows:
        old=store.metadata(film_id)
        movie_id=(confirmed or {}).get(message) or old.get('tmdb_id')
        if old.get('checked') and not ((confirmed or {}).get(message) and not old.get('confirmed')):
            continue
        try:
            bundle=provider.bundle(title,movie_id)
            if bundle:
                values=dict(bundle,checked=True)
                if (confirmed or {}).get(message):
                    values['confirmed']=True
                if old.get('manual_cover'):
                    values.pop('poster_file',None)
                store.save_metadata(film_id,values)
                counts['enriched']+=1
            else:
                store.save_metadata(film_id,{'checked':True})
                counts['not_found']+=1
        except (PosterError,OSError,ValueError,TypeError):
            counts['failed']+=1
        time.sleep(0.05)
    return counts


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed',type=Path)
    parser.add_argument('--channel-id',type=int)
    args=parser.parse_args()
    confirmed={int(key):value for key,value in json.loads(args.confirmed.read_text()).items()} if args.confirmed else {}
    store=Catalogue(os.environ['DATABASE_URL'])
    try:
        provider=TMDBPosters(os.environ['TMDB_READ_TOKEN'],Path('/var/lib/maxxie-films-bot/posters'))
        channel=args.channel_id or os.environ.get('CHANNEL_ID')
        if not channel or not str(channel).lstrip('-').isdigit():
            channels=store.db.execute('SELECT DISTINCT channel_id FROM channel_films').fetchall()
            if len(channels)!=1:
                raise SystemExit('Précise --channel-id avec l’identifiant numérique du canal.')
            channel=channels[0][0]
        print(json.dumps(enrich(store,provider,int(channel), confirmed)))
    finally:
        store.db.close()
