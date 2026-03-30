"""WebSocket terminal proxy — holds the PTY session server-side."""
import asyncio
import json
import logging
from typing import Any

import asyncssh
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..config import settings
from .auth import ALGORITHM, settings as cfg
from jose import JWTError, jwt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["terminal"])

# How long to wait for SSH before dropping WS client (seconds)
SSH_CONNECT_TIMEOUT = 15
# Null-byte heartbeat from client — ignored, never forwarded to SSH
HEARTBEAT_BYTE = b"\x00"
# Max PTY read chunk
READ_SIZE = 32768


def _verify_ws_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        payload = jwt.decode(token, cfg.secret_key, algorithms=[ALGORITHM])
        return bool(payload.get("sub"))
    except JWTError:
        return False


class TerminalSession:
    """Owns one SSH connection + PTY process for one WebSocket client."""

    def __init__(self, ws: WebSocket, host: str, port: int, user: str):
        self.ws = ws
        self.host = host
        self.port = port
        self.user = user
        self._conn: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess | None = None
        self._cols = 80
        self._rows = 24
        self._running = False

    async def start(self) -> None:
        connect_kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "username": self.user,
            "known_hosts": None,  # users manage their own trust
            "connect_timeout": SSH_CONNECT_TIMEOUT,
            "keepalive_interval": 25,
            "keepalive_count_max": 10,
        }

        # Prefer key auth, fall back to password
        if settings.ssh_key_path:
            connect_kwargs["client_keys"] = [settings.ssh_key_path]
        elif settings.ssh_password:
            connect_kwargs["password"] = settings.ssh_password

        self._conn = await asyncssh.connect(**connect_kwargs)
        self._process = await self._conn.create_process(
            term_type="xterm-256color",
            term_size=(self._cols, self._rows),
            encoding=None,  # raw bytes — fastest path
        )
        self._running = True

    async def resize(self, cols: int, rows: int) -> None:
        self._cols = cols
        self._rows = rows
        if self._process:
            self._process.change_terminal_size(cols, rows)

    async def pump_ssh_to_ws(self) -> None:
        """Read PTY output and forward to WebSocket client."""
        assert self._process is not None
        try:
            while self._running:
                data = await self._process.stdout.read(READ_SIZE)
                if not data:
                    break
                await self.ws.send_bytes(data)
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
        except Exception as e:
            logger.debug("SSH→WS pump ended: %s", e)
        finally:
            self._running = False

    async def send_to_ssh(self, data: bytes) -> None:
        if self._process and self._running:
            try:
                self._process.stdin.write(data)
            except Exception:
                pass

    async def close(self) -> None:
        self._running = False
        try:
            if self._process:
                self._process.close()
        except Exception:
            pass
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass


@router.websocket("/ws/terminal")
async def terminal_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    host: str = Query(default=None),
    port: int = Query(default=None),
    user: str = Query(default=None),
):
    """
    WebSocket terminal endpoint.

    Query params:
      token  — JWT bearer token
      host   — SSH host (overrides server default)
      port   — SSH port (overrides server default)
      user   — SSH username (overrides server default)
    """
    # Auth check
    if not _verify_ws_token(token):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()

    ssh_host = host or settings.ssh_host
    ssh_port = port or settings.ssh_port
    ssh_user = user or settings.ssh_user

    session = TerminalSession(websocket, ssh_host, ssh_port, ssh_user)

    # Connect SSH
    try:
        await session.start()
        await websocket.send_text(
            f"\x1b[2m\u276f Connected to {ssh_user}@{ssh_host}:{ssh_port}\x1b[0m\r\n"
        )
    except Exception as e:
        err = str(e)
        logger.warning("SSH connect failed for %s@%s: %s", ssh_user, ssh_host, err)
        await websocket.send_text(f"\x1b[31m[SSH Error] {err}\x1b[0m\r\n")
        await websocket.close(code=4500, reason="SSH connection failed")
        return

    # Pump SSH output → client in background
    pump_task = asyncio.create_task(session.pump_ssh_to_ws())

    try:
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break

            # Binary: raw input from terminal (keystrokes)
            if "bytes" in message and message["bytes"]:
                data = message["bytes"]
                if data == HEARTBEAT_BYTE:
                    continue  # discard — just a keepalive ping
                await session.send_to_ssh(data)

            # Text: control messages (resize JSON, etc.)
            elif "text" in message and message["text"]:
                try:
                    msg = json.loads(message["text"])
                    if msg.get("type") == "resize":
                        cols = int(msg.get("cols", 80))
                        rows = int(msg.get("rows", 24))
                        await session.resize(cols, rows)
                except (json.JSONDecodeError, ValueError):
                    pass  # ignore malformed control messages

    except Exception as e:
        logger.debug("WS receive loop ended: %s", e)
    finally:
        pump_task.cancel()
        await session.close()
        logger.info("Terminal session closed for %s@%s", ssh_user, ssh_host)
