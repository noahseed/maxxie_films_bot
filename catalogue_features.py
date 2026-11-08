"""Métadonnées durables, tirages et signalements du catalogue."""
import json
import secrets
import time


class CatalogueFeatures:
    def init_features(self):
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS film_metadata (
                film_id BIGINT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS random_history (
                user_id BIGINT NOT NULL, film_id BIGINT NOT NULL, selected_at BIGINT NOT NULL,
                PRIMARY KEY(user_id,film_id));
            CREATE TABLE IF NOT EXISTS film_reports (
                token TEXT PRIMARY KEY,user_id BIGINT NOT NULL,film_id BIGINT NOT NULL,
                reason TEXT NOT NULL,created_at BIGINT NOT NULL,status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS technical_alerts (
                key TEXT PRIMARY KEY,sent_at BIGINT NOT NULL);
        ''')

    def metadata(self, film_id):
        row = self.db.execute('SELECT data FROM film_metadata WHERE film_id=?', (film_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_metadata(self, film_id, values):
        data = self.metadata(film_id)
        data.update(values)
        with self.db:
            self.db.execute('''INSERT INTO film_metadata VALUES(?,?) ON CONFLICT(film_id)
                DO UPDATE SET data=excluded.data''', (film_id, json.dumps(data, ensure_ascii=False)))
        return data

    def choose_random(self, channel_id, user_id, genre='', year=''):
        rows = self.db.execute('''SELECT films.id,films.title,channel_films.message_id,coalesce(m.data,'{}')
            FROM films JOIN channel_films ON channel_films.film_id=films.id
            LEFT JOIN film_metadata m ON m.film_id=films.id
            WHERE channel_films.channel_id=?''', (channel_id,)).fetchall()
        candidates = []
        for row in rows:
            data = json.loads(row[3])
            if year and data.get('year') != year:
                continue
            if genre and genre not in data.get('genres', []):
                continue
            candidates.append(row[:3])
        if not candidates:
            return None
        now = int(time.time())
        recent = {row[0] for row in self.db.execute('''SELECT film_id FROM random_history
            WHERE user_id=? AND selected_at>? ORDER BY selected_at DESC LIMIT 10''',
            (user_id, (now - 86400) * 1_000_000_000)).fetchall()}
        pool = [row for row in candidates if row[0] not in recent]
        if not pool:
            # Cycle terminé : éviter encore le dernier film si plusieurs choix existent.
            last = self.db.execute('SELECT film_id FROM random_history WHERE user_id=? ORDER BY selected_at DESC LIMIT 1', (user_id,)).fetchone()
            pool = [row for row in candidates if not last or row[0] != last[0]] or candidates
        chosen = secrets.choice(pool)
        with self.db:
            self.db.execute('DELETE FROM random_history WHERE selected_at<?', ((now - 86400) * 1_000_000_000,))
            self.db.execute('''INSERT INTO random_history VALUES(?,?,?) ON CONFLICT(user_id,film_id)
                DO UPDATE SET selected_at=excluded.selected_at''', (user_id, chosen[0], time.time_ns()))
        return chosen

    def filter_values(self, channel_id):
        genres, years = set(), set()
        for raw, in self.db.execute('''SELECT m.data FROM film_metadata m JOIN channel_films c ON c.film_id=m.film_id WHERE c.channel_id=?''', (channel_id,)).fetchall():
            data = json.loads(raw)
            genres.update(data.get('genres', []))
            if data.get('year'):
                years.add(data['year'])
        return sorted(genres), sorted(years, reverse=True)

    def record_report(self, user_id, film_id, reason):
        now = int(time.time())
        with self.db:
            self.db.execute('DELETE FROM film_reports WHERE created_at<?', (now - 30 * 86400,))
            if self.db.execute('SELECT 1 FROM film_reports WHERE user_id=? AND created_at>?', (user_id, now - 60)).fetchone():
                return None
            token = secrets.token_hex(8)
            self.db.execute('INSERT INTO film_reports VALUES(?,?,?,?,?,?)', (token,user_id,film_id,reason,now,'pending'))
        return token

    def reserve_alert(self, key, interval=3600):
        now = int(time.time())
        with self.db:
            row = self.db.execute('SELECT sent_at FROM technical_alerts WHERE key=?', (key,)).fetchone()
            if row and now - row[0] < interval:
                return False
            self.db.execute('''INSERT INTO technical_alerts VALUES(?,?) ON CONFLICT(key)
                DO UPDATE SET sent_at=excluded.sent_at''', (key,now))
        return True

    def purge_film(self, film_id):
        with self.db:
            for channel, message in self.db.execute('SELECT channel_id,message_id FROM channel_films WHERE film_id=?', (film_id,)).fetchall():
                for table in ('poster_jobs','synopsis_jobs','video_messages'):
                    self.db.execute(f'DELETE FROM {table} WHERE channel_id=? AND message_id=?', (channel,message))
            for table in ('film_metadata','random_history','film_reports'):
                self.db.execute(f'DELETE FROM {table} WHERE film_id=?', (film_id,))
            self.remove(film_id)
