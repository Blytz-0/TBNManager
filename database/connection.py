# database/connection.py
"""
MySQL Database Connection Pool for TBNManager

Provides async-compatible connection management using mysql-connector-python
with connection pooling for better performance.
"""

import mysql.connector
from mysql.connector import pooling
from contextlib import contextmanager
from config.settings import DATABASE_CONFIG
import logging

logger = logging.getLogger(__name__)

# Connection pool (initialized lazily)
_connection_pool = None


def get_pool():
    """Get or create the connection pool."""
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = pooling.MySQLConnectionPool(
                pool_name="tbnmanager_pool",
                pool_size=5,
                pool_reset_session=True,
                host=DATABASE_CONFIG['host'],
                port=DATABASE_CONFIG.get('port', 3306),
                user=DATABASE_CONFIG['user'],
                password=DATABASE_CONFIG['password'],
                database=DATABASE_CONFIG['database'],
                autocommit=False
            )
            logger.info("Database connection pool created successfully")
        except mysql.connector.Error as err:
            logger.error(f"Failed to create connection pool: {err}")
            raise
    return _connection_pool


@contextmanager
def get_connection():
    """
    Context manager for getting a database connection from the pool.
    Automatically returns connection to pool when done.

    Usage:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM guilds")
            results = cursor.fetchall()
            conn.commit()  # if making changes
    """
    conn = None
    try:
        conn = get_pool().get_connection()
        yield conn
    except mysql.connector.Error as err:
        logger.error(f"Database error: {err}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


@contextmanager
def get_cursor(dictionary=True):
    """
    Context manager for getting a cursor with automatic connection handling.

    Args:
        dictionary: If True, returns results as dictionaries instead of tuples

    Usage:
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM guilds WHERE guild_id = %s", (guild_id,))
            guild = cursor.fetchone()
    """
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor
            conn.commit()
        except mysql.connector.Error as err:
            conn.rollback()
            logger.error(f"Cursor error: {err}")
            raise
        finally:
            cursor.close()


def test_connection():
    """Test database connectivity. Returns True if successful."""
    try:
        with get_cursor() as cursor:
            cursor.execute("SELECT 1 AS test")
            result = cursor.fetchone()
            return result.get('test') == 1
    except Exception as err:
        logger.error(f"Connection test failed: {err}")
        return False


def close_pool():
    """Close all connections in the pool. Call on bot shutdown."""
    global _connection_pool
    if _connection_pool:
        # Note: mysql-connector-python pools don't have explicit close
        # Connections are closed when returned to pool
        _connection_pool = None
        logger.info("Database connection pool closed")
