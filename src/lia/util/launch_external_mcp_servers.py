#!/usr/bin/env python3

import typer
import os
import subprocess
from pathlib import Path
from typing import List, Optional

SUPERVISOR_CONF = Path("mcp_supervisord.conf")
SUPERVISORD_PID = Path("mcp_supervisord.pid")
LOG_DIR = Path("mcp_logs")
PROGRAM_NAMES = ["mcp_server_1", "mcp_server_2"]

def build_supervisord_config(commands: List[List[str]]):
    LOG_DIR.mkdir(exist_ok=True)

    config = [
        "[supervisord]",
        f"pidfile={SUPERVISORD_PID}",
        f"logfile={LOG_DIR / 'supervisord.log'}",
        "logfile_maxbytes=1MB",
        "logfile_backups=2",
        "",
    ]

    for i, cmd in enumerate(commands):
        name = PROGRAM_NAMES[i]
        command_str = " ".join(cmd)
        config += [
            f"[program:{name}]",
            f"command={command_str}",
            f"stdout_logfile={LOG_DIR / f'{name}.out.log'}",
            f"stderr_logfile={LOG_DIR / f'{name}.err.log'}",
            "autorestart=true",
            "startsecs=1",
            "",
        ]

    SUPERVISOR_CONF.write_text("\n".join(config))
    typer.echo(f"✅ Generated supervisor config at {SUPERVISOR_CONF}")


def run_supervisorctl(*args):
    cmd = ["supervisorctl", "-c", str(SUPERVISOR_CONF)] + list(args)
    subprocess.run(cmd)


def get_mcp_app(context_data: dict) -> typer.Typer:
    mcp_app = typer.Typer(help="MCP Supervisor Control")

    @mcp_app.command()
    def start(
        overwrite: bool = typer.Option(False, "--overwrite", "-o", help="Overwrite existing supervisor config")
    ):
        """Start MCP services under supervisord"""
        commands = context_data["commands"]

        if not SUPERVISOR_CONF.exists() or overwrite:
            build_supervisord_config(commands)
        else:
            typer.echo(f"ℹ️ Using existing supervisor config: {SUPERVISOR_CONF}")

        typer.echo("🚀 Starting supervisord...")
        subprocess.run(["supervisord", "-c", str(SUPERVISOR_CONF)])
        run_supervisorctl("status")

    @mcp_app.command()
    def stop():
        """Stop MCP services"""
        typer.echo("🛑 Stopping supervisord...")
        run_supervisorctl("shutdown")
        if SUPERVISORD_PID.exists():
            SUPERVISORD_PID.unlink()
            typer.echo(f"🧽 Removed PID file {SUPERVISORD_PID}")

    @mcp_app.command()
    def restart(
        overwrite: bool = typer.Option(False, "--overwrite", "-o", help="Overwrite existing supervisor config")
    ):
        """Restart MCP services"""
        commands = context_data["commands"]

        if overwrite or not SUPERVISOR_CONF.exists():
            build_supervisord_config(commands)
        else:
            typer.echo(f"ℹ️ Using existing supervisor config: {SUPERVISOR_CONF}")

        run_supervisorctl("restart", *PROGRAM_NAMES)

    @mcp_app.command()
    def status():
        """Show status of MCP services"""
        run_supervisorctl("status")

    return mcp_app
