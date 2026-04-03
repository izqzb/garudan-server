# garudan-server

Backend API for the [Garudan](https://github.com/izqzb/garudan) mobile app.

## Install in 60 seconds

```bash
pip3 install garudan-server
garudan-server setup
garudan-server start
```

That's it. The interactive setup wizard asks for your SSH credentials and generates a config at `~/.garudan.env`.

## Requirements

- Python 3.10+
- Linux server (SSH must be enabled)
- Docker socket readable (for Docker features) — optional

## Expose publicly (optional)

For the app to work outside your home network, expose port 8400:

**Cloudflare Tunnel (recommended — free):**
```bash
cloudflared tunnel create garudan
cloudflared tunnel route dns garudan api.yourdomain.com
cloudflared tunnel run --url http://localhost:8400 garudan
```

**Tailscale (easiest — no domain needed):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
# Use your Tailscale IP (100.x.x.x:8400) as the API URL in the app
```

## Configuration

All settings live in `~/.garudan.env`:

```env
ADMIN_USER=admin
ADMIN_PASS=your_password
SECRET_KEY=auto_generated
SSH_HOST=localhost
SSH_PORT=22
SSH_USER=youruser
SSH_PASSWORD=yourpassword   # or use SSH_KEY_PATH
FILE_ROOT=/home/youruser
PORT=8400
```

## API Docs

Once running, visit `http://localhost:8400/docs` for the full interactive API documentation.

## Systemd Service (auto-start on boot)

```bash
cat > /etc/systemd/system/garudan-server.service << 'UNIT'
[Unit]
Description=Garudan Server
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
ExecStart=/usr/local/bin/garudan-server start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl enable --now garudan-server
```

## Docker

```bash
docker run -d \
  --name garudan-server \
  -p 8400:8400 \
  -e ADMIN_USER=admin \
  -e ADMIN_PASS=changeme \
  -e SSH_HOST=host.docker.internal \
  -e SSH_USER=youruser \
  -e SSH_PASSWORD=yourpassword \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /home/youruser:/data \
  --restart unless-stopped \
  ghcr.io/your-username/garudan-server:latest
```

## License

MIT
