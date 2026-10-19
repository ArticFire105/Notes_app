"""Open a backend database connection for ingestion and later SQL operations.
Register pgvector's adapters so vectors use the database's vector type.
The connection context commits on success, rolls back on error, and closes.
"""

from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from app.config import Settings


@contextmanager
def get_conn():
    settings = Settings()
    # Unwrap only at the driver boundary; never include the URL in diagnostics.
    with psycopg.connect(
        settings.database_url.get_secret_value(), connect_timeout=10
    ) as connection:
        register_vector(connection)
        yield connection
