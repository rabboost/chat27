import os
import psycopg2
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def drop_users_table():
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            raise RuntimeError("DATABASE_URL environment variable not set")
        with psycopg2.connect(database_url, sslmode='require') as conn:
            with conn.cursor() as c:
                c.execute('DROP TABLE IF EXISTS users CASCADE')
                conn.commit()
                logger.info("Users table dropped successfully.")
    except Exception as e:
        logger.error(f"Error dropping users table: {e}")

if __name__ == "__main__":
    drop_users_table()
