"""Migration vérifiée d’un catalogue SQLite arrêté vers une base PostgreSQL vide."""
import argparse
import json
import sqlite3
from catalogue import Catalogue
from database import Postgres

TABLES = ('films', 'state', 'visitors', 'ai_usage', 'poster_jobs', 'synopsis_jobs',
          'video_messages', 'contact_requests', 'contact_threads', 'reply_sessions', 'channel_films',
          'film_metadata', 'random_history', 'film_reports', 'technical_alerts')


def migrate(source, destination):
    source = sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True)
    target = Catalogue(destination)
    try:
        if not isinstance(target.db, Postgres):
            raise ValueError('La destination doit être PostgreSQL')
        counts = {}
        with target.db:
            for table in TABLES:
                if target.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                    raise ValueError('La destination doit être vide')
            source_tables={row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in TABLES:
                if table not in source_tables:
                    counts[table]=0
                    continue
                cursor = source.execute(f'SELECT * FROM {table}')
                columns = [item[0] for item in cursor.description]
                rows = cursor.fetchall()
                for row in rows:
                    target.db.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})', row)
                copied = target.db.execute(f'SELECT {",".join(columns)} FROM {table}').fetchall()
                key = lambda row: json.dumps(row, ensure_ascii=False)
                if sorted(rows, key=key) != sorted(copied, key=key):
                    raise ValueError('Vérification des données échouée : ' + table)
                counts[table] = len(rows)
            target.db.execute("SELECT setval(pg_get_serial_sequence('films','id'), coalesce(max(id),1), max(id) IS NOT NULL) FROM films")
        return counts
    finally:
        source.close()
        target.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.destination), sort_keys=True))
