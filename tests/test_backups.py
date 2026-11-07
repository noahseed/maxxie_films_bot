import json
from pathlib import Path
import sqlite3
import stat
import tarfile
import tempfile
import unittest
from contextlib import closing

from backups import make_backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        root = Path(self.scratch.name)
        self.database, self.config = root / 'live.sqlite3', root / 'config.env'
        self.code, self.units, self.destination = root / 'code', root / 'systemd', root / 'backups'
        self.code.mkdir()
        self.units.mkdir()
        for name in ('bot.py', 'catalogue.py', 'search.py', 'telegram_api.py', 'openai_api.py',
                     'posters.py', 'configure.py', 'configure_openai.py', 'configure_posters.py', 'backups.py'):
            (self.code / name).write_text('# code')
        for name in ('maxxie-films-bot.service', 'maxxie-films-backup.service', 'maxxie-films-backup.timer'):
            (self.units / name).write_text('[Unit]')
        self.config.write_text('BOT_TOKEN=fake-test-token')
        self.writer = sqlite3.connect(self.database)
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.execute('CREATE TABLE films (title TEXT)')
        self.writer.execute("INSERT INTO films VALUES('Matrix')")
        self.writer.commit()

    def tearDown(self):
        self.writer.close()
        self.scratch.cleanup()

    def backup(self, keep=14):
        return make_backup(self.database, self.config, self.code, self.units, self.destination, keep)

    def test_live_wal_database_can_be_restored_and_archive_is_private(self):
        archive_path = self.backup()
        self.assertEqual(stat.S_IMODE(archive_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o700)
        with tarfile.open(archive_path) as archive:
            restored = self.database.parent / 'restored.sqlite3'
            restored.write_bytes(archive.extractfile('data/catalogue.sqlite3').read())
            self.assertEqual(archive.extractfile('config/maxxie-films-bot.env').read(), b'BOT_TOKEN=fake-test-token')
            manifest = json.load(archive.extractfile('manifest.json'))
            self.assertIn('data/catalogue.sqlite3', manifest)
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('SELECT title FROM films').fetchall(), [('Matrix',)])

    def test_retention_preserves_two_most_recent_archives(self):
        first, second, third = self.backup(2), self.backup(2), self.backup(2)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(third.exists())

    def test_missing_configuration_does_not_prune_previous_backup(self):
        first = self.backup(1)
        self.config.unlink()
        with self.assertRaises(FileNotFoundError):
            self.backup(1)
        self.assertTrue(first.exists())
        self.assertEqual(list(self.destination.glob('*.partial')), [])


if __name__ == '__main__':
    unittest.main()
