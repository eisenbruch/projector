# Projector

Share your screen with multiple viewers via their web browsers. No app installs needed — attendees just scan a QR code or visit a URL.

## Prerequisites

- macOS (Apple Silicon or Intel)
- Python 3
- [ffmpeg](https://formulae.brew.sh/formula/ffmpeg) (`brew install ffmpeg`)
- Screen Recording permission granted to your terminal app (System Settings → Privacy & Security → Screen Recording)
- Host and attendees on the same WiFi network

## Usage

```bash
python3 server.py
```

Open http://localhost:8000/project on your machine, select a screen, and click **Start Sharing**.

A QR code and URL will appear — share either with your attendees.

## How It Works

1. ffmpeg captures your screen via macOS avfoundation at 30fps
2. Frames are hardware-encoded (H.264 via VideoToolbox) and output as HLS segments
3. A built-in HTTP server serves the HLS stream to any number of browser viewers
4. Attendees open the URL and the stream plays via hls.js (or native HLS on Safari/iOS)

## Routes

| Path | Purpose |
|------|---------|
| `/` | Viewer page (what attendees see) |
| `/project` | Control panel (presenter only) |

## Firewall

If attendees can't connect, allow incoming connections on port 8000:

**System Settings → Network → Firewall → Options** — allow Python.
