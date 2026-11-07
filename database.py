"""Connexion PostgreSQL ; SQLite reste disponible pour les tests et la migration."""
import sqlite3


class Postgres:
    def __init__(self, dsn):
        import psycopg
        self.connection = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
        self.connection.execute("SET statement_timeout TO '10s'")
        self.connection.execute("SET lock_timeout TO '5s'")
        self.transactions = []

    def execute(self, query, parameters=()):
        query = query.replace('%', '%%').replace('?', '%s')
        return self.connection.execute(query, parameters)

    def executescript(self, script):
        with self:
            for statement in script.split(';'):
                if statement.strip():
                    self.execute(statement)

    def __enter__(self):
        transaction = self.connection.transaction()
        transaction.__enter__()
        self.transactions.append(transaction)
        return self

    def __exit__(self, *error):
        return self.transactions.pop().__exit__(*error)

    def close(self):
        self.connection.close()


def connect(target):
    if str(target).startswith(('postgresql://', 'postgres://', 'dbname=')):
        return Postgres(str(target))
    return sqlite3.connect(target)
