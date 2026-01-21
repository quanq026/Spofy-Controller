import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "spotify_controller.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                client_id TEXT DEFAULT '',
                client_secret TEXT DEFAULT '',
                gist_id TEXT DEFAULT '',
                github_token TEXT DEFAULT '',
                gist_filename TEXT DEFAULT 'spotify_tokens.json',
                app_api_key TEXT DEFAULT '',
                redirect_uri TEXT DEFAULT '',
                validated INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Migration: Add validated column if not exists
        try:
            cursor.execute("ALTER TABLE user_configs ADD COLUMN validated INTEGER DEFAULT 0")
        except:
            pass  # Column already exists
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

def create_user(username: str, password_hash: str) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO user_configs (user_id) VALUES (?)",
            (user_id,)
        )
        return user_id

def get_user_by_username(username: str) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_session(user_id: int, session_token: str, expires_at: datetime) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (user_id, session_token, expires_at) VALUES (?, ?, ?)",
            (user_id, session_token, expires_at)
        )
        return cursor.lastrowid

def get_session(session_token: str) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE session_token = ? AND expires_at > datetime('now')",
            (session_token,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_session(session_token: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))

def delete_user_sessions(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

def get_user_config(user_id: int) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_configs WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_user_config(user_id: int, **kwargs) -> bool:
    allowed_fields = ['client_id', 'client_secret', 'gist_id', 'github_token', 'gist_filename', 'app_api_key', 'redirect_uri', 'validated']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if not updates:
        return False
    
    updates['updated_at'] = datetime.now()
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [user_id]
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE user_configs SET {set_clause} WHERE user_id = ?",
            values
        )
        return cursor.rowcount > 0

def cleanup_expired_sessions():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
        return cursor.rowcount

def get_user_by_api_key(api_key: str) -> dict | None:
    """Get user by their API key"""
    if not api_key:
        return None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username FROM users u
            JOIN user_configs c ON u.id = c.user_id
            WHERE c.app_api_key = ?
        """, (api_key,))
        row = cursor.fetchone()
        return dict(row) if row else None

init_db()
