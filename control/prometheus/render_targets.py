"""Write targets/platform.json for Prometheus file_sd from PLATFORM_HOST."""

import json
from pathlib import Path

from resilience_core.settings import SERVICE_PORTS, settings

out = Path(__file__).parent / "targets" / "platform.json"
groups = [
    {"targets": [f"{settings.platform_host}:{port}"], "labels": {"service": name}}
    for name, port in SERVICE_PORTS.items()
]
out.write_text(json.dumps(groups, indent=2) + "\n")
print(f"wrote {out} -> {settings.platform_host}")
