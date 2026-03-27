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
    """Context manager that ensures the FAISS MCP server is running.

    If already running on the port, reuses it (launched_here=False).
    Otherwise, starts it as a subprocess and kills on exit.
    """
    if is_port_open(port):
        print(f"MCP server already running on port {port}, reusing.")
        yield
        return

    script = find_mcp_server_script()
    python = python or sys.executable
    cmd = [python, str(script), "--file", hs_rollup_file, "--port", str(port)]

    print(f"Starting MCP server: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for server to be ready (up to 30 seconds)
    for i in range(60):
        if is_port_open(port):
            print(f"MCP server ready on port {port}")
            break
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise RuntimeError(f"MCP server exited with code {proc.returncode}: {stderr}")
        time.sleep(0.5)
    else:
        proc.terminate()
        raise TimeoutError(f"MCP server did not start within 30 seconds on port {port}")

    try:
        yield
    finally:
        print(f"Shutting down MCP server (pid {proc.pid})")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
