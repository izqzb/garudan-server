"""Central configuration — all values come from env vars or .env file."""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Load .env from cwd or home
for env_path in [Path.cwd() / ".garudan.env", Path.home() / ".garudan.env", Path(".env")]:
    if env_path.exists():
        load_dotenv(env_path)
        break


class Settings:
    # Auth
    secret_key: str = os.getenv("SECRET_KEY", secrets.token_hex(32))
    access_token_expire_minutes: int = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))
    admin_username: str = os.getenv("ADMIN_USER", "admin")
    admin_password: str = os.getenv("ADMIN_PASS", "changeme")

    # SSH defaults (app connects directly or via profile override)
    ssh_host: str = os.getenv("SSH_HOST", "localhost")
    ssh_port: int = int(os.getenv("SSH_PORT", "22"))
    ssh_user: str = os.getenv("SSH_USER", os.getenv("USER", "root"))
    ssh_password: str | None = os.getenv("SSH_PASSWORD")
    ssh_key_path: str | None = os.getenv("SSH_KEY_PATH")

    # File browser
    file_root: str = os.getenv("FILE_ROOT", str(Path.home()))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "500"))

    # Server
    host: str = os.getenv("BIND_HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8400"))
    workers: int = int(os.getenv("WORKERS", "1"))

    # CORS — comma-separated origins. * allows all (dev mode)
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # Docker socket
    docker_socket: str = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")


settings = Settings()
