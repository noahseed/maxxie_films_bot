"""Contrôles PostgreSQL réels, activés avec TEST_POSTGRES_DSN."""
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode
import uuid

from catalogue import Catalogue
from database import Postgres
from migrate_postgres import migrate, TABLES


@unittest.skipUnless(os.environ.get('TEST_POSTGRES_DSN'), 'PostgreSQL de test non configuré')
class MigrationTests(unittest.TestCase):
    def setUp(self):
        base = os.environ['TEST_POSTGRES_DSN']
        self.admin = Postgres(base)
        self.schema = 'migration_' + uuid.uuid4().hex
        self.admin.execute(f'CREATE SCHEMA {self.schema}')
        self.dsn = base + ('&' if '?' in base else '?') + urlencode({'options': '-csearch_path=' + self.schema})
        self.scratch = tempfile.TemporaryDirectory()
        self.source = Path(self.scratch.name) / 'source.sqlite3'
        store = Catalogue(self.source)
        film = store.add({'file_id': 'secret-file', 'file_unique_id': 'u'}, 'video', 'Été 2026 VF')
        store.link_channel(-1004428637580, film, 42)
        store.remember_visitor(9123456789)
        store.acknowledge(12345)
        store.queue_posters(-1004428637580)
        store.queue_synopses(-1004428637580)
        store.synopsis_status(-1004428637580, 42, 'done', 'Été 2026 VF\n\nRésumé français.')
        store.db.close()

    def tearDown(self):
        self.admin.execute(f'DROP SCHEMA {self.schema} CASCADE')
        self.admin.close()
        self.scratch.cleanup()

    def test_migration_preserves_all_rows_big_ids_and_sequence(self):
        counts = migrate(self.source, self.dsn)
        self.assertEqual(set(counts), set(TABLES))
        store = Catalogue(self.dsn)
        try:
            self.assertEqual(store.offset(), 12346)
            self.assertEqual(store.channel_message(-1004428637580, 1), 42)
            self.assertFalse(store.remember_visitor(9123456789))
            self.assertEqual(store.channel_synopsis(-1004428637580, 1), 'Résumé français.')
            self.assertGreater(store.add({'file_id': 'f2', 'file_unique_id': 'u2'}, 'video', 'Suite'), 1)
            with self.assertRaises(ValueError):
                migrate(self.source, self.dsn)
            self.assertEqual(store.get(1)[2], 'Été 2026 VF')
        finally:
            store.db.close()

    def test_failed_transaction_rolls_back_without_closing_connection(self):
        store = Catalogue(self.dsn)
        try:
            with self.assertRaises(RuntimeError):
                with store.db:
                    store.remember_visitor(9123456789)
                    raise RuntimeError('annuler')
            self.assertTrue(store.remember_visitor(9123456789))
        finally:
            store.db.close()
