import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clear_messages_table():
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            raise RuntimeError("DATABASE_URL environment variable not set")
        conn = psycopg2.connect(database_url, sslmode='require')
        c = conn.cursor()
        c.execute('DELETE FROM messages;')
        conn.commit()
        logger.info('Messages table cleared successfully.')
    except Exception as e:
        logger.error(f'Error clearing messages table: {e}')
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    clear_messages_table()
