# Projector

Browser-based screen sharing for workshops using ffmpeg HLS streaming.

## Architecture

- `server.py` — Python stdlib HTTP server (no dependencies). Manages ffmpeg subprocess for screen capture and serves HLS segments + control UI.
- `control.html` — Presenter control panel. Dark theme, source picker, QR code via CDN.
- `viewer.html` — Attendee viewer. Uses hls.js from CDN for HLS playback.

## How It Works

1. ffmpeg captures screen via avfoundation (macOS) at 30fps
2. Hardware-encodes to H.264 via VideoToolbox (`h264_videotoolbox`)
3. Outputs HLS segments (1s each) to `/tmp/projector-stream/`
4. Built-in HTTP server serves segments to viewers

## Routes

| Path | Purpose |
|------|---------|
| `/` | Viewer (attendees) — serves `viewer.html` when streaming, placeholder when not |
| `/project` | Control panel (presenter) — serves `control.html` |
| `/hls/*` | HLS segments from `/tmp/projector-stream/` |
| `/api/status` | JSON: `{running, ip, viewer_url}` |
| `/api/sources` | JSON: `{screens}` — lists avfoundation capture devices |
| `/api/start` | POST `{id}` — starts ffmpeg capture |
| `/api/stop` | POST — kills ffmpeg |

## Key Details

- No third-party Python dependencies — stdlib only
- QR generation is client-side via CDN
- ffmpeg requires `-enc_time_base 1/30` to fix duration-0 packet issue in ffmpeg 8.0
- Screen Recording permission required for the terminal app running the server
- Port 8000
