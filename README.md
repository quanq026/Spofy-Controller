# Spotify Controller

**A powerful Spotify Web API wrapper with automatic token management and essential playback control endpoints.**

Spotify Controller provides a lightweight FastAPI server that simplifies Spotify Web API integration. It handles OAuth authentication, automatic token refresh via GitHub Gist storage, and exposes clean REST endpoints for controlling playback—play, pause, skip, shuffle, like tracks, manage queue, and seek. Includes a bonus responsive web frontend for easy interaction.

## Preview

![Spotify Controller Preview](https://github.com/quanq026/Spo/blob/main/image.png?raw=true)

## Features

### Spotify API Control
- **Playback Management** - Play, pause, next, previous track control
- **Queue Management** - Fetch queue list and skip to any track in queue
- **Shuffle & Repeat** - Toggle shuffle mode and control repeat state
- **Track Management** - Like/unlike tracks (add to/remove from library)
- **Seek Control** - Seek to any position in current track
- **Volume Control** - Adjust playback volume
- **Token Management** - Automatic OAuth token refresh and secure storage

### Frontend UI (Bonus)
- Clean, responsive web interface with dark theme
- Real-time playback status updates (1s polling)
- Queue preview with album thumbnails
- Toast notifications for user feedback
- Mobile-friendly responsive design

## Requirements

### Backend (Core)
- Python 3.8+
- FastAPI
- Requests library
- Uvicorn

### Frontend (Optional)
- Modern web browser (Chrome, Firefox, Safari, Edge)
- JavaScript enabled

## Installation

### 1. Clone or set up the project
```bash
git clone <repository-url>
cd Spo
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
Create a `.env` file in the root directory with:

```env
# Spotify Credentials
CLIENT_ID=your_spotify_client_id
CLIENT_SECRET=your_spotify_client_secret

# GitHub Gist Configuration (for token storage)
GITHUB_GIST_ID=your_gist_id
GITHUB_TOKEN=your_github_token
GIST_FILENAME=tokens.json

# API Security (optional)
APP_API_KEY=your_api_key
```

#### How to get Spotify credentials:
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Accept terms and create
4. Copy `Client ID` and `Client Secret`

#### How to set up GitHub Gist for token storage:
1. Create a GitHub Gist (can be private)
2. Get the Gist ID from the URL: `https://gist.github.com/username/{GIST_ID}`
3. Create a GitHub Personal Access Token with `gist` scope
4. Create initial `tokens.json` file in your Gist

### 4. Run the server
```bash
uvicorn index:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access the application
- Open `http://localhost:8000` in your browser

## Project Structure

```
.
├── index.html          # Main UI template
├── index.py           # FastAPI backend server
├── script.js          # Frontend JavaScript logic
├── style.css          # Frontend styling
├── vercel.json        # Vercel deployment config
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## API Endpoints

### Playback Control
- `GET /current` - Get current playback state and track info
- `GET /play` - Resume playback
- `GET /pause` - Pause playback
- `GET /next` - Skip to next track
- `GET /prev` - Skip to previous track

### Queue Management
- `GET /queue` - Get queue list and upcoming tracks
- `GET /queue/{index}` - Play track at queue index

### Track Management
- `GET /like` - Add current track to library
- `GET /dislike` - Remove current track from library

### Controls
- `GET /shuffle/{state}` - Toggle shuffle mode (true/false)
- `GET /seek/{percent}` - Seek to position (0-100%)
- `GET /volume/{level}` - Set volume level (0-100)

### Utilities
- `GET /gettoken` - Get current valid access token
- `GET /debug` - Check token status and expiration
- `GET /force-renew` - Manually renew access token
- `POST /init` - Initialize tokens (requires access_token and refresh_token)

## Security Features

- **Environment Variables** - All credentials stored in `.env` (not in code)
- **API Key Protection** - Optional header-based API key authentication
- **Token Storage** - Spotify tokens stored in private GitHub Gist
- **Auto Token Renewal** - Tokens automatically refresh before expiration
- **CORS Protection** - Restricted to specified origins
- **Sanitized Error Messages** - No sensitive data in error responses

## Deployment

### Deploy to Vercel
1. Install Vercel CLI: `npm i -g vercel`
2. Set environment variables in Vercel dashboard
3. Deploy: `vercel`

The `vercel.json` config is already set up for FastAPI deployment.

## Usage

### API-First Approach
Use the FastAPI endpoints directly in your applications:

```bash
# Get current playback state
curl http://localhost:8000/current

# Control playback
curl http://localhost:8000/play
curl http://localhost:8000/pause
curl http://localhost:8000/next

# Manage queue
curl http://localhost:8000/queue
curl http://localhost:8000/queue/1

# Advanced controls
curl http://localhost:8000/shuffle/true
curl http://localhost:8000/seek/50
curl http://localhost:8000/like
```

### Web UI (Optional)
1. Visit `http://localhost:8000` in your browser
2. App automatically connects to your Spotify playback
3. Use the interface to control playback visually

See [API Endpoints](#api-endpoints) for complete documentation.

## Troubleshooting

### "No active playback" message
- Make sure Spotify is playing on one of your devices
- Restart the app and try again

### "Authentication failed"
- Check your CLIENT_ID and CLIENT_SECRET
- Verify Spotify API credentials in Developer Dashboard
- Check token expiration in `/debug` endpoint

### "Failed to save to Gist"
- Verify GITHUB_GIST_ID and GITHUB_TOKEN are correct
- Ensure the gist exists and is accessible
- Check that tokens.json file exists in the gist

### Queue not updating
- Queue updates when track changes or on polling intervals
- Try refreshing the page

## Development

### Backend (Primary)
- **FastAPI** - High-performance async web framework
- **Spotify Web API Integration** - Direct API calls for playback control
- **Automatic Token Renewal** - Checks token expiration and auto-refreshes
- **GitHub Gist Storage** - Secure token persistence without database
- **CORS & Security** - Origin-based access control, sanitized error responses

### Frontend (Bonus UI)
- **Vanilla JavaScript** - No framework dependencies, lightweight
- **CSS Variables** - Dynamic theming with dark Spotify-inspired design
- **Responsive CSS** - Mobile and desktop layouts
- **Real-time Polling** - 1-second interval updates to track playback state
- **Toast Notifications** - User feedback system for actions

## License

MIT

## Support

For issues or questions, please check:
- [Spotify Web API Documentation](https://developer.spotify.com/documentation/web-api)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| CLIENT_ID | Yes | Spotify app Client ID |
| CLIENT_SECRET | Yes | Spotify app Client Secret |
| GITHUB_GIST_ID | Yes | GitHub Gist ID for token storage |
| GITHUB_TOKEN | Yes | GitHub Personal Access Token |
| GIST_FILENAME | Yes | Filename in gist (e.g., tokens.json) |
| APP_API_KEY | No | Optional API key for endpoint protection |
