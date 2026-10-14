"""Start the five mock services as separate processes (like the real platform). Ctrl+C stops all."""

import os
import signal
import subprocess
import sys

from resilience_core.settings import SERVICE_PORTS


def main() -> None:
    procs = []
    for service, port in SERVICE_PORTS.items():
        env = {**os.environ, "CS_SERVICE": service}
        procs.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "mock_platform.app:app", "--host", "0.0.0.0",
             "--port", str(port), "--log-level", "warning", "--no-access-log"],
            env=env,
        ))
        print(f"mock {service:<15} :{port}  pid {procs[-1].pid}", flush=True)

    def stop(*_):
        for p in procs:
            p.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    codes = [p.wait() for p in procs]
    sys.exit(max(codes))


if __name__ == "__main__":
    main()
