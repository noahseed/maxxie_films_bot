"""Catalogue SQLite : références Telegram uniquement."""
import sqlite3
import unicodedata
import time
import secrets
import json
from search import ranked_results


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


class Catalogue:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS films (
                id INTEGER PRIMARY KEY, unique_id TEXT NOT NULL UNIQUE,
                file_id TEXT NOT NULL, kind TEXT NOT NULL,
                title TEXT NOT NULL, search_title TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS visitors (user_id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS ai_usage (
                day TEXT NOT NULL, user_id INTEGER NOT NULL, requests INTEGER NOT NULL,
                PRIMARY KEY(day,user_id));
            CREATE TABLE IF NOT EXISTS poster_jobs (
                channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, film_id INTEGER NOT NULL,
                title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                PRIMARY KEY(channel_id,message_id));
            CREATE TABLE IF NOT EXISTS video_messages (
                channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, media TEXT NOT NULL,
                PRIMARY KEY(channel_id,message_id));
            CREATE TABLE IF NOT EXISTS contact_requests (
                user_id INTEGER PRIMARY KEY, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS contact_threads (
                token TEXT PRIMARY KEY, owner_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS reply_sessions (
                owner_id INTEGER PRIMARY KEY, token TEXT NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS channel_films (
                channel_id INTEGER NOT NULL, film_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL, PRIMARY KEY(channel_id, film_id));
        """)

    def add(self, media, kind, title):
        title = title.strip()[:200]
        if not title:
            raise ValueError("Titre manquant")
        with self.db:
            self.db.execute("""INSERT INTO films(unique_id,file_id,kind,title,search_title)
                VALUES(?,?,?,?,?) ON CONFLICT(unique_id) DO UPDATE SET
                file_id=excluded.file_id,kind=excluded.kind,title=excluded.title,
                search_title=excluded.search_title""",
                (media["file_unique_id"], media["file_id"], kind, title, normalize(title)))
        return self.db.execute("SELECT id FROM films WHERE unique_id=?",
                               (media["file_unique_id"],)).fetchone()[0]

    def search(self, query="", page=0):
        query = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return self.db.execute("""SELECT id,title FROM films
            WHERE search_title LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT 11 OFFSET ?""",
            (f"%{query}%", page * 10)).fetchall()

    def get(self, film_id):
        return self.db.execute("SELECT file_id,kind,title FROM films WHERE id=?",
                               (film_id,)).fetchone()

    def search_channel(self, channel_id, query):
        # Conserver le sens littéral des recherches contenant des caractères spéciaux.
        if not any(c.isalnum() for c in query):
            escaped = normalize(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            return self.db.execute("""SELECT films.id,films.title,channel_films.message_id
                FROM films JOIN channel_films ON channel_films.film_id=films.id
                WHERE channel_films.channel_id=? AND films.search_title LIKE ? ESCAPE '\\'
                ORDER BY films.id DESC LIMIT 11""", (channel_id, f"%{escaped}%")).fetchall()
        rows = self.db.execute("""SELECT films.id,films.title,channel_films.message_id
            FROM films JOIN channel_films ON channel_films.film_id=films.id
            WHERE channel_films.channel_id=?""", (channel_id,))
        return ranked_results(rows, query)

    def remove(self, film_id):
        with self.db:
            self.db.execute("DELETE FROM channel_films WHERE film_id=?", (film_id,))
            return self.db.execute("DELETE FROM films WHERE id=?", (film_id,)).rowcount

    def channel_message(self, channel_id, film_id):
        row = self.db.execute("SELECT message_id FROM channel_films WHERE channel_id=? AND film_id=?",
                              (channel_id, film_id)).fetchone()
        return row[0] if row else None

    def published_file(self, channel_id, unique_id):
        return self.db.execute("""SELECT films.id, films.title, channel_films.message_id
            FROM films JOIN channel_films ON channel_films.film_id=films.id
            WHERE channel_films.channel_id=? AND films.unique_id=?""",
            (channel_id, unique_id)).fetchone()

    def link_channel(self, channel_id, film_id, message_id):
        with self.db:
            # Un remplacement de fichier dans un message retire l’ancienne association.
            self.db.execute("DELETE FROM channel_films WHERE channel_id=? AND message_id=?",
                            (channel_id, message_id))
            self.db.execute("INSERT OR REPLACE INTO channel_films VALUES(?,?,?)",
                            (channel_id, film_id, message_id))

    def offset(self):
        row = self.db.execute("SELECT value FROM state WHERE key='offset'").fetchone()
        return row[0] if row else 0

    def remember_visitor(self, user_id):
        with self.db:
            return self.db.execute("INSERT OR IGNORE INTO visitors VALUES(?)", (user_id,)).rowcount == 1

    def request_contact(self, user_id):
        with self.db:
            self.db.execute("DELETE FROM contact_requests WHERE expires_at<=?", (int(time.time()),))
            self.db.execute("INSERT OR REPLACE INTO contact_requests VALUES(?,?)",
                            (user_id, int(time.time()) + 900))

    def contact_pending(self, user_id):
        return self.db.execute("SELECT 1 FROM contact_requests WHERE user_id=? AND expires_at>?",
                               (user_id, int(time.time()))).fetchone() is not None

    def clear_contact(self, user_id):
        with self.db:
            self.db.execute("DELETE FROM contact_requests WHERE user_id=?", (user_id,))

    def create_contact_thread(self, owner_id, user_id):
        token = secrets.token_urlsafe(12)
        now = int(time.time())
        with self.db:
            self.db.execute("DELETE FROM contact_threads WHERE expires_at<=?", (now,))
            self.db.execute("DELETE FROM reply_sessions WHERE expires_at<=?", (now,))
            self.db.execute("INSERT INTO contact_threads VALUES(?,?,?,?)",
                            (token, owner_id, user_id, now + 7 * 86400))
        return token

    def begin_reply(self, owner_id, token):
        row = self.db.execute("SELECT user_id FROM contact_threads WHERE owner_id=? AND token=? AND expires_at>?",
                              (owner_id, token, int(time.time()))).fetchone()
        if row:
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO reply_sessions VALUES(?,?,?)",
                                (owner_id, token, int(time.time()) + 900))
            return row[0]

    def reply_target(self, owner_id):
        row = self.db.execute("""SELECT contact_threads.user_id FROM reply_sessions
            JOIN contact_threads ON reply_sessions.token=contact_threads.token
            AND reply_sessions.owner_id=contact_threads.owner_id
            WHERE reply_sessions.owner_id=? AND reply_sessions.expires_at>? AND contact_threads.expires_at>?""",
            (owner_id, int(time.time()), int(time.time()))).fetchone()
        return row[0] if row else None

    def clear_reply(self, owner_id):
        with self.db:
            self.db.execute("DELETE FROM reply_sessions WHERE owner_id=?", (owner_id,))

    def acknowledge(self, update_id):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES('offset',?)", (update_id + 1,))

    def reserve_ai(self, user_id, per_user=20, total=100):
        day = time.strftime('%Y-%m-%d', time.gmtime())
        with self.db:
            self.db.execute("DELETE FROM ai_usage WHERE day<>?", (day,))
            used = self.db.execute("SELECT requests FROM ai_usage WHERE day=? AND user_id=?",
                                   (day, user_id)).fetchone()
            overall = self.db.execute("SELECT coalesce(sum(requests),0) FROM ai_usage WHERE day=?", (day,)).fetchone()[0]
            if (used and used[0] >= per_user) or overall >= total:
                return False
            self.db.execute("INSERT INTO ai_usage VALUES(?,?,1) ON CONFLICT(day,user_id) DO UPDATE SET requests=requests+1",
                            (day, user_id))
            return True

    def queue_posters(self, channel_id):
        with self.db:
            # Migration autorisée : pour les anciens posts, conserver le titre connu.
            for message_id, file_id, title in self.db.execute("""SELECT channel_films.message_id,films.file_id,films.title
                FROM channel_films JOIN films ON films.id=channel_films.film_id
                WHERE channel_films.channel_id=? AND films.kind='video'""", (channel_id,)).fetchall():
                media = json.dumps({'type': 'video', 'media': file_id, 'caption': title})
                self.db.execute('INSERT OR IGNORE INTO video_messages VALUES(?,?,?)', (channel_id, message_id, media))
            self.db.execute("UPDATE poster_jobs SET status='queued' WHERE channel_id=? AND status IN ('sent','uncertain')", (channel_id,))
            self.db.execute("""INSERT INTO poster_jobs(channel_id,message_id,film_id,title)
                SELECT channel_films.channel_id,channel_films.message_id,films.id,films.title
                FROM channel_films JOIN films ON films.id=channel_films.film_id
                WHERE channel_films.channel_id=? AND films.kind='video'
                ON CONFLICT(channel_id,message_id) DO UPDATE SET
                    film_id=excluded.film_id,title=excluded.title,status='queued'
                WHERE poster_jobs.film_id<>excluded.film_id OR
                    (poster_jobs.title<>excluded.title AND poster_jobs.status NOT IN ('covered','cover_uncertain'))""", (channel_id,))

    def next_poster(self, channel_id):
        return self.db.execute("""SELECT poster_jobs.message_id,poster_jobs.film_id,poster_jobs.title
            FROM poster_jobs JOIN channel_films ON channel_films.channel_id=poster_jobs.channel_id
                AND channel_films.message_id=poster_jobs.message_id AND channel_films.film_id=poster_jobs.film_id
            JOIN films ON films.id=poster_jobs.film_id
            WHERE poster_jobs.channel_id=? AND poster_jobs.status='queued' AND films.kind='video'
            ORDER BY poster_jobs.message_id LIMIT 1""", (channel_id,)).fetchone()

    def poster_status(self, channel_id, message_id, status):
        with self.db:
            self.db.execute("UPDATE poster_jobs SET status=? WHERE channel_id=? AND message_id=?",
                            (status, channel_id, message_id))

    def remember_video(self, channel_id, message):
        video = message.get('video', {})
        if not video.get('file_id'):
            return
        media = {'type': 'video', 'media': video['file_id'], 'caption': message.get('caption', '')}
        for key in ('width', 'height', 'duration', 'start_timestamp'):
            if key in video:
                media[key] = video[key]
        for key in ('caption_entities', 'has_spoiler', 'show_caption_above_media'):
            if key in message:
                media[key] = message[key]
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO video_messages VALUES(?,?,?)',
                            (channel_id, message['message_id'], json.dumps(media)))

    def video_message(self, channel_id, message_id):
        row = self.db.execute('SELECT media FROM video_messages WHERE channel_id=? AND message_id=?',
                              (channel_id, message_id)).fetchone()
        return json.loads(row[0]) if row else None
