# * Opens a connection to Postgres as the read-only app user.
import psycopg

from unirag.config.settings import get_settings


def connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url)
