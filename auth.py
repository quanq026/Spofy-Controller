import hashlib
import secrets
from datetime import datetime, timedelta
from database import (
    create_user, get_user_by_username, get_user_by_id,
    create_session, get_session, delete_session, delete_user_sessions
)

SESSION_DURATION_DAYS = 30

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, stored_hash = password_hash.split('$')
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return secrets.compare_digest(pwd_hash.hex(), stored_hash)
    except ValueError:
        return False

def generate_session_token() -> str:
    return secrets.token_urlsafe(32)

def register_user(username: str, password: str) -> dict:
    if len(username) < 3:
        return {"success": False, "error": "Tên đăng nhập phải có ít nhất 3 ký tự"}
    
    if len(password) < 4:
        return {"success": False, "error": "Mật khẩu phải có ít nhất 4 ký tự"}
    
    existing = get_user_by_username(username)
    if existing:
        return {"success": False, "error": "Tên đăng nhập đã tồn tại"}
    
    try:
        password_hash = hash_password(password)
        user_id = create_user(username, password_hash)
        return {"success": True, "user_id": user_id}
    except Exception as e:
        return {"success": False, "error": f"Lỗi tạo tài khoản: {str(e)}"}

def login_user(username: str, password: str) -> dict:
    user = get_user_by_username(username)
    if not user:
        return {"success": False, "error": "Tên đăng nhập hoặc mật khẩu không đúng"}
    
    if not verify_password(password, user['password_hash']):
        return {"success": False, "error": "Tên đăng nhập hoặc mật khẩu không đúng"}
    
    session_token = generate_session_token()
    expires_at = datetime.now() + timedelta(days=SESSION_DURATION_DAYS)
    
    try:
        create_session(user['id'], session_token, expires_at)
        return {
            "success": True,
            "session_token": session_token,
            "user_id": user['id'],
            "username": user['username'],
            "expires_at": expires_at.isoformat()
        }
    except Exception as e:
        return {"success": False, "error": f"Lỗi tạo phiên: {str(e)}"}

def validate_session(session_token: str) -> dict | None:
    if not session_token:
        return None
    
    session = get_session(session_token)
    if not session:
        return None
    
    user = get_user_by_id(session['user_id'])
    if not user:
        return None
    
    return {
        "id": user['id'],
        "username": user['username'],
        "session_token": session_token
    }

def logout_user(session_token: str) -> bool:
    try:
        delete_session(session_token)
        return True
    except Exception:
        return False

def logout_all_sessions(user_id: int) -> bool:
    try:
        delete_user_sessions(user_id)
        return True
    except Exception:
        return False
