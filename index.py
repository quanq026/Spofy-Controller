from fastapi import FastAPI, HTTPException, Header, Depends, Request, Response, Cookie
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse, JSONResponse
from urllib.parse import quote
from pydantic import BaseModel
import requests
import os, json, time, base64, secrets
from dotenv import load_dotenv

load_dotenv()

import database
import auth as auth_module

from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
if ENVIRONMENT == "production":
    origins = [
        os.getenv("PRODUCTION_ORIGIN", "https://your-app.vercel.app"),
    ]
else:
    origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type"],
)

oauth_pending_states: dict = {}

# ======================= Pydantic Models =======================
class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    gist_id: str
    github_token: str
    gist_filename: str = "spotify_tokens.json"
    redirect_uri: str = ""

# ======================= Auth Helpers =======================
def get_current_user(session_token: str = Cookie(None, alias="session_token")):
    """Get current logged in user from session cookie"""
    if not session_token:
        return None
    return auth_module.validate_session(session_token)

def require_auth(session_token: str = Cookie(None, alias="session_token")):
    """Require authentication - raise 401 if not logged in"""
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def get_user_config(user_id: int) -> dict:
    """Get user's Spotify/Gist configuration"""
    config = database.get_user_config(user_id)
    if config:
        return {
            "client_id": config.get("client_id", ""),
            "client_secret": config.get("client_secret", ""),
            "gist_id": config.get("gist_id", ""),
            "github_token": config.get("github_token", ""),
            "gist_filename": config.get("gist_filename") or "spotify_tokens.json",
            "app_api_key": config.get("app_api_key", ""),
            "redirect_uri": config.get("redirect_uri", ""),
            "validated": config.get("validated", 0)
        }
    return None

async def verify_api_key(request: Request, x_api_key: str = Header(None), session_token: str = Cookie(None, alias="session_token")):
    """Verify session or API key (URL param or header)"""
    # Check session first
    user = get_current_user(session_token)
    if user:
        return {"user": user, "via": "session"}
    
    # Check API key from URL param or header
    api_key = request.query_params.get("api_key") or x_api_key
    if api_key:
        user = database.get_user_by_api_key(api_key)
        if user:
            return {"user": user, "via": "api_key"}
    
    raise HTTPException(status_code=401, detail="Authentication required")


def load_token_from_gist_for_user(user_id: int = None, config: dict = None) -> dict:
    """Load tokens from Gist - requires user config"""
    if not config:
        return {"access_token": "", "refresh_token": "", "expires_at": 0}
    
    gist_id = config.get("gist_id")
    github_token = config.get("github_token")
    gist_filename = config.get("gist_filename") or "spotify_tokens.json"
    
    if not gist_id or not github_token:
        return {"access_token": "", "refresh_token": "", "expires_at": 0}

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {github_token}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if gist_filename in data["files"]:
                content = data["files"][gist_filename]["content"]
                return json.loads(content)
    except Exception as e:
        print(f"[ERROR] Load Gist failed: {e}")
    return {"access_token": "", "refresh_token": "", "expires_at": 0}

def save_token_to_gist(access_token: str, refresh_token: str, expires_at: float, config: dict = None):
    """Save tokens to Gist - requires user config"""
    if not config:
        print("[WARN] No config provided")
        return False
    
    gist_id = config.get("gist_id")
    github_token = config.get("github_token")
    gist_filename = config.get("gist_filename") or "spotify_tokens.json"
    
    if not gist_id or not github_token:
        print("[WARN] Gist not configured")
        return False

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"token {github_token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "files": {
            gist_filename: {
                "content": json.dumps(
                    {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "expires_at": expires_at,
                    },
                    indent=2,
                )
            }
        }
    }

    try:
        res = requests.patch(url, headers=headers, json=data, timeout=10)
        print(f"[DEBUG] Gist save status: {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[ERROR] Save Gist failed: {e}")
        return False

def renew_access_token(refresh_token: str, config: dict = None):
    """Renew access token using refresh token - requires config"""
    if not config:
        return None
    
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    
    if not client_id or not client_secret:
        return None
    
    url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

    res = requests.post(url, headers=headers, data=data, timeout=10)
    print(f"[DEBUG] Renew status: {res.status_code}")

    if res.status_code == 200:
        token_data = res.json()
        access_token = token_data["access_token"]
        new_refresh_token = token_data.get("refresh_token", refresh_token)
        expires_at = time.time() + token_data.get("expires_in", 3600)
        save_token_to_gist(access_token, new_refresh_token, expires_at, config)
        return token_data
    else:
        print(f"[ERROR] Renew failed: {res.text[:200]}")
        return None

def get_valid_token(config: dict = None) -> str:
    """Get valid Spotify token, refreshing if needed"""
    cached = load_token_from_gist_for_user(config=config)
    access_token = cached.get("access_token", "")
    refresh_token = cached.get("refresh_token", "")
    expires_at = cached.get("expires_at", 0)

    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token in Gist. Call /init first")
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh_token in Gist")

    if time.time() >= expires_at - 300:
        print(f"[DEBUG] Token expires in {int(expires_at - time.time())}s, renewing...")
        token_data = renew_access_token(refresh_token, config)
        if token_data:
            return token_data["access_token"]
        else:
            raise HTTPException(status_code=500, detail="Failed to renew token")

    return access_token

def spotify_request(method, endpoint, access_token, config: dict = None, **kwargs):
    url = f"https://api.spotify.com/v1{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    
    if res.status_code == 401:
        print("[DEBUG] Got 401, retrying with fresh token...")
        cached = load_token_from_gist_for_user(config=config)
        token_data = renew_access_token(cached.get("refresh_token", ""), config)
        if token_data:
            headers["Authorization"] = f"Bearer {token_data['access_token']}"
            res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    
    return res

def handle_spotify_error(res):
    if res.status_code in [200, 204]:
        return
    print(f"[ERROR] Spotify API {res.status_code}: {res.text}")
    detail = "An error occurred with the music player service."
    if res.status_code == 403:
        detail = "Action forbidden."
    elif res.status_code == 404:
        detail = "Resource not found."
    elif res.status_code == 401:
        detail = "Authentication failed."
    raise HTTPException(status_code=res.status_code, detail=detail)

def parse_time(ms: int):
    minutes = int(ms / 60000)
    seconds = int((ms % 60000) / 1000)
    return f"{minutes:02}:{seconds:02}"

def parse_track_data(data: dict):
    if not data or not data.get("item"):
        return {"is_playing": False, "message": "No active playback"}

    item = data["item"]
    album = item.get("album", {})
    images = album.get("images", [])
    thumbnail = images[1]["url"] if len(images) > 1 else (images[0]["url"] if images else "")
    
    progress_ms = data.get("progress_ms", 0)
    duration_ms = item.get("duration_ms", 0)
    progress_percent = (progress_ms / duration_ms * 100) if duration_ms else 0

    return {
        "is_playing": data.get("is_playing", False),
        "track": item.get("name", ""),
        "artist": ", ".join(a["name"] for a in item.get("artists", [])),
        "album": album.get("name", ""),
        "thumbnail": thumbnail,
        "duration_ms": duration_ms,
        "progress_ms": progress_ms,
        "progress_percent": round(progress_percent, 2),
        "progress": f"{parse_time(progress_ms)} / {parse_time(duration_ms)}",
        "device": data.get("device", {}).get("name", ""),
        "volume_percent": data.get("device", {}).get("volume_percent"),
        "shuffle_state": data.get("shuffle_state", False),
        "repeat_state": data.get("repeat_state", "off"),
        "track_id": item.get("id"),
    }

# ======================= Auth Routes =======================
@app.get("/")
def serve_root(session_token: str = Cookie(None, alias="session_token")):
    """Root route - redirect based on auth state"""
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse("/welcome")
    
    # Check if user has config
    config = get_user_config(user["id"])
    if not config or not config.get("client_id"):
        return RedirectResponse("/setup")
    
    # If config not validated yet, go to setup
    if not config.get("validated"):
        return RedirectResponse("/setup")
    
    # Check if has valid tokens
    try:
        cached = load_token_from_gist_for_user(config=config)
        if not cached.get("access_token") or not cached.get("refresh_token"):
            return RedirectResponse("/spotify/login")
    except Exception:
        return RedirectResponse("/spotify/login")
    
    return FileResponse("index.html")

@app.get("/welcome")
def serve_welcome():
    return FileResponse("welcome.html")

@app.get("/auth/register")
def serve_register():
    return FileResponse("register.html")

@app.get("/auth/login")
def serve_login():
    return FileResponse("login.html")

@app.get("/setup")
def serve_setup(session_token: str = Cookie(None, alias="session_token")):
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse("/auth/login")
    return FileResponse("setup.html")

@app.get("/player")
def serve_player(session_token: str = Cookie(None, alias="session_token")):
    """Serve player - requires auth and setup"""
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse("/auth/login")
    
    config = get_user_config(user["id"])
    if not config or not config.get("client_id"):
        return RedirectResponse("/setup")
    
    return FileResponse("index.html")

@app.post("/api/auth/register")
async def api_register(request: RegisterRequest, response: Response):
    result = auth_module.register_user(request.username, request.password)
    
    if result.get("error"):
        return JSONResponse({"success": False, "error": result["error"]}, status_code=400)
    
    return {"success": True, "message": "Đăng ký thành công!"}

@app.post("/api/auth/login")
async def api_login(request: LoginRequest, response: Response):
    result = auth_module.login_user(request.username, request.password)
    
    if result.get("error"):
        return JSONResponse({"success": False, "error": result["error"]}, status_code=401)
    
    # Set session cookie
    resp = JSONResponse({
        "success": True,
        "user": {"id": result["user_id"], "username": result["username"]}
    })
    resp.set_cookie(
        key="session_token",
        value=result["session_token"],
        httponly=True,
        max_age=30 * 24 * 60 * 60,  # 30 days
        samesite="lax"
    )
    return resp

@app.post("/api/auth/logout")
async def api_logout(response: Response, session_token: str = Cookie(None, alias="session_token")):
    if session_token:
        auth_module.logout_user(session_token)
    
    resp = JSONResponse({"success": True})
    resp.delete_cookie("session_token")
    return resp

@app.get("/api/auth/me")
async def api_me(session_token: str = Cookie(None, alias="session_token")):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": user["id"], "username": user["username"]}

@app.get("/api/config")
async def api_get_config(session_token: str = Cookie(None, alias="session_token")):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    config = get_user_config(user["id"])
    if not config:
        return {}
    
    # Don't return full secrets, just indicators
    return {
        "client_id": config.get("client_id", ""),
        "client_secret": "••••••••" if config.get("client_secret") else "",
        "gist_id": config.get("gist_id", ""),
        "github_token": "••••••••" if config.get("github_token") else "",
        "gist_filename": config.get("gist_filename", "spotify_tokens.json"),
        "redirect_uri": config.get("redirect_uri", "")
    }

@app.post("/api/config")
async def api_save_config(config: ConfigRequest, session_token: str = Cookie(None, alias="session_token")):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate required fields
    if not config.client_id or not config.client_secret:
        return JSONResponse({"success": False, "error": "Client ID và Client Secret là bắt buộc"}, status_code=400)
    
    if not config.gist_id or not config.github_token:
        return JSONResponse({"success": False, "error": "Gist ID và GitHub Token là bắt buộc"}, status_code=400)
    
    # Test Gist access
    try:
        test_url = f"https://api.github.com/gists/{config.gist_id}"
        test_res = requests.get(test_url, headers={"Authorization": f"token {config.github_token}"}, timeout=10)
        if test_res.status_code != 200:
            return JSONResponse({"success": False, "error": "Không thể truy cập Gist. Kiểm tra Gist ID và GitHub Token."}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": f"Lỗi kết nối GitHub: {str(e)}"}, status_code=400)
    
    # Save config
    database.update_user_config(
        user_id=user["id"],
        client_id=config.client_id,
        client_secret=config.client_secret,
        gist_id=config.gist_id,
        github_token=config.github_token,
        gist_filename=config.gist_filename or "spotify_tokens.json",
        redirect_uri=config.redirect_uri or f"http://127.0.0.1:8000/api/spotify/callback"
    )
    
    return {"success": True}

@app.post("/api/generate-api-key")
async def api_generate_key(session_token: str = Cookie(None, alias="session_token")):
    """Generate a new API key for the user"""
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    new_key = secrets.token_urlsafe(32)
    database.update_user_config(user["id"], app_api_key=new_key)
    return {"success": True, "api_key": new_key}

@app.get("/api/my-api-key")
async def api_get_my_key(session_token: str = Cookie(None, alias="session_token")):
    """Get current user's API key"""
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    config = get_user_config(user["id"])
    return {"api_key": config.get("app_api_key", "") if config else ""}

# ======================= Static Files =======================
@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

@app.get("/script.js")
def serve_js():
    return FileResponse("script.js")

# ======================= Spotify OAuth =======================
@app.get("/spotify/login")
def spotify_login(session_token: str = Cookie(None, alias="session_token")):
    """Initiate Spotify OAuth - requires user to be logged in"""
    user = get_current_user(session_token)
    if not user:
        return RedirectResponse("/auth/login")
    
    config = get_user_config(user["id"])
    if not config or not config.get("client_id"):
        return RedirectResponse("/setup")
    
    client_id = config["client_id"]
    redirect_uri = config.get("redirect_uri") or (f"https://100.53.0.184.nip.io/api/spotify/callback" if ENVIRONMENT == "production" else f"http://127.0.0.1:8000/api/spotify/callback")
    
    state = secrets.token_urlsafe(32)
    oauth_pending_states[state] = {"time": time.time(), "user_id": user["id"]}
    
    # Clean up old states
    current_time = time.time()
    expired_states = [s for s, data in oauth_pending_states.items() if current_time - data.get("time", 0) > 600]
    for s in expired_states:
        del oauth_pending_states[s]
    
    scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing user-library-read user-library-modify"
    auth_url = (
        f"https://accounts.spotify.com/authorize?response_type=code"
        f"&client_id={client_id}"
        f"&scope={quote(scopes)}"
        f"&redirect_uri={quote(redirect_uri)}"
        f"&state={state}"
    )
    return RedirectResponse(auth_url)

@app.get("/api/spotify/callback")
def spotify_callback(code: str, state: str = None, session_token: str = Cookie(None, alias="session_token")):
    """Handle Spotify OAuth callback"""
    if not state or state not in oauth_pending_states:
        raise HTTPException(status_code=400, detail="Invalid or missing state parameter")
    
    state_data = oauth_pending_states.get(state, {})
    if time.time() - state_data.get("time", 0) > 300:
        del oauth_pending_states[state]
        raise HTTPException(status_code=400, detail="Authentication session expired. Please try again.")
    
    user_id = state_data.get("user_id")
    del oauth_pending_states[state]
    
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid session")
    
    config = get_user_config(user_id)
    if not config:
        raise HTTPException(status_code=400, detail="User config not found")
    
    client_id = config["client_id"]
    client_secret = config["client_secret"]
    redirect_uri = config.get("redirect_uri") or (f"https://100.53.0.184.nip.io/api/spotify/callback" if ENVIRONMENT == "production" else f"http://127.0.0.1:8000/api/spotify/callback")
    
    url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    res = requests.post(url, headers=headers, data=data, timeout=10)
    
    if res.status_code == 200:
        token_data = res.json()
        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = time.time() + token_data.get("expires_in", 3600)
        
        success = save_token_to_gist(access_token, refresh_token, expires_at, config)
        
        if success:
            # Mark config as validated
            database.update_user_config(user_id, validated=1)
            return HTMLResponse("""
                <html>
                    <body style='background:#0a0a0a; color:#fff; font-family:Poppins,sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh;'>
                        <div style='text-align:center;'>
                            <svg width='64' height='64' viewBox='0 0 24 24' fill='#1ed760'><path d='M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z'/></svg>
                            <h2 style='color:#1ed760; margin:24px 0 8px;'>Kết nối thành công!</h2>
                            <p style='color:#a7a7a7; margin-bottom:24px;'>Tokens đã được lưu vào Gist của bạn.</p>
                            <a href='/' style='display:inline-block; background:#1ed760; color:#000; padding:14px 32px; border-radius:50px; text-decoration:none; font-weight:600;'>Bắt đầu nghe nhạc</a>
                        </div>
                    </body>
                </html>
            """)
        else:
            return HTMLResponse("""
                <html>
                    <body style='background:#0a0a0a; color:#fff; font-family:Poppins,sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh;'>
                        <h2 style='color:#f44336;'>Lỗi lưu tokens</h2>
                        <p style='color:#a7a7a7;'>Không thể lưu tokens vào Gist. Kiểm tra cấu hình GitHub.</p>
                        <a href='/setup' style='color:#1ed760;'>Quay lại cài đặt</a>
                    </body>
                </html>
            """, status_code=500)
    else:
        error_text = res.text[:200] if res.text else ""
        print(f"[ERROR] OAuth token exchange failed: {res.status_code} - {error_text}")
        
        # Mark config as not validated
        database.update_user_config(user_id, validated=0)
        
        # Determine error type for user-friendly message
        error_param = "oauth_failed"
        if "invalid_client" in error_text.lower() or res.status_code == 401:
            error_param = "invalid_client"
        elif "invalid_grant" in error_text.lower():
            error_param = "invalid_grant"
        
        return RedirectResponse(f"/setup?error={error_param}")

# ======================= Spotify API Endpoints =======================
def get_user_config_from_session(session_token: str) -> dict:
    """Helper to get user config from session"""
    user = get_current_user(session_token)
    if not user:
        return None
    return get_user_config(user["id"])

@app.get("/current")
@limiter.limit("120/minute")
def current(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("GET", "/me/player", access_token, config)

    if res.status_code == 200:
        data = res.json()
        parsed = parse_track_data(data)
        track_id = parsed.get("track_id")
        if track_id:
            like_res = spotify_request("GET", f"/me/tracks/contains?ids={track_id}", access_token, config)
            if like_res.status_code == 200:
                parsed["is_liked"] = like_res.json()[0]
            else:
                parsed["is_liked"] = None
        return parsed
    elif res.status_code == 204:
        return {"is_playing": False, "message": "Nothing playing"}
    else:
        handle_spotify_error(res)

@app.get("/play")
@limiter.limit("60/minute")
def play(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("PUT", "/me/player/play", access_token, config)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "play"}
    handle_spotify_error(res)

@app.get("/pause")
@limiter.limit("60/minute")
def pause(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("PUT", "/me/player/pause", access_token, config)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "pause"}
    handle_spotify_error(res)

@app.get("/next")
@limiter.limit("60/minute")
def next_track(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("POST", "/me/player/next", access_token, config)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "next"}
    handle_spotify_error(res)

@app.get("/prev")
@limiter.limit("60/minute")
def prev_track(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("POST", "/me/player/previous", access_token, config)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "previous"}
    handle_spotify_error(res)

@app.get("/like")
@limiter.limit("20/minute")
def like_track(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    current = spotify_request("GET", "/me/player", access_token, config)
    if current.status_code == 200:
        data = current.json()
        track_id = data.get("item", {}).get("id")
        if track_id:
            res = spotify_request("PUT", f"/me/tracks?ids={track_id}", access_token, config)
            if res.status_code in [200, 204]:
                return {"success": True, "action": "liked", "track_id": track_id}
            handle_spotify_error(res)
    
    raise HTTPException(status_code=400, detail="No track playing")

@app.get("/dislike")
@limiter.limit("20/minute")
def dislike_track(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    current = spotify_request("GET", "/me/player", access_token, config)
    if current.status_code == 200:
        data = current.json()
        track_id = data.get("item", {}).get("id")
        if track_id:
            res = spotify_request("DELETE", f"/me/tracks?ids={track_id}", access_token, config)
            if res.status_code in [200, 204]:
                return {"success": True, "action": "disliked", "track_id": track_id}
            handle_spotify_error(res)
    
    raise HTTPException(status_code=400, detail="No track playing")

@app.get("/queue")
@limiter.limit("60/minute")
def get_queue(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("GET", "/me/player/queue", access_token, config)

    if res.status_code != 200:
        handle_spotify_error(res)

    data = res.json()
    queue_items = data.get("queue", [])

    queue_list = []
    for i, item in enumerate(queue_items[:20]):
        album = item.get("album", {})
        images = album.get("images", [])
        thumbnail = images[1]["url"] if len(images) > 1 else (images[0]["url"] if images else "")
        artists = ", ".join(a["name"] for a in item.get("artists", []))

        queue_list.append({
            "index": i + 1,
            "track": item.get("name", ""),
            "artist": artists,
            "album": album.get("name", ""),
            "thumbnail": thumbnail,
            "id": item.get("id", "")
        })

    current = data.get("currently_playing")
    current_info = None
    if current:
        c_album = current.get("album", {})
        c_images = c_album.get("images", [])
        c_thumb = c_images[1]["url"] if len(c_images) > 1 else (c_images[0]["url"] if c_images else "")
        current_info = {
            "track": current.get("name", ""),
            "artist": ", ".join(a["name"] for a in current.get("artists", [])),
            "album": c_album.get("name", ""),
            "thumbnail": c_thumb,
            "id": current.get("id", "")
        }

    return {
        "success": True,
        "currently_playing": current_info,
        "up_next": queue_list,
        "total": len(queue_list)
    }

@app.get("/shuffle/{state}")
@limiter.limit("20/minute")
def toggle_shuffle(state: str, request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    
    if state.lower() not in ["true", "false"]:
        raise HTTPException(status_code=400, detail="State must be 'true' or 'false'")
    
    res = spotify_request("PUT", f"/me/player/shuffle?state={state.lower()}", access_token, config)
    
    if res.status_code in [204, 200]:
        return {
            "success": True,
            "shuffle_state": state.lower() == "true"
        }
    else:
        handle_spotify_error(res)

@app.get("/queue/{index}")
@limiter.limit("20/minute")
def play_from_queue(index: int, request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    player_res = spotify_request("GET", "/me/player", access_token, config)
    if player_res.status_code != 200:
        raise HTTPException(status_code=player_res.status_code, detail="Cannot get player info")
    
    player_data = player_res.json()
    context = player_data.get("context") or {}
    context_uri = context.get("uri")

    queue_res = spotify_request("GET", "/me/player/queue", access_token, config)
    if queue_res.status_code != 200:
        raise HTTPException(status_code=queue_res.status_code, detail="Failed to get queue")

    queue_data = queue_res.json()
    queue_list = queue_data.get("queue", [])
    current = queue_data.get("currently_playing", {})
    full_list = [current] + queue_list

    if index < 0 or index >= len(full_list):
        raise HTTPException(status_code=400, detail=f"Index {index} out of range")

    target_track = full_list[index]
    track_id = target_track.get("id")

    if context_uri:
        body = {"context_uri": context_uri, "offset": {"uri": f"spotify:track:{track_id}"}}
    else:
        body = {"uris": [f"spotify:track:{track_id}"]}

    res = spotify_request("PUT", "/me/player/play", access_token, config, json=body)

    if res.status_code in [204, 200]:
        return {
            "success": True,
            "message": f"Now playing {target_track.get('name')} by {', '.join(a['name'] for a in target_track.get('artists', []))}",
            "track_id": track_id,
            "used_context": bool(context_uri)
        }
    else:
        handle_spotify_error(res)

@app.get("/seek/{percent}")
@limiter.limit("60/minute")
def seek_position(percent: int, request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    if not (0 <= percent <= 100):
        raise HTTPException(status_code=400, detail="Percent must be between 0 and 100")

    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    current_res = spotify_request("GET", "/me/player", access_token, config)
    if current_res.status_code != 200:
        handle_spotify_error(current_res)
    
    current_data = current_res.json()
    duration_ms = current_data.get("item", {}).get("duration_ms", 0)
    
    if duration_ms == 0:
        raise HTTPException(status_code=400, detail="Cannot determine track duration")
    
    position_ms = int((percent / 100) * duration_ms)
    res = spotify_request("PUT", f"/me/player/seek?position_ms={position_ms}", access_token, config)
    
    if res.status_code in [204, 200]:
        return {
            "success": True,
            "position_ms": position_ms,
            "percent": percent
        }
    else:
        handle_spotify_error(res)

@app.get("/volume/{level}")
@limiter.limit("20/minute")
def set_volume(level: int, request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    if not (0 <= level <= 100):
        raise HTTPException(status_code=400, detail="Volume must be between 0 and 100")

    config = get_user_config_from_session(session_token)
    access_token = get_valid_token(config)
    res = spotify_request("PUT", f"/me/player/volume?volume_percent={level}", access_token, config)

    if res.status_code in [204, 200]:
        return {
            "success": True,
            "volume_percent": level
        }
    else:
        handle_spotify_error(res)

@app.get("/force-renew")
@limiter.limit("5/minute")
def force_renew(request: Request, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    config = get_user_config_from_session(session_token)
    cached = load_token_from_gist_for_user(config=config)
    refresh_token = cached.get("refresh_token", "")
    if not refresh_token:
        return {"error": "No refresh_token found in Gist"}

    token_data = renew_access_token(refresh_token, config)
    return (
        {"success": True, "message": "Token renewed", "expires_in": token_data.get("expires_in", 3600)}
        if token_data
        else {"success": False, "message": "Failed to renew token"}
    )

@app.get("/debug")
def debug(auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    if ENVIRONMENT != "development":
        raise HTTPException(status_code=404, detail="Not found")
    
    config = get_user_config_from_session(session_token)
    cached = load_token_from_gist_for_user(config=config)
    expires_at = cached.get("expires_at", 0)
    expires_in = int(expires_at - time.time())
    
    return {
        "access_token_preview": "********" if cached.get("access_token") else None,
        "has_refresh_token": bool(cached.get("refresh_token")),
        "expires_in_seconds": expires_in,
        "is_expired": expires_in <= 0,
    }

@app.get("/gettoken")
def get_token(auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    if ENVIRONMENT != "development":
        raise HTTPException(status_code=404, detail="Not found")
    
    try:
        config = get_user_config_from_session(session_token)
        access_token = get_valid_token(config)
        return {"success": True, "access_token": access_token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/init")
async def init_tokens(request: dict, auth: str = Depends(verify_api_key), session_token: str = Cookie(None, alias="session_token")):
    access_token = request.get("access_token", "")
    refresh_token = request.get("refresh_token", "")
    
    if not access_token or not refresh_token:
        return {"error": "Both access_token and refresh_token required"}

    config = get_user_config_from_session(session_token)
    expires_at = time.time() + 3600
    success = save_token_to_gist(access_token, refresh_token, expires_at, config)
    
    return (
        {"success": True, "message": "Tokens saved to Gist", "expires_in": 3600}
        if success
        else {"success": False, "message": "Failed to save to Gist"}
    )

# Legacy login route - redirect to new flow
@app.get("/login")
def login():
    return RedirectResponse("/welcome")

app = app