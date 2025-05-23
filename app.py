import psycopg2
import psycopg2.extras
import logging
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
import hashlib
import uuid
from markupsafe import Markup
import os
import os
from dotenv import load_dotenv

# Load environment variables from .env file only if not in production
if os.environ.get('FLASK_ENV') != 'production':
    load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Log the DATABASE_URL environment variable at startup for debugging
database_url = os.environ.get('DATABASE_URL')
if database_url:
    logger.info(f"DATABASE_URL environment variable is set: {database_url[:40]}...")  # Log partial for security
else:
    logger.error("DATABASE_URL environment variable is NOT set")

def get_db_connection():
    """Helper function to get a PostgreSQL connection with dict cursor."""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        raise RuntimeError("DATABASE_URL environment variable not set")
    conn = psycopg2.connect(database_url, sslmode='require')
    return conn

def emit_system_message(msg, suppress_emit=False):
    """Helper function to log and emit a system message via socketio."""
    logger.info(f"System message: {msg}")
    message_type = 'system' if suppress_emit else 'common'
    sent_at = insert_message('System', msg, message_type=message_type)
    if not suppress_emit:
        socketio.emit('message', {'username': 'System', 'msg': msg, 'sent_at': sent_at, 'message_type': message_type})

def user_exists(field, value):
    """Helper function to check if a user exists by a specific field."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                c.execute(f'SELECT 1 FROM users WHERE {field} = %s', (value,))
                return c.fetchone() is not None
    except Exception as e:
        logger.error(f"Database error checking user existence by {field}: {e}")
        return False

def setup_user_session(user):
    """Helper function to set up user session and update user status."""
    session['user_id'] = user['user_id']
    session['username'] = user['username']
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute('UPDATE users SET last_seen_at = CURRENT_TIMESTAMP, is_online = TRUE WHERE user_id = %s', (user['user_id'],))
                conn.commit()
    except Exception as e:
        logger.error(f"Database error updating user status for user_id {user['user_id']}: {e}")

def init_db():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                # Create users table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE,
                        email VARCHAR(100) UNIQUE,
                        phone VARCHAR(20) UNIQUE NOT NULL,
                        password_hash VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen_at TIMESTAMP,
                        is_online BOOLEAN DEFAULT FALSE,
                        is_blocked BOOLEAN DEFAULT FALSE,
                        avatar_url VARCHAR(255)
                    )
                ''')
                # Ensure system user with user_id 1 exists
                c.execute('SELECT * FROM users WHERE user_id = 1')
                system_user = c.fetchone()
                if not system_user:
                    c.execute('''
                        INSERT INTO users (user_id, username, email, phone, password_hash, created_at, last_edited_at, is_online, is_blocked)
                        VALUES (1, 'System', 'sys@mail.ru', '0', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, FALSE, FALSE)
                    ''')
                # Create messages table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        msg TEXT NOT NULL,
                        message_type TEXT DEFAULT 'common',
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # Create user_profiles table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
                        last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        first_name VARCHAR(50),
                        last_name VARCHAR(50),
                        birth_date DATE,
                        bio TEXT,
                        status VARCHAR(100)
                    )
                ''')
                # Create user_settings table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
                        last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        theme VARCHAR(20) DEFAULT 'dark',
                        language VARCHAR(10) DEFAULT 'en',
                        notification_enabled BOOLEAN DEFAULT TRUE,
                        privacy_level SMALLINT DEFAULT 0
                    )
                ''')
                # Create user_contacts table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_contacts (
                        user_id INTEGER REFERENCES users(user_id),
                        last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        contact_id BIGINT REFERENCES users(user_id),
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, contact_id)
                    )
                ''')
                # Create user_sessions table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id INTEGER REFERENCES users(user_id),
                        device_info VARCHAR(255),
                        ip_address VARCHAR(45),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP
                    )
                ''')
                # Create index on messages.user_id for performance
                c.execute('CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);')
                conn.commit()
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

init_db()

@app.route('/')
def index():
    username = session.get('username')
    ip_address = request.remote_addr or 'Unknown IP'
    user_display = username if username else 'Anonymous'
    logger.info(f"Rendering index page for user: {username}")
    try:
        if not session.get('loaded_login_page_logged'):
            emit_system_message(f'{user_display} loaded login page from IP {ip_address}.', suppress_emit=True)
            session['loaded_login_page_logged'] = True
    except Exception as e:
        logger.error(f"Error logging page load via socketio message: {e}")
    theme = 'dark'
    return render_template('index.html', username=username, theme=theme)

@app.route('/logout')
def logout():
    session.clear()
    logger.info("User logged out and session cleared")
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    ip_address = request.remote_addr or 'Unknown IP'
    if not username or not password:
        flash('Username and password are required.')
        logger.warning("Login attempt with missing username or password")
        try:
            emit_system_message(f'Failed login attempt with missing credentials from IP {ip_address}.', suppress_emit=True)
        except Exception as e:
            logger.error(f"Error logging failed login attempt via socketio message: {e}")
        return redirect(url_for('index'))
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
                c.execute('SELECT * FROM users WHERE username = %s AND password_hash = %s', (username, password_hash))
                user = c.fetchone()
                if user:
                    setup_user_session(user)
                    emit_system_message(f'{username} logged in successfully from IP {ip_address}.', suppress_emit=True)
                    logger.info(f"User {username} logged in successfully")
                    return redirect(url_for('index'))
                else:
                    flash('Invalid username or password.')
                    logger.warning(f"Invalid login attempt for username: {username}")
                    try:
                        emit_system_message(f'Failed login attempt for username {username} from IP {ip_address}.', suppress_emit=True)
                    except Exception as e:
                        logger.error(f"Error logging failed login attempt via socketio message: {e}")
                    return redirect(url_for('index'))
    except Exception as e:
        flash('Database error during login.')
        logger.error(f"Database error during login for username {username}: {e}")
        return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    data = request.form
    username = data.get('username')
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    birth_date = data.get('birth_date')
    bio = data.get('bio')
    status = data.get('status')
    theme = data.get('theme', 'light')
    language = data.get('language', 'en')
    notification_enabled = data.get('notification_enabled', 'true').lower() == 'true'
    privacy_level = int(data.get('privacy_level', 0))

    logger.info(f"Registration attempt with data: username={username}, email={email}, phone={phone}, first_name={first_name}, last_name={last_name}, birth_date={birth_date}, bio={bio}, status={status}, theme={theme}, language={language}, notification_enabled={notification_enabled}, privacy_level={privacy_level}")

    if not username or not password:
        flash('Username and password are required.')
        logger.warning("Registration attempt with missing username or password")
        return redirect(url_for('index'))

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                if user_exists('username', username):
                    flash('Username already exists.')
                    logger.warning(f"Registration failed: username {username} already exists.")
                    return redirect(url_for('index'))
                if email and user_exists('email', email):
                    flash('Email already exists.')
                    logger.warning(f"Registration failed: email {email} already exists.")
                    return redirect(url_for('index'))
                if phone and user_exists('phone', phone):
                    flash('Phone number already exists.')
                    logger.warning(f"Registration failed: phone {phone} already exists.")
                    return redirect(url_for('index'))

                logger.info("Inserting new user into users table")
                c.execute('''
                    INSERT INTO users (username, email, phone, password_hash, created_at, last_edited_at, is_online, is_blocked)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, FALSE, FALSE)
                ''', (username, email, phone, password_hash))
                c.execute('SELECT currval(pg_get_serial_sequence(\'users\', \'user_id\'))')
                user_id = c.fetchone()[0]

                logger.info(f"Inserted user with user_id: {user_id}")

                logger.info("Inserting user profile")
                c.execute('''
                    INSERT INTO user_profiles (user_id, last_edited_at, first_name, last_name, birth_date, bio, status)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
                ''', (user_id, first_name, last_name, birth_date, bio, status))
                logger.info("User profile inserted")

                logger.info("Inserting user settings")
                c.execute('''
                    INSERT INTO user_settings (user_id, last_edited_at, theme, language, notification_enabled, privacy_level)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
                ''', (user_id, theme, language, notification_enabled, privacy_level))
                logger.info("User settings inserted")

                conn.commit()
                flash('Registration successful. Please log in.')
                logger.info(f"User {username} registered successfully")
                return redirect(url_for('index'))
    except Exception as e:
        flash('Database error during registration.')
        logger.error(f"Database error during registration for username {username}: {e}")
        return redirect(url_for('index'))

@socketio.on('connect')
def on_connect():
    logger.info(f'Client connected: {request.sid}')
    user_id = session.get('user_id')
    username = session.get('username')
    if user_id and username:
        logger.info(f'Authenticated user {username} connected with session id {request.sid}')
        try:
            with get_db_connection() as conn:
                with conn.cursor() as c:
                    c.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
                    user_row = c.fetchone()
                    if not user_row:
                        logger.warning(f'User id {user_id} from session not found in database')
                        return
                    c.execute('SELECT sent_at FROM messages WHERE id = (SELECT MAX(id) FROM messages WHERE user_id = 1)')
                    sent_at_row = c.fetchone()
                    sent_at = sent_at_row[0] if sent_at_row else None
                    c.execute('''
                        SELECT users.username, messages.msg, messages.sent_at
                        FROM messages
                        JOIN users ON messages.user_id = users.user_id
                        WHERE messages.message_type != 'system'
                        ORDER BY messages.id ASC
                    ''')
                    messages = c.fetchall()
        except Exception as e:
            logger.error(f"Database error in on_connect join logic: {e}")
            messages = []
            sent_at = None
        emit('load_messages', [{'username': username_msg, 'msg': msg, 'sent_at': sent_at_msg} for username_msg, msg, sent_at_msg in messages], room=request.sid)
        emit_system_message(f'{username} has entered the chat.', suppress_emit=False)
    else:
        logger.info(f'Unauthenticated client connected with session id {request.sid}')

@socketio.on('disconnect')
def on_disconnect():
    logger.info(f'Client disconnected: {request.sid}')

@socketio.on('join')
def on_join(data):
    logger.info('join event received but ignored because join logic is handled in on_connect')
    pass

def insert_message(username, msg, message_type='common'):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute('SELECT user_id FROM users WHERE username = %s', (username,))
                user_id_row = c.fetchone()
                if user_id_row is None:
                    c.execute('INSERT INTO users (username) VALUES (%s) RETURNING user_id', (username,))
                    user_id = c.fetchone()[0]
                else:
                    user_id = user_id_row[0]
                c.execute('INSERT INTO messages (user_id, msg, message_type, sent_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)', (user_id, msg, message_type))
                conn.commit()
                c.execute('SELECT sent_at FROM messages WHERE id = (SELECT MAX(id) FROM messages WHERE user_id = %s)', (user_id,))
                sent_at_row = c.fetchone()
                sent_at = sent_at_row[0] if sent_at_row else None
                return sent_at
    except Exception as e:
        logger.error(f"Database error in insert_message: {e}")
        return None

@socketio.on('message')
def handle_message(data):
    username = data['username']
    msg = data['msg']
    logger.info(f'Message from {username}: {msg}')
    sent_at = insert_message(username, msg)
    if sent_at is None:
        emit('message', {'username': username, 'msg': msg, 'sent_at': None}, broadcast=True)
        return
    emit('message', {'username': username, 'msg': msg, 'sent_at': sent_at}, broadcast=True)

@app.route('/check_data')
def check_data():
    logger.info("check_data route accessed")
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute("""SELECT table_name FROM information_schema.tables WHERE table_schema='public'""")
                tables = [row[0] for row in c.fetchall()]
                tables_html = ""
                for table in tables:
                    c.execute(f"SELECT * FROM {table}")
                    rows = c.fetchall()
                    columns = [desc[0] for desc in c.description] if rows else []
                    table_html = f"<h3>Table: {table}</h3>"
                    table_html += "<table class='table table-striped table-bordered table-dark' cellpadding='5' cellspacing='0'><thead><tr>"
                    for col in columns:
                        table_html += f"<th>{col}</th>"
                    table_html += "</tr></thead><tbody>"
                    for row in rows:
                        table_html += "<tr>"
                        for col in columns:
                            table_html += f"<td>{row[columns.index(col)]}</td>"
                        table_html += "</tr>"
                    table_html += "</tbody></table><br/>"
                    tables_html += table_html
    except Exception as e:
        tables_html = f"<p>Error loading data: {e}</p>"
    return f"""
<html>
<head>
    <title>Database Tables</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootswatch@4.5.2/dist/darkly/bootstrap.min.css" crossorigin="anonymous">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #121212;
            color: #e0e0e0;
        }}
        h2, h3 {{
            color: #e0e0e0;
        }}
    </style>
</head>
<body>
<div class="container">
    <h2>Database Tables Content</h2>
    {tables_html}
</div>
</body>
</html>
"""

@app.route('/get_path_files')
def get_path_files():
    logger.info("get_path_files route accessed")
    try:
        current_path = os.path.abspath(os.getcwd())
        files = os.listdir(current_path)
        return jsonify({
            'path': current_path,
            'files': files
        })
    except Exception as e:
        logger.error(f"Error getting path and files: {e}")
        return jsonify({'error': 'Failed to get path and files'}), 500

if __name__ == '__main__':
    import eventlet
    import eventlet.wsgi
    import os

    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 5000))
    if debug_mode:
        socketio.run(app, debug=True)
    else:
        # Use eventlet WSGI server for production
        eventlet.wsgi.server(eventlet.listen(('', port)), app)
