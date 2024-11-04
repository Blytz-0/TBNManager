from mysql.connector import connect
from config.config import DATABASE_CONFIG

def get_connection():
    return connect(
        host=DATABASE_CONFIG["host"],
        user=DATABASE_CONFIG["user"],
        password=DATABASE_CONFIG["password"],
        database=DATABASE_CONFIG["database"]
    )

