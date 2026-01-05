from fastapi import FastAPI, HTTPException, Header, Security, Depends, Request
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
# CONFIGURATION HELPERS
# ======================
def get_settings(request: Request = None):
    """
    Retrieves configuration from Cookies (first priority) or Environment Variables (fallback).
    """
    cookies = request.cookies if request else {}
    
    return {
        "CLIENT_ID": cookies.get("CLIENT_ID") or os.getenv("CLIENT_ID", ""),
        "CLIENT_SECRET": cookies.get("CLIENT_SECRET") or os.getenv("CLIENT_SECRET", ""),
        "GITHUB_GIST_ID": cookies.get("GITHUB_GIST_ID") or os.getenv("GITHUB_GIST_ID", ""),
        "GITHUB_TOKEN": cookies.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN", ""),
        "GIST_FILENAME": cookies.get("GIST_FILENAME") or os.getenv("GIST_FILENAME", ""),
        "APP_API_KEY": cookies.get("APP_API_KEY") or os.getenv("APP_API_KEY", ""),
        "REDIRECT_URI": cookies.get("SPOTIFY_REDIRECT_URI") or os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/spotify/callback")
    }

# ======================
# SECURITY
# ======================
async def verify_api_key(request: Request, x_api_key: str = Header(None)):
    """Verifies the API Key from the X-API-Key header against the dynamic settings."""
    settings = get_settings(request)
    api_key = settings["APP_API_KEY"]
    
    if not api_key:
        return

    if x_api_key and x_api_key == api_key:
        return

    raise HTTPException(status_code=401, detail="Missing or Invalid API Key")

# ======================
# GIST STORAGE
# ======================


def load_token_from_gist(settings: dict) -> dict:
    """Loads tokens from GitHub Gist using dynamic settings."""
    gist_id = settings["GITHUB_GIST_ID"]
    token = settings["GITHUB_TOKEN"]
    filename = settings["GIST_FILENAME"]

    if not gist_id or not token:
        return {"access_token": "", "refresh_token": "", "expires_at": 0}

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {token}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            content = data["files"][filename]["content"]
            return json.loads(content)
    except Exception as e:
        print(f"[ERROR] Load Gist failed: {e}")
    return {"access_token": "", "refresh_token": "", "expires_at": 0}

def save_token_to_gist(settings: dict, access_token: str, refresh_token: str, expires_at: float):
    """Saves tokens to GitHub Gist using dynamic settings."""
    gist_id = settings["GITHUB_GIST_ID"]
    token = settings["GITHUB_TOKEN"]
    filename = settings["GIST_FILENAME"]

    if not gist_id or not token:
        print("[WARN] Gist not configured")
        return False

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "files": {
            filename: {
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
def renew_access_token(settings: dict, refresh_token: str):
    """Renews the access token using the refresh token and dynamic settings."""
    url = "https://accounts.spotify.com/api/token"
    client_id = settings["CLIENT_ID"]
    client_secret = settings["CLIENT_SECRET"]
    
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
        save_token_to_gist(settings, access_token, new_refresh_token, expires_at)
        return token_data
    else:
        print(f"[ERROR] Renew failed: {res.text[:200]}")
        return None

def get_valid_token(settings: dict) -> str:
    """Retrieves a valid access token, renewing it if necessary."""
    cached = load_token_from_gist(settings)
    access_token = cached.get("access_token", "")
    refresh_token = cached.get("refresh_token", "")
    expires_at = cached.get("expires_at", 0)

    if not access_token:
        # Don't error out immediately, maybe they need to login.
        # But for this function's contract, it expects a token.
        raise HTTPException(status_code=400, detail="No access_token in Gist. Call /init first or check settings")
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh_token in Gist")

    # Renew if expired or expiring soon (< 5 minutes)
    if time.time() >= expires_at - 300:
        print(f"[DEBUG] Token expires in {int(expires_at - time.time())}s, renewing...")
        token_data = renew_access_token(settings, refresh_token)
        if token_data:
            return token_data["access_token"]
        else:
            raise HTTPException(status_code=500, detail="Failed to renew token")

    return access_token

# ======================
# SPOTIFY API HELPERS
# ======================
def spotify_request(method, endpoint, access_token, settings: dict, **kwargs):
    """Helper to send Spotify requests with retry logic."""
    url = f"https://api.spotify.com/v1{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    
    # Retry if token is expired (401 Unauthorized)
    if res.status_code == 401:
        print("[DEBUG] Got 401, retrying with fresh token...")
        cached = load_token_from_gist(settings)
        token_data = renew_access_token(settings, cached.get("refresh_token", ""))
        if token_data:
            headers["Authorization"] = f"Bearer {token_data['access_token']}"
            res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    
    return res

def handle_spotify_error(res):
    """Logs detailed errors and raises sanitized HTTP exceptions."""
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
    """Formats milliseconds to mm:ss."""
    minutes = int(ms / 60000)
    seconds = int((ms % 60000) / 1000)
    return f"{minutes:02}:{seconds:02}"

def parse_track_data(data: dict):
    """Parses raw playback data into a simplified JSON response."""
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
# API ROUTES
# ======================
# ======================
# STATIC ASSETS (UI)
# ======================

@app.get("/")
def serve_ui(settings: dict = Depends(get_settings)):
    # Check if we have valid tokens in Gist
    try:
        cached = load_token_from_gist(settings)
        # If Gist is empty, malformed, or missing critical keys -> Redirect to Login
        # Only redirect if we have configured gist settings but no token. 
        # If we have NO settings, we should serve UI so they can enter settings.
        if settings["GITHUB_GIST_ID"] and settings["GITHUB_TOKEN"]:
             if not cached or not cached.get("access_token") or not cached.get("refresh_token"):
                 return RedirectResponse("/login")
    except Exception:
        # If unreadable -> Redirect to Login
        return RedirectResponse("/login")

    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css")

@app.get("/script.js")
def serve_js():
    return FileResponse("script.js")

@app.get("/current")
def current(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Retrieves the current playback state and 'liked' status."""
    access_token = get_valid_token(settings)
    res = spotify_request("GET", "/me/player", access_token, settings)

    if res.status_code == 200:
        data = res.json()
        parsed = parse_track_data(data)

        # Check if the current track is in the user's "Liked Songs"
        track_id = parsed.get("track_id")
        if track_id:
            like_res = spotify_request("GET", f"/me/tracks/contains?ids={track_id}", access_token, settings)
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
def play(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Resumes playback."""
    access_token = get_valid_token(settings)
    res = spotify_request("PUT", "/me/player/play", access_token, settings)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "play"}
    handle_spotify_error(res)

@app.get("/pause")
def pause(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Pauses playback."""
    access_token = get_valid_token(settings)
    res = spotify_request("PUT", "/me/player/pause", access_token, settings)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "pause"}
    handle_spotify_error(res)

@app.get("/next")
def next_track(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Skips to the next track."""
    access_token = get_valid_token(settings)
    res = spotify_request("POST", "/me/player/next", access_token, settings)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "next"}
    handle_spotify_error(res)

@app.get("/prev")
def prev_track(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Skips to the previous track."""
    access_token = get_valid_token(settings)
    res = spotify_request("POST", "/me/player/previous", access_token, settings)
    
    if res.status_code in [204, 200]:
        return {"success": True, "action": "previous"}
    handle_spotify_error(res)

@app.get("/like")
def like_track(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Adds the current track to the user's library."""
    access_token = get_valid_token(settings)
    
    # Get current track
    current = spotify_request("GET", "/me/player", access_token, settings)
    if current.status_code == 200:
        data = current.json()
        track_id = data.get("item", {}).get("id")
        if track_id:
            res = spotify_request("PUT", f"/me/tracks?ids={track_id}", access_token, settings)
            if res.status_code in [200, 204]:
                return {"success": True, "action": "liked", "track_id": track_id}
            handle_spotify_error(res)
    
    raise HTTPException(status_code=400, detail="No track playing")

@app.get("/dislike")
def dislike_track(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Removes the current track from the user's library."""
    access_token = get_valid_token(settings)
    
    # Get current track
    current = spotify_request("GET", "/me/player", access_token, settings)
    if current.status_code == 200:
        data = current.json()
        track_id = data.get("item", {}).get("id")
        if track_id:
            res = spotify_request("DELETE", f"/me/tracks?ids={track_id}", access_token, settings)
            if res.status_code in [200, 204]:
                return {"success": True, "action": "disliked", "track_id": track_id}
            handle_spotify_error(res)
    
    raise HTTPException(status_code=400, detail="No track playing")

@app.get("/queue")
def get_queue(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Retrieves the current playback queue."""
    access_token = get_valid_token(settings)
    res = spotify_request("GET", "/me/player/queue", access_token, settings)

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
def toggle_shuffle(state: str, settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Toggles shuffle mode."""
    access_token = get_valid_token(settings)
    
    if state.lower() not in ["true", "false"]:
        raise HTTPException(status_code=400, detail="State must be 'true' or 'false'")
    
    res = spotify_request("PUT", f"/me/player/shuffle?state={state.lower()}", access_token, settings)
    
    if res.status_code in [204, 200]:
        return {
            "success": True,
            "shuffle_state": state.lower() == "true"
        }
    else:
        handle_spotify_error(res)

@app.get("/queue/{index}")
def play_from_queue(index: int, settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Plays a track from the queue within the current context."""
    access_token = get_valid_token(settings)
    player_res = spotify_request("GET", "/me/player", access_token, settings)
    if player_res.status_code != 200:
        raise HTTPException(status_code=player_res.status_code, detail="Cannot get player info")
    
    player_data = player_res.json()
    context_uri = player_data.get("context", {}).get("uri", None)

    queue_res = spotify_request("GET", "/me/player/queue", access_token, settings)
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

    # If context (playlist/album) exists, play within context
    if context_uri:
        body = {"context_uri": context_uri, "offset": {"uri": f"spotify:track:{track_id}"}}
    else:
    # Otherwise, play as a standalone track
        body = {"uris": [f"spotify:track:{track_id}"]}

    res = spotify_request("PUT", "/me/player/play", access_token, settings, json=body)

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
def seek_position(percent: int, settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Seeks to a specific position (percentage) in the track."""
    if not (0 <= percent <= 100):
        raise HTTPException(status_code=400, detail="Percent must be between 0 and 100")

    access_token = get_valid_token(settings)
    current_res = spotify_request("GET", "/me/player", access_token, settings)
    if current_res.status_code != 200:
        handle_spotify_error(current_res)
    
    current_data = current_res.json()
    duration_ms = current_data.get("item", {}).get("duration_ms", 0)
    
    if duration_ms == 0:
        raise HTTPException(status_code=400, detail="Cannot determine track duration")
    
    position_ms = int((percent / 100) * duration_ms)
    res = spotify_request("PUT", f"/me/player/seek?position_ms={position_ms}", access_token, settings)
    
    if res.status_code in [204, 200]:
        return {
            "success": True,
            "position_ms": position_ms,
            "percent": percent
        }
    else:
        handle_spotify_error(res)

@app.get("/volume/{level}")
def set_volume(level: int, settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Sets the playback volume (0-100)."""
    if not (0 <= level <= 100):
        raise HTTPException(status_code=400, detail="Volume must be between 0 and 100")

    access_token = get_valid_token(settings)
    res = spotify_request("PUT", f"/me/player/volume?volume_percent={level}", access_token, settings)

    if res.status_code in [204, 200]:
        return {
            "success": True,
            "volume_percent": level
        }
    else:
        handle_spotify_error(res)

@app.get("/force-renew")
def force_renew(settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Forces a token renewal."""
    cached = load_token_from_gist(settings)
    refresh_token = cached.get("refresh_token", "")
    if not refresh_token:
        return {"error": "No refresh_token found in Gist"}

    token_data = renew_access_token(settings, refresh_token)
    return (
        {"success": True, "message": "Token renewed", "expires_in": token_data.get("expires_in", 3600)}
        if token_data
        else {"success": False, "message": "Failed to renew token"}
    )

@app.get("/debug")
def debug(settings: dict = Depends(get_settings)):
    """Debugs the current token status."""
    cached = load_token_from_gist(settings)
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
def get_token(settings: dict = Depends(get_settings)):
    """Returns a valid access token."""
    try:
        access_token = get_valid_token(settings)
        return {
            "success": True,
            "access_token": access_token
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/init")
async def init_tokens(request: dict, settings: dict = Depends(get_settings), auth: str = Depends(verify_api_key)):
    """Initializes the Gist with provided tokens."""
    access_token = request.get("access_token", "")
    refresh_token = request.get("refresh_token", "")
    
    if not access_token or not refresh_token:
        return {"error": "Both access_token and refresh_token required"}

    expires_at = time.time() + 3600
    success = save_token_to_gist(settings, access_token, refresh_token, expires_at)
    
    return (
        {"success": True, "message": "Tokens saved to Gist", "expires_in": 3600}
        if success
        else {"success": False, "message": "Failed to save to Gist"}
    )

# ======================
# OAUTH FLOW
# ======================
@app.get("/login")
def login(settings: dict = Depends(get_settings)):
    """Redirects the user to Spotify for authentication."""
    client_id = settings["CLIENT_ID"]
    redirect_uri = settings["REDIRECT_URI"]

    if not client_id:
        return {"error": "CLIENT_ID not configured"}
        
    scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing user-library-read user-library-modify"
    auth_url = (
        f"https://accounts.spotify.com/authorize?response_type=code"
        f"&client_id={client_id}"
        f"&scope={quote(scopes)}"
        f"&redirect_uri={quote(redirect_uri)}"
    )
    return RedirectResponse(auth_url)

@app.get("/api/spotify/callback")
def callback(code: str, settings: dict = Depends(get_settings)):
    """Exchanges the authorization code for tokens and saves them to Gist."""
    client_id = settings["CLIENT_ID"]
    client_secret = settings["CLIENT_SECRET"]
    redirect_uri = settings["REDIRECT_URI"]

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
        
        success = save_token_to_gist(settings, access_token, refresh_token, expires_at)
        
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