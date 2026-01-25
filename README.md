# Spotify Controller 2.0

Self-hosted Spotify remote control with multi-user authentication.

> **Requirement:** Spotify Premium account is required. The Spotify Web API only allows playback control for Premium users.

![Preview](https://github.com/quanq026/Spo/blob/main/image.png?raw=true)

## What's New in 2.0

- **Multi-user authentication** - Each user has their own account and session
- **Per-user configuration** - Separate Spotify credentials and Gist storage per user
- **API Key support** - Generate API keys for scripts, automation, IoT integration
- **Setup wizard** - Step-by-step configuration guide
- **Smart validation** - Automatically skip setup if already authenticated

## Requirements

- Python 3.8+
- Spotify Premium Account
- GitHub Account (for token storage)

## Installation

```bash
git clone https://github.com/quanq026/Spofy-Controller.git
cd Spofy-Controller
pip install -r requirements.txt
```

Create `.env` file:

```env
ENVIRONMENT=development
PRODUCTION_ORIGIN=https://your-domain.com
```

Run server:

```bash
uvicorn index:app --host 127.0.0.1 --port 8000 --reload
```

## Usage

1. Go to `http://127.0.0.1:8000`
2. Create account and login
3. Follow Setup Wizard to configure Spotify App and GitHub Gist
4. Connect Spotify - done

Next time you login, you'll go directly to the player.

### Spotify App Setup

At [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), add Redirect URIs:
- Local: `http://127.0.0.1:8000/api/spotify/callback`
- Production: `https://YOUR_DOMAIN/api/spotify/callback`

## API Reference

All endpoints require either:
- Session cookie (automatic when logged in via web)
- API Key via URL param: `?api_key=YOUR_KEY`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/current` | Get current track info |
| GET | `/queue` | Get queue list |
| POST | `/play` | Play/Resume |
| POST | `/pause` | Pause |
| POST | `/next` | Next track |
| POST | `/prev` | Previous track |
| POST | `/shuffle` | Toggle shuffle |
| POST | `/like` | Like/Unlike track |
| POST | `/seek?position_ms=` | Seek to position |

Example:

```bash
curl "http://127.0.0.1:8000/current?api_key=YOUR_API_KEY"
curl -X POST "http://127.0.0.1:8000/next?api_key=YOUR_API_KEY"
```

## Deploy to Vercel

1. Push to GitHub
2. Import to Vercel
3. Add environment variables: `ENVIRONMENT=production`, `PRODUCTION_ORIGIN=https://your-app.vercel.app`
4. Deploy

## Security

- Session tokens expire after 30 days
- API keys unique per user, regeneratable anytime

## License

MIT