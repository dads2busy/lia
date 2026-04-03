import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def kill_orphan_on_port(port: int) -> bool:
    """Kill any process listening on the given port. Returns True if something was killed."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = {int(p) for p in result.stdout.split() if p.strip()}
    except (subprocess.TimeoutExpired, ValueError):
        return False
    if not pids:
        return False
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    # Wait briefly for processes to exit
    for _ in range(10):
        if not is_port_open(port):
            return True
        time.sleep(0.2)
    # Force kill if still alive
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return True


def find_mcp_server_script() -> Path:
    """Locate the FAISS MCP server script relative to this package."""
    pkg_dir = Path(__file__).resolve().parent.parent
    script = pkg_dir / "tools" / "mcp-server-hscode-faiss-rollupmd.py"
    if not script.exists():
        raise FileNotFoundError(f"MCP server script not found at {script}")
    return script


@contextmanager
def mcp_server_context(
    hs_rollup_file: str,
    port: int = 8000,
    python: Optional[str] = None,
):
    """Context manager that ensures a fresh FAISS MCP server is running.

    Kills any orphaned process on the port before starting a new one.
    The server subprocess is terminated on exit.
    """
    if is_port_open(port):
        print(f"Port {port} in use — killing orphaned MCP server.")
        kill_orphan_on_port(port)

    script = find_mcp_server_script()
    python = python or sys.executable
    # Server port is hardcoded in the script (mcp.run(..., port=8000))
    cmd = [python, str(script), "--file", hs_rollup_file]

    print(f"Starting MCP server: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for server to be ready (up to 90 seconds — first run builds FAISS index)
    for i in range(180):
        if is_port_open(port):
            print(f"MCP server ready on port {port}")
            break
        if proc.poll() is not None:
            raise RuntimeError(f"MCP server exited with code {proc.returncode}")
        time.sleep(0.5)
    else:
        proc.terminate()
        raise TimeoutError(f"MCP server did not start within 90 seconds on port {port}")

    try:
        yield
    finally:
        print(f"Shutting down MCP server (pid {proc.pid})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
