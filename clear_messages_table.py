import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clear_messages_table():
    try:
        conn = sqlite3.connect('chat.db')
        c = conn.cursor()
        c.execute('DELETE FROM messages;')
        conn.commit()
        logger.info('Messages table cleared successfully.')
    except sqlite3.Error as e:
        logger.error(f'Error clearing messages table: {e}')
    finally:
        conn.close()

if __name__ == '__main__':
    clear_messages_table()
