"""Throwaway PostgreSQL cluster for migration tests.

Preference order: an explicit TERROIR_PG_TEST_DSN (CI service container),
else a private cluster bootstrapped with initdb in a temp directory and
reachable only over its own unix socket. Tests skip if neither is possible.
"""

from __future__ import annotations

import atexit
import getpass
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

_PG_BIN_CANDIDATES = [
    Path("/usr/lib/postgresql/18/bin"),
    Path("/usr/lib/postgresql/17/bin"),
    Path("/usr/lib/postgresql/16/bin"),
]

_cluster: dict[str, str] | None = None


def _pg_bin() -> Path | None:
    for candidate in _PG_BIN_CANDIDATES:
        if (candidate / "initdb").exists():
            return candidate
    initdb = shutil.which("initdb")
    return Path(initdb).parent if initdb else None


def _bootstrap() -> dict[str, str] | None:
    pg_bin = _pg_bin()
    if pg_bin is None:
        return None
    root = Path(tempfile.mkdtemp(prefix="terroir_pg_"))
    data = root / "data"
    socket_dir = root / "sock"
    socket_dir.mkdir()
    try:
        subprocess.run(
            [
                str(pg_bin / "initdb"),
                "-D",
                str(data),
                "-A",
                "trust",
                "--no-sync",
                "-U",
                getpass.getuser(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        shutil.rmtree(root, ignore_errors=True)
        return None

    # Run the postmaster as a direct foreground child (pg_ctl daemonizes,
    # which sandboxed environments may not allow).
    server = subprocess.Popen(
        [
            str(pg_bin / "postgres"),
            "-D",
            str(data),
            "-c",
            "listen_addresses=",
            "-c",
            f"unix_socket_directories={socket_dir}",
            "-c",
            "fsync=off",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _teardown() -> None:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(root, ignore_errors=True)

    atexit.register(_teardown)

    ready = pg_bin / "pg_isready"
    for _ in range(100):
        if server.poll() is not None:
            return None  # postmaster died
        probe = subprocess.run(
            [str(ready), "-h", str(socket_dir)], capture_output=True, timeout=10
        )
        if probe.returncode == 0:
            return {
                "dsn": f"host={socket_dir} dbname=postgres user={getpass.getuser()}"
            }
        time.sleep(0.2)
    return None


def scratch_dsn() -> str | None:
    """DSN of a database usable for destructive schema tests, or None.

    (Not named test_* so pytest does not collect it as a test.)
    """
    global _cluster
    env_dsn = os.environ.get("TERROIR_PG_TEST_DSN")
    if env_dsn:
        return env_dsn
    if _cluster is None:
        _cluster = _bootstrap() or {}
    return _cluster.get("dsn")
