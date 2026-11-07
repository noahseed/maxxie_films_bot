"""Exécuter les tests du bot dans des schémas PostgreSQL isolés (base de test)."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import Postgres, connect


def test_connection(target):
    if str(target) != ':memory:':
        return connect(target)
    connection = Postgres(os.environ['TEST_POSTGRES_DSN'])
    schema = 'test_' + uuid.uuid4().hex
    connection.execute(f'CREATE SCHEMA {schema}')
    connection.execute(f'SET search_path TO {schema}')
    original_close = connection.close
    def close():
        connection.execute(f'DROP SCHEMA {schema} CASCADE')
        original_close()
    connection.close = close
    return connection


if __name__ == '__main__':
    with patch('catalogue.connect', side_effect=test_connection):
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_*.py')
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
