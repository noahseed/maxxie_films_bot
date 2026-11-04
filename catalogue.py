"""Catalogue SQLite : références Telegram uniquement."""
import sqlite3
import unicodedata


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

    def remove(self, film_id):
        with self.db:
            return self.db.execute("DELETE FROM films WHERE id=?", (film_id,)).rowcount

    def offset(self):
        row = self.db.execute("SELECT value FROM state WHERE key='offset'").fetchone()
        return row[0] if row else 0

    def acknowledge(self, update_id):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES('offset',?)", (update_id + 1,))
