#!/usr/bin/env python
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from urllib import error as urlerror
from urllib import request as urlrequest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WEB_ROOT = PROJECT_ROOT / "web"
DEEPTUTOR_WEB_NODE_MODULES = Path("/Users/frud_/Desktop/DeepTutor/web/node_modules")


def choose_specific_port(preferred: int, span: int = 40) -> int:
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port found in {preferred}-{preferred + span - 1}.")


def stream_output(prefix: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{prefix}] {line.rstrip()}", flush=True)


def wait_for_http(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlrequest.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (OSError, urlerror.URLError):
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}")


def main() -> None:
    os.chdir(PROJECT_ROOT)
    backend_port = int(os.getenv("BACKEND_PORT", "0")) or choose_specific_port(8000)
    frontend_port = int(os.getenv("FRONTEND_PORT", "0")) or choose_specific_port(3000)

    node_modules = WEB_ROOT / "node_modules"
    if not node_modules.exists():
        if DEEPTUTOR_WEB_NODE_MODULES.exists():
            node_modules.symlink_to(DEEPTUTOR_WEB_NODE_MODULES, target_is_directory=True)
        else:
            raise RuntimeError(
                "web/node_modules is missing, and /Users/frud_/Desktop/DeepTutor/web/node_modules was not found."
            )

    backend_env = os.environ.copy()
    # Ensure the project root is always in PYTHONPATH so EduFlowGraph is importable
    existing_pythonpath = backend_env.get("PYTHONPATH", "")
    backend_env["PYTHONPATH"] = (
        str(PROJECT_ROOT) + (":" + existing_pythonpath if existing_pythonpath else "")
    )
    frontend_env = os.environ.copy()
    frontend_env["NEXT_PUBLIC_API_BASE"] = f"http://127.0.0.1:{backend_port}"

    backend_cmd = [
        ".venv/bin/python",
        "-m",
        "uvicorn",
        "EduFlowGraph.web_app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(backend_port),
    ]
    frontend_cmd = [
        "npm",
        "run",
        "dev",
        "--",
        "--hostname",
        "127.0.0.1",
        "--port",
        str(frontend_port),
    ]

    backend = subprocess.Popen(
        backend_cmd,
        cwd=str(PROJECT_ROOT),
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    frontend = subprocess.Popen(
        frontend_cmd,
        cwd=str(WEB_ROOT),
        env=frontend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    backend_thread = threading.Thread(target=stream_output, args=("backend", backend), daemon=True)
    frontend_thread = threading.Thread(target=stream_output, args=("frontend", frontend), daemon=True)
    backend_thread.start()
    frontend_thread.start()

    try:
        wait_for_http(f"http://127.0.0.1:{backend_port}/api/health", 60)
        wait_for_http(f"http://127.0.0.1:{frontend_port}", 120)
        print(f"Backend ready at http://127.0.0.1:{backend_port}", flush=True)
        print(f"Frontend ready at http://127.0.0.1:{frontend_port}", flush=True)
        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()
            if backend_code is not None:
                raise RuntimeError(f"Backend exited with code {backend_code}")
            if frontend_code is not None:
                raise RuntimeError(f"Frontend exited with code {frontend_code}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down EduFlowGraph web stack...", flush=True)
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()
        for process in (frontend, backend):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
