"""Subprocess helper shared by collectors.

Every collector that shells out goes through run_cmd so timeouts, encoding and
the "no console window" flag are handled in one place (the backend runs under
pythonw at logon; a stray console per nvidia-smi call would flash on screen).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class CommandFailed(RuntimeError):
    def __init__(self, args: list[str], rc: int, stderr: str):
        super().__init__(f"{args[0]} exited {rc}: {stderr.strip()[:300]}")
        self.rc = rc
        self.stderr = stderr


def run_cmd(args: list[str], timeout: float = 20.0, cwd: Path | None = None) -> str:
    """Run a command, return stdout decoded as UTF-8 (errors replaced)."""
    proc = subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        creationflags=CREATE_NO_WINDOW,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise CommandFailed(args, proc.returncode, proc.stderr.decode("utf-8", errors="replace"))
    return out


def run_powershell_file(script: Path, *args: str, timeout: float = 40.0) -> str:
    return run_cmd(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), *args],
        timeout=timeout,
    )
