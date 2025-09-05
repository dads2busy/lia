import subprocess
from pathlib import Path
from typing import List, Tuple
from os.path import dirname,basename

def build_supervisord_config(commands: List[Tuple[str, List[str]]], config_path: Path, pidfile_path: Path, log_dir: Path=Path("mcp_logs")):
    
    
    log_dir.mkdir(exist_ok=True)
    socketfile = Path("/tmp",f"{basename(dirname(pidfile_path))}_supervisord.socket")
    config = [
        "[supervisord]",
        f"pidfile={pidfile_path}",
        f"logfile={log_dir / 'supervisord.log'}",
        "logfile_maxbytes=1MB",
        "logfile_backups=2",
        "",
        "[unix_http_server]",
        f"file={socketfile}",
        "",
        "[rpcinterface:supervisor]",
        "supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface",
        "",
        "[supervisorctl]",
        f"serverurl=unix://{socketfile}"
    ]

    for tcmd in commands:
        name = tcmd[0]
        cmd = tcmd[1]
        print(f"Name: {name}")
        print(f"CMD: {cmd}")
        command_str = " ".join(cmd)
        config += [
            f"[program:{name}]",
            f"command={command_str}",
            f"stdout_logfile={log_dir / f'{name}.out.log'}",
            f"stderr_logfile={log_dir / f'{name}.err.log'}",
            "autorestart=true",
            "startsecs=1",
            "",
        ]

    config_path.write_text("\n".join(config))
    print(f"✅ Generated supervisor config at {config_path}")

def run_supervisorctl(config_path: Path, *args):
    cmd = ["supervisorctl", "-c", str(config_path)] + list(args)
    subprocess.run(cmd)

def start_supervisor(commands: List[Tuple[str, List[str]]], config_path: Path, pidfile_path: Path, overwrite: bool = False, log_dir: Path = Path("mcp_logs")):
    if not config_path.exists() or overwrite:
        build_supervisord_config(commands, config_path, pidfile_path,log_dir)
    else:
        print(f"ℹ️ Using existing supervisor config: {config_path}")

    print("🚀 Starting supervisord...")
    subprocess.run(["supervisord", "-c", str(config_path)])
    run_supervisorctl(config_path, "status")

def stop_supervisor(config_path: Path, pidfile_path: Path):
    print("🛑 Stopping supervisord...")
    run_supervisorctl(config_path, "shutdown")
    if pidfile_path.exists():
        pidfile_path.unlink()
        print(f"🧽 Removed PID file {pidfile_path}")

def restart_supervisor(commands: List[Tuple[str, List[str]]], config_path: Path, pidfile_path: Path, overwrite: bool = False,log_dir: Path = Path("mcp_logs")):
    if not config_path.exists() or overwrite:
        build_supervisord_config(commands, config_path, pidfile_path,log_dir)
    else:
        print(f"ℹ️ Using existing supervisor config: {config_path}")

    program_names = [name for name, _ in commands]
    run_supervisorctl(config_path, "restart", *program_names)

def status_supervisor(config_path: Path):
    run_supervisorctl(config_path, "status")
    
def check_all_running(config_path: Path) -> bool:
    if not config_path.exists():
        print(f"⚠️ Config file not found: {config_path}")
        return False

    try:
        result = subprocess.run(
            ["supervisorctl", "-c", str(config_path), "status"],
            capture_output=True, text=True, check=True
        )
        output = result.stdout.strip()
        if not output:
            print("⚠️ No programs listed in supervisor status output.")
            return False

        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[1] != "RUNNING":
                print(f"❌ Program not running: {line}")
                return False

        return True
    except subprocess.CalledProcessError as e:
        print("⚠️ Failed to check status:", e.stderr or str(e))
        return False
