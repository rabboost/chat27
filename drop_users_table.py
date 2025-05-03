import sqlite3
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def drop_users_table():
    try:
        with sqlite3.connect('chat.db') as conn:
            c = conn.cursor()
            c.execute('DROP TABLE IF EXISTS users')
            conn.commit()
            logger.info("Users table dropped successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error dropping users table: {e}")

if __name__ == "__main__":
    drop_users_table()
