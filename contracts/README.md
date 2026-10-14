# Contracts

These files are the only interface between the Mac (platform) and Fedora (control room).
Change them only through a PR that both people approve. `scripts/check_contracts.py`
parses `metrics.md`, so keep its main table format intact.

| File | Owner | Covers |
| --- | --- | --- |
| `metrics.md` | both | Metric names, types, labels, `service` label values |
| `redis_keys.md` | both | Every Redis key, writer, reader, TTL |
| `control_api.md` | both | Ports, control API, chaos hooks, public API, degradation levels |
| `features.md` | Fedora | Failure label, feature list, units, windows (Phase 2) |
