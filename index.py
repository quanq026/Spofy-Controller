from fastapi import FastAPI, HTTPException, Header, Security, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from typing import Optional
from urllib.parse import quote
import requests
import os, json, time, base64

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

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
    allow_methods=["*"],
    allow_headers=["*"],
)
# ======================
# CONFIG
# ======================
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
GITHUB_GIST_ID = os.getenv("GITHUB_GIST_ID", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GIST_FILENAME = os.getenv("GIST_FILENAME", "")
APP_API_KEY = os.getenv("APP_API_KEY", "")
REDIRECT_URI = "https://spotifyesp32.vercel.app/api/spotify/callback"

# ======================
# SECURITY
# ======================
async def verify_api_key(x_api_key: str = Header(None)):
    """Validates the API Key via Header (X-API-Key)."""
    if not APP_API_KEY:
        return

    if x_api_key and x_api_key == APP_API_KEY:
        return

    raise HTTPException(status_code=401, detail="Missing or Invalid API Key")

# ======================
# GIST STORAGE
# ======================


def load_token_from_gist() -> dict:
    """Đọc token từ GitHub Gist"""
    if not GITHUB_GIST_ID or not GITHUB_TOKEN:
        return {"access_token": "", "refresh_token": "", "expires_at": 0}

    url = f"https://api.github.com/gists/{GITHUB_GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            content = data["files"][GIST_FILENAME]["content"]
            return json.loads(content)
    except Exception as e:
        print(f"[ERROR] Load Gist failed: {e}")
    return {"access_token": "", "refresh_token": "", "expires_at": 0}

def save_token_to_gist(access_token: str, refresh_token: str, expires_at: float):
    """Lưu token vào GitHub Gist"""
    if not GITHUB_GIST_ID or not GITHUB_TOKEN:
        print("[WARN] Gist not configured")
        return False

    url = f"https://api.github.com/gists/{GITHUB_GIST_ID}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "files": {
            GIST_FILENAME: {
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

# ======================
# TOKEN HANDLING
# ======================
def renew_access_token(refresh_token: str):
    """Làm mới access token"""
    url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
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
        save_token_to_gist(access_token, new_refresh_token, expires_at)
        return token_data
    else:
        print(f"[ERROR] Renew failed: {res.text[:200]}")
        return None

def get_valid_token() -> str:
    """Đọc token từ Gist, tự renew nếu gần hết hạn"""
    cached = load_token_from_gist()
    access_token = cached.get("access_token", "")
    refresh_token = cached.get("refresh_token", "")
    expires_at = cached.get("expires_at", 0)

    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token in Gist. Call /init first")
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh_token in Gist")

    # Renew if expired or near expiry (< 5 min)
    if time.time() >= expires_at - 300:
        print(f"[DEBUG] Token expires in {int(expires_at - time.time())}s, renewing...")
        token_data = renew_access_token(refresh_token)
        if token_data:
            return token_data["access_token"]
        else:
            raise HTTPException(status_code=500, detail="Failed to renew token")

    return access_token

# ======================
# SPOTIFY API HELPERS
# ======================
def spotify_request(method, endpoint, access_token, **kwargs):
    """Helper gửi request Spotify với retry logic"""
    url = f"https://api.spotify.com/v1{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    
    # Retry nếu 401 (token expired)
    if res.status_code == 401:
        print("[DEBUG] Got 401, retrying with fresh token...")
        cached = load_token_from_gist()
        token_data = renew_access_token(cached.get("refresh_token", ""))
        if token_data:
            headers["Authorization"] = f"Bearer {token_data['access_token']}"
            res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    
    return res

def handle_spotify_error(res):
    """Logs detailed error and raises sanitized HTTPException"""
    if res.status_code in [200, 204]:
        return
    
    # Log full details internally
    print(f"[ERROR] Spotify API {res.status_code}: {res.text}")
    
    # Return sanitized error to client
    detail = "An error occurred with the music player service."
    if res.status_code == 403:
        detail = "Action forbidden."
    elif res.status_code == 404:
        detail = "Resource not found."
    elif res.status_code == 401:
        detail = "Authentication failed."
        
    raise HTTPException(status_code=res.status_code, detail=detail)

def parse_time(ms: int):
    """Format ms -> mm:ss"""
    minutes = int(ms / 60000)
    seconds = int((ms % 60000) / 1000)
    return f"{minutes:02}:{seconds:02}"

def parse_track_data(data: dict):
    """Parse playback state thành JSON response"""
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

# ======================
# ROUTES
# ======================
# ======================
# STATIC SERVING (UI)
# ======================

@app.get("/")
def serve_ui():
    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

@app.get("/script.js")
def serve_js():
    return FileResponse("script.js")

@app.get("/current")
def current(auth: str = Depends(verify_api_key)):
    """Lấy trạng thái playback hiện tại, kèm thông tin liked"""
    access_token = get_valid_token()
    res = spotify_request("GET", "/me/player", access_token)

    if res.status_code == 200:
        data = res.json()
        parsed = parse_track_data(data)

        # Kiểm tra bài này có nằm trong "Liked Songs" không
        track_id = parsed.get("track_id")
        if track_id:
            like_res = spotify_request("GET", f"/me/tracks/contains?ids={track_id}", access_token)
            if like_res.status_code == 200:
                liked_status = like_res.json()[0]
                parsed["is_liked"] = liked_status
            else:
                parsed["is_liked"] = None

        return parsed

    elif res.status_code == 204:
        return {"is_playing": False, "message": "Nothing playing"}
    else:
        handle_spotify_error(res)

@app.get("/play")
def play(auth: str = Depends(verify_api_key)):
    """Resume playback"""
    access_token = get_valid_token()
    res = spotify_request("PUT", "/me/player/play", access_token)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "play"}
    handle_spotify_error(res)

@app.get("/pause")
def pause(auth: str = Depends(verify_api_key)):
    """Pause playback"""
    access_token = get_valid_token()
    res = spotify_request("PUT", "/me/player/pause", access_token)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "pause"}
    handle_spotify_error(res)

@app.get("/next")
def next_track(auth: str = Depends(verify_api_key)):
    """Skip to next track"""
    access_token = get_valid_token()
    res = spotify_request("POST", "/me/player/next", access_token)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "next"}
    handle_spotify_error(res)

@app.get("/prev")
def prev_track(auth: str = Depends(verify_api_key)):
    """Skip to previous track"""
    access_token = get_valid_token()
    res = spotify_request("POST", "/me/player/previous", access_token)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "previous"}
    handle_spotify_error(res)

@app.get("/like")
def like_track(auth: str = Depends(verify_api_key)):
    """Save current track to library"""
    access_token = get_valid_token()
    
    # Get current track
    current = spotify_request("GET", "/me/player", access_token)
    if current.status_code == 200:
        data = current.json()
        track_id = data.get("item", {}).get("id")
        if track_id:
            res = spotify_request("PUT", f"/me/tracks?ids={track_id}", access_token)
            if res.status_code in [200, 204]:
                return {"success": True, "action": "liked", "track_id": track_id}
            handle_spotify_error(res)
    
    raise HTTPException(status_code=400, detail="No track playing")

@app.get("/dislike")
def dislike_track(auth: str = Depends(verify_api_key)):
    """Remove current track from library"""
    access_token = get_valid_token()
    
    # Get current track
    current = spotify_request("GET", "/me/player", access_token)
    if current.status_code == 200:
        data = current.json()
        track_id = data.get("item", {}).get("id")
        if track_id:
            res = spotify_request("DELETE", f"/me/tracks?ids={track_id}", access_token)
            if res.status_code in [200, 204]:
                return {"success": True, "action": "disliked", "track_id": track_id}
            handle_spotify_error(res)
    
    raise HTTPException(status_code=400, detail="No track playing")

@app.get("/queue")
def get_queue(auth: str = Depends(verify_api_key)):
    """Lấy danh sách bài hát trong hàng chờ"""
    access_token = get_valid_token()
    res = spotify_request("GET", "/me/player/queue", access_token)

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
def toggle_shuffle(state: str, auth: str = Depends(verify_api_key)):
    """Bật hoặc tắt chế độ trộn bài"""
    access_token = get_valid_token()
    
    if state.lower() not in ["true", "false"]:
        raise HTTPException(status_code=400, detail="State must be 'true' or 'false'")
    
    res = spotify_request("PUT", f"/me/player/shuffle?state={state.lower()}", access_token)
    
    if res.status_code in [204, 200]:
        return {
            "success": True,
            "shuffle_state": state.lower() == "true"
        }
    else:
        handle_spotify_error(res)

@app.get("/queue/{index}")
def play_from_queue(index: int, auth: str = Depends(verify_api_key)):
    """Phát bài trong context hiện tại thay vì reset queue"""
    access_token = get_valid_token()
    player_res = spotify_request("GET", "/me/player", access_token)
    if player_res.status_code != 200:
        raise HTTPException(status_code=player_res.status_code, detail="Cannot get player info")
    
    player_data = player_res.json()
    context_uri = player_data.get("context", {}).get("uri", None)

    queue_res = spotify_request("GET", "/me/player/queue", access_token)
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

    # Nếu có context (playlist/album), phát theo context
    if context_uri:
        body = {"context_uri": context_uri, "offset": {"uri": f"spotify:track:{track_id}"}}
    else:
        # Nếu không có context
        body = {"uris": [f"spotify:track:{track_id}"]}

    res = spotify_request("PUT", "/me/player/play", access_token, json=body)

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
def seek_position(percent: int, auth: str = Depends(verify_api_key)):
    """Seek to a specific position in the track (0-100%)"""
    if not (0 <= percent <= 100):
        raise HTTPException(status_code=400, detail="Percent must be between 0 and 100")

    access_token = get_valid_token()
    current_res = spotify_request("GET", "/me/player", access_token)
    if current_res.status_code != 200:
        handle_spotify_error(current_res)
    
    current_data = current_res.json()
    duration_ms = current_data.get("item", {}).get("duration_ms", 0)
    
    if duration_ms == 0:
        raise HTTPException(status_code=400, detail="Cannot determine track duration")
    
    position_ms = int((percent / 100) * duration_ms)
    res = spotify_request("PUT", f"/me/player/seek?position_ms={position_ms}", access_token)
    
    if res.status_code in [204, 200]:
        return {
            "success": True,
            "position_ms": position_ms,
            "percent": percent
        }
    else:
        handle_spotify_error(res)

@app.get("/volume/{level}")
def set_volume(level: int, auth: str = Depends(verify_api_key)):
    """Điều chỉnh âm lượng (0–100%)"""
    if not (0 <= level <= 100):
        raise HTTPException(status_code=400, detail="Volume must be between 0 and 100")

    access_token = get_valid_token()
    res = spotify_request("PUT", f"/me/player/volume?volume_percent={level}", access_token)

    if res.status_code in [204, 200]:
        return {
            "success": True,
            "volume_percent": level
        }
    else:
        handle_spotify_error(res)

@app.get("/force-renew")
def force_renew(auth: str = Depends(verify_api_key)):
    """Force renew token"""
    cached = load_token_from_gist()
    refresh_token = cached.get("refresh_token", "")
    if not refresh_token:
        return {"error": "No refresh_token found in Gist"}

    token_data = renew_access_token(refresh_token)
    return (
        {"success": True, "message": "Token renewed", "expires_in": token_data.get("expires_in", 3600)}
        if token_data
        else {"success": False, "message": "Failed to renew token"}
    )

@app.get("/debug")
def debug():
    """Debug token status"""
    cached = load_token_from_gist()
    expires_at = cached.get("expires_at", 0)
    expires_in = int(expires_at - time.time())
    
    return {
        "access_token_preview": "********" if cached.get("access_token") else None,
        "has_refresh_token": bool(cached.get("refresh_token")),
        "expires_at": expires_at,
        "expires_in_seconds": expires_in,
        "is_expired": expires_in <= 0,
        "timestamp": time.time()
    }

@app.get("/gettoken")
def get_token():
    """Trả về access_token hợp lệ."""
    try:
        access_token = get_valid_token()
        return {
            "success": True,
            "access_token": access_token
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/init")
async def init_tokens(request: dict, auth: str = Depends(verify_api_key)):
    """Initialize Gist with tokens"""
    access_token = request.get("access_token", "")
    refresh_token = request.get("refresh_token", "")
    
    if not access_token or not refresh_token:
        return {"error": "Both access_token and refresh_token required"}

    expires_at = time.time() + 3600
    success = save_token_to_gist(access_token, refresh_token, expires_at)
    
    return (
        {"success": True, "message": "Tokens saved to Gist", "expires_in": 3600}
        if success
        else {"success": False, "message": "Failed to save to Gist"}
    )

# ======================
# OAUTH FLOW
# ======================
@app.get("/login")
def login():
    """Redirect user to Spotify for authentication"""
    if not CLIENT_ID:
        return {"error": "CLIENT_ID not configured"}
        
    scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing user-library-read user-library-modify"
    auth_url = (
        f"https://accounts.spotify.com/authorize?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&scope={quote(scopes)}"
        f"&redirect_uri={quote(REDIRECT_URI)}"
    )
    return RedirectResponse(auth_url)

@app.get("/callback")
def callback(code: str):
    """Exchange code for tokens and save to Gist"""
    url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    res = requests.post(url, headers=headers, data=data, timeout=10)
    
    if res.status_code == 200:
        token_data = res.json()
        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = time.time() + token_data.get("expires_in", 3600)
        
        success = save_token_to_gist(access_token, refresh_token, expires_at)
        
        if success:
             return HTMLResponse("""
                <html>
                    <body style='background:#121212; color:#fff; font-family:sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh;'>
                        <h2 style='color:#1ed760'>Setup Complete!</h2>
                        <p>Tokens have been saved to Gist.</p>
                        <a href='/' style='color:#fff; text-decoration:underline;'>Go to Player</a>
                    </body>
                </html>
            """)
        else:
            return {"error": "Failed to save tokens to Gist"}
    else:
        return {"error": "Failed to exchange code", "details": res.json()}

app = app