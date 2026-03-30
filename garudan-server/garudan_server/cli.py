"""garudan-server CLI — pip3 install garudan-server → garudan-server start"""
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

app = typer.Typer(
    name="garudan-server",
    help="Garudan Server — backend for the Garudan mobile SSH/server management app",
    add_completion=False,
)
console = Console()


def _env_path() -> Path:
    return Path.home() / ".garudan.env"


def _load_env() -> dict[str, str]:
    p = _env_path()
    if not p.exists():
        return {}
    env = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _save_env(env: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in env.items()]
    _env_path().write_text("\n".join(lines) + "\n")


@app.command()
def setup():
    """Interactive first-time setup wizard."""
    console.print(Panel.fit(
        "[bold cyan]Garudan Server Setup[/bold cyan]\n"
        "Configure your server in ~60 seconds.",
        border_style="cyan",
    ))

    env = _load_env()

    console.print("\n[bold]1. Authentication[/bold]")
    env["ADMIN_USER"] = Prompt.ask("Admin username", default=env.get("ADMIN_USER", "admin"))
    import secrets as _sec
    env["ADMIN_PASS"] = Prompt.ask(
        "Admin password", password=True,
        default=env.get("ADMIN_PASS", ""),
    ) or env.get("ADMIN_PASS", _sec.token_urlsafe(12))
    env["SECRET_KEY"] = env.get("SECRET_KEY") or _sec.token_hex(32)

    console.print("\n[bold]2. SSH Connection[/bold]")
    env["SSH_HOST"] = Prompt.ask("SSH host", default=env.get("SSH_HOST", "localhost"))
    env["SSH_PORT"] = Prompt.ask("SSH port", default=env.get("SSH_PORT", "22"))
    env["SSH_USER"] = Prompt.ask("SSH username", default=env.get("SSH_USER", os.getenv("USER", "root")))

    auth_type = Prompt.ask(
        "SSH auth type", choices=["password", "key"], default="password"
    )
    if auth_type == "password":
        env["SSH_PASSWORD"] = Prompt.ask("SSH password", password=True)
    else:
        default_key = str(Path.home() / ".ssh" / "id_ed25519")
        env["SSH_KEY_PATH"] = Prompt.ask("Path to SSH private key", default=default_key)

    console.print("\n[bold]3. Server[/bold]")
    env["PORT"] = Prompt.ask("API port", default=env.get("PORT", "8400"))
    env["FILE_ROOT"] = Prompt.ask(
        "File browser root directory",
        default=env.get("FILE_ROOT", str(Path.home())),
    )

    _save_env(env)
    console.print(f"\n[green]✓ Config saved to {_env_path()}[/green]")
    console.print("\nRun [bold cyan]garudan-server start[/bold cyan] to launch.")


@app.command()
def start(
    host: str = typer.Option(None, help="Bind host"),
    port: int = typer.Option(None, help="Port"),
    workers: int = typer.Option(1, help="Uvicorn workers"),
    reload: bool = typer.Option(False, help="Dev auto-reload"),
):
    """Start the Garudan API server."""
    env = _load_env()
    if not env:
        console.print("[yellow]No config found. Running setup first...[/yellow]\n")
        setup()
        env = _load_env()

    bind_host = host or env.get("BIND_HOST", "0.0.0.0")
    bind_port = str(port or env.get("PORT", "8400"))

    console.print(Panel.fit(
        f"[bold cyan]Garudan Server[/bold cyan]\n"
        f"Listening on [bold]{bind_host}:{bind_port}[/bold]\n"
        f"Docs → http://localhost:{bind_port}/docs\n"
        f"Press Ctrl+C to stop",
        border_style="cyan",
    ))

    # Set env vars for the process
    for k, v in env.items():
        os.environ.setdefault(k, v)

    import uvicorn
    uvicorn.run(
        "garudan_server.main:app",
        host=bind_host,
        port=int(bind_port),
        workers=workers,
        reload=reload,
        log_level="info",
        ws_ping_interval=25,
        ws_ping_timeout=60,
    )


@app.command()
def status():
    """Show current configuration."""
    env = _load_env()
    if not env:
        console.print("[red]No config found. Run: garudan-server setup[/red]")
        raise typer.Exit(1)

    table = Table(title="Garudan Server Config", border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    safe_keys = {"PORT", "BIND_HOST", "SSH_HOST", "SSH_PORT", "SSH_USER", "FILE_ROOT", "ADMIN_USER", "WORKERS"}
    for k, v in env.items():
        if k in safe_keys:
            table.add_row(k, v)
        else:
            table.add_row(k, "••••••••")

    console.print(table)


@app.command()
def reset():
    """Delete configuration and start fresh."""
    if Confirm.ask("[red]Delete all config?[/red]"):
        _env_path().unlink(missing_ok=True)
        console.print("[green]Config deleted.[/green]")


if __name__ == "__main__":
    app()
