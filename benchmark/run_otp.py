#!/usr/bin/env python3
"""
Build and serve one GTFS variant in an isolated OTP container.

ISOLATION GUARANTEES (read this before changing anything)
---------------------------------------------------------
The project's own OTP runs from docker-compose.yml on host port 8080 with
`./otp` bind-mounted.  This script must never disturb it, so:

  * it never invokes `docker compose` — only `docker run` / `stop` / `rm`;
  * every container it creates is named `otp-bench-<variant>` and it refuses to
    stop or remove any container whose name lacks the `otp-bench-` prefix
    (see _assert_ours);
  * it publishes only host port 8081 (default `--port`) and aborts if that port
    is already in use by something that is not one of its own containers;
  * it bind-mounts `benchmark/data/otp/<variant>/`, never `otp/`.  The OSM
    extract is *hard-linked* into that directory (copy-on-fallback), so the
    176 MB pbf is not duplicated six times and `otp/egypt-latest.osm.pbf` is
    never written to.  The GTFS zip is a real copy of the variant, so nothing
    can write back into `benchmark/data/variants/`.

WHAT IS MEASURED
----------------
  build    : wall-clock seconds for `--build --save` (container start to exit),
             plus the resulting graph.obj size in bytes.
  serve    : seconds until the health endpoint answers, then container RSS after
             a warmup of `--warmup` plan queries.

Caveat on RSS: a JVM with a fixed `-Xmx` reports RSS that is largely a function
of the heap ceiling and GC timing, not of graph size.  RSS is therefore only
comparable across variants if `--xmx` is identical for all of them (it is, by
default).  graph.obj size is the more honest size signal; treat RSS as a
smoke-level indicator.  Both, plus everything else, land in
`benchmark/data/otp/<variant>/run_meta.json`.

USAGE
-----
    python3 benchmark/run_otp.py prepare --variant spacing_500m
    python3 benchmark/run_otp.py build   --variant spacing_500m
    python3 benchmark/run_otp.py serve   --variant spacing_500m
    python3 benchmark/run_otp.py status
    python3 benchmark/run_otp.py stop    --variant spacing_500m
    python3 benchmark/run_otp.py up      --variant spacing_500m   # prepare+build+serve
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from variants import DATA_DIR, REPO_ROOT, VARIANTS_DIR

OTP_IMAGE = "opentripplanner/opentripplanner:latest"  # same image as docker-compose.yml
CONTAINER_PREFIX = "otp-bench-"
OTP_DIR = DATA_DIR / "otp"
OSM_PBF = REPO_ROOT / "otp" / "egypt-latest.osm.pbf"
BUILD_CONFIG = REPO_ROOT / "otp" / "build-config.json"
DEFAULT_PORT = 8081
DEFAULT_XMX = "6G"
FORBIDDEN_PORTS = {8080, 8090}  # project OTP, project Go server


# --- docker plumbing ---------------------------------------------------------
def _docker(*args, check=True, capture=True, timeout=None):
    return subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        timeout=timeout,
    )


def container_name(variant: str) -> str:
    return f"{CONTAINER_PREFIX}{variant}"


def _assert_ours(name: str) -> None:
    """Hard guard: never touch a container we did not create."""
    if not name.startswith(CONTAINER_PREFIX):
        raise SystemExit(
            f"refusing to operate on container {name!r}: "
            f"only {CONTAINER_PREFIX}* containers are managed by this script"
        )


def _exists(name: str) -> bool:
    out = _docker(
        "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"
    ).stdout.strip()
    return out == name


def _running(name: str) -> bool:
    out = _docker(
        "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"
    ).stdout.strip()
    return out == name


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _check_port(port: int, variant: str) -> None:
    if port in FORBIDDEN_PORTS:
        raise SystemExit(
            f"port {port} belongs to the project's own services — refusing"
        )
    if _port_free(port):
        return
    # occupied: only acceptable if it is our own container for this variant
    if _running(container_name(variant)):
        raise SystemExit(
            f"port {port} is held by {container_name(variant)} — "
            f"run `stop --variant {variant}` first"
        )
    raise SystemExit(
        f"port {port} is already in use by something else. Pass a different --port."
    )


# --- data dir ----------------------------------------------------------------
def variant_dir(variant: str) -> Path:
    return OTP_DIR / variant


def prepare(variant: str, force: bool = False) -> Path:
    """Assemble an isolated OTP input directory for `variant`."""
    src_zip = VARIANTS_DIR / f"{variant}.zip"
    if not src_zip.exists():
        raise SystemExit(
            f"{src_zip} not found — build it first:\n"
            f"  python3 benchmark/variants.py build --spacing <m>"
        )
    if not OSM_PBF.exists():
        raise SystemExit(f"{OSM_PBF} not found (see README.md first-time setup)")

    d = variant_dir(variant)
    d.mkdir(parents=True, exist_ok=True)

    dst_zip = d / "alex_gtfs.zip"
    if force or not dst_zip.exists() or dst_zip.stat().st_mtime < src_zip.stat().st_mtime:
        shutil.copy2(src_zip, dst_zip)

    dst_pbf = d / OSM_PBF.name
    if not dst_pbf.exists():
        try:
            os.link(OSM_PBF, dst_pbf)  # hardlink: no 176 MB copy, read-only use
            how = "hardlink"
        except OSError:
            shutil.copy2(OSM_PBF, dst_pbf)
            how = "copy"
        print(f"  {OSM_PBF.name}: {how}")

    shutil.copy2(BUILD_CONFIG, d / "build-config.json")
    print(f"prepared {d}")
    return d


def _meta_path(variant: str) -> Path:
    return variant_dir(variant) / "run_meta.json"


def _load_meta(variant: str) -> dict:
    p = _meta_path(variant)
    return json.loads(p.read_text()) if p.exists() else {"variant": variant}


def _save_meta(variant: str, patch: dict) -> dict:
    meta = _load_meta(variant)
    meta.update(patch)
    _meta_path(variant).write_text(json.dumps(meta, indent=2) + "\n")
    return meta


# --- build -------------------------------------------------------------------
def build(variant: str, xmx: str = DEFAULT_XMX, timeout: int = 3600) -> dict:
    """Run `--build --save` to completion and time it."""
    d = prepare(variant)
    graph = d / "graph.obj"
    if graph.exists():
        graph.unlink()
    name = container_name(f"build-{variant}")
    _assert_ours(name)
    if _exists(name):
        _docker("rm", "-f", name, check=False)

    log = d / "build.log"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{d}:/var/opentripplanner",
        "-e", f"JAVA_TOOL_OPTIONS=-Xmx{xmx}",
        OTP_IMAGE,
        "--build", "--save",
    ]
    print(f"building {variant} (xmx={xmx}) ...")
    t0 = time.perf_counter()
    with open(log, "w") as lf:
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
    elapsed = time.perf_counter() - t0

    if proc.returncode != 0:
        print(log.read_text()[-4000:])
        raise SystemExit(f"graph build failed (exit {proc.returncode}); see {log}")
    if not graph.exists():
        raise SystemExit(f"build finished but {graph} is missing; see {log}")

    patch = {
        "variant": variant,
        "image": OTP_IMAGE,
        "xmx": xmx,
        "build_seconds": round(elapsed, 1),
        "graph_obj_bytes": graph.stat().st_size,
        "gtfs_zip_bytes": (d / "alex_gtfs.zip").stat().st_size,
        "build_log": str(log),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **_grep_build_summary(log),
    }
    meta = _save_meta(variant, patch)
    print(
        f"built in {elapsed:.1f}s, graph.obj = {graph.stat().st_size/1e6:.1f} MB, "
        f"stops = {patch['transit_stops']}, patterns = {patch['transit_patterns']}"
    )
    return meta


def _grep_build_summary(log: Path) -> dict:
    """Pull OTP's `Transit built.` summary line out of the build log.

        Transit built. |Stops|=5,638 |Patterns|=192 |ConstrainedTransfers|=0

    A variant whose synthetic stop_times are non-monotonic makes OTP silently
    drop patterns (this is exactly what happened on 2026-05-30), so recording
    these counts is the cheapest possible correctness tripwire: if
    transit_patterns falls below the trip count, that variant's feed is broken
    and its deviation numbers are meaningless.
    """
    import re

    text = log.read_text(errors="replace")

    def grab(pattern):
        hits = re.findall(pattern, text)
        return int(hits[-1].replace(",", "")) if hits else None

    return {
        "transit_patterns": grab(r"\|Patterns\|=(\d[\d,]*)"),
        "transit_stops": grab(r"\|Stops\|=(\d[\d,]*)"),
        "frequency_entries": grab(r"Added (\d[\d,]*) frequency-based"),
        "single_trip_entries": grab(r"frequency-based and (\d[\d,]*) single-trip"),
    }


# --- serve -------------------------------------------------------------------
def serve(
    variant: str,
    port: int = DEFAULT_PORT,
    xmx: str = DEFAULT_XMX,
    warmup: int = 5,
    ready_timeout: int = 600,
) -> dict:
    d = variant_dir(variant)
    if not (d / "graph.obj").exists():
        raise SystemExit(f"no graph.obj for {variant} — run `build --variant {variant}`")
    _check_port(port, variant)

    name = container_name(variant)
    _assert_ours(name)
    if _exists(name):
        _docker("rm", "-f", name, check=False)

    cmd = [
        "docker", "run", "-d", "--name", name,
        "-p", f"127.0.0.1:{port}:8080",  # container keeps OTP's default 8080
        "-v", f"{d}:/var/opentripplanner",
        "-e", f"JAVA_TOOL_OPTIONS=-Xmx{xmx}",
        OTP_IMAGE,
        "--load", "--serve",
    ]
    print(f"starting {name} on 127.0.0.1:{port} ...")
    _docker(*cmd[1:])

    t0 = time.perf_counter()
    base = f"http://127.0.0.1:{port}"
    while time.perf_counter() - t0 < ready_timeout:
        if _healthy(base):
            break
        if not _running(name):
            logs = _docker("logs", "--tail", "60", name, check=False).stdout
            raise SystemExit(f"{name} died during startup:\n{logs}")
        time.sleep(2)
    else:
        raise SystemExit(f"{name} not healthy after {ready_timeout}s")
    ready = time.perf_counter() - t0
    print(f"healthy after {ready:.1f}s")

    for i in range(warmup):
        _warmup_query(base)
    time.sleep(3)  # let allocation settle before reading RSS

    patch = {
        "port": port,
        "endpoint": f"{base}/otp/gtfs/v1",
        "container": name,
        "load_seconds": round(ready, 1),
        "warmup_queries": warmup,
        "rss_bytes": _rss_bytes(name),
        "cgroup_memory_current": _cgroup_mem(name),
        "docker_mem_usage": _docker_mem_string(name),
        "served_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    meta = _save_meta(variant, patch)
    rss = patch["rss_bytes"]
    print(f"RSS after warmup: {rss/1e6:.0f} MB" if rss else "RSS: unavailable")
    print(f"query endpoint: {patch['endpoint']}")
    return meta


def _healthy(base: str) -> bool:
    for path in ("/otp/actuators/health", "/otp"):
        try:
            with urllib.request.urlopen(base + path, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            continue
    return False


WARMUP_QUERY = (
    '{ plan(from:{lat:31.234556,lon:29.963111}, to:{lat:31.212118,lon:29.933577}, '
    'date:"2026-08-03", time:"08:00:00", '
    "transportModes:[{mode:BUS},{mode:WALK}]) { itineraries { duration } } }"
)


def _warmup_query(base: str) -> None:
    req = urllib.request.Request(
        base + "/otp/gtfs/v1",
        data=json.dumps({"query": WARMUP_QUERY}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as e:  # warmup failures are not fatal
        print(f"  warmup query failed: {e}")


def _rss_bytes(name: str) -> int | None:
    """Container RSS from the cgroup, falling back to `docker stats`."""
    out = _docker(
        "exec", name, "cat", "/sys/fs/cgroup/memory.stat", check=False
    ).stdout
    for line in out.splitlines():
        if line.startswith("anon "):
            return int(line.split()[1])
    mem = _docker_mem_string(name)
    if mem:
        try:
            used = mem.split("/")[0].strip()
            unit = "".join(c for c in used if c.isalpha()).upper()
            num = float("".join(c for c in used if c.isdigit() or c == "."))
            return int(num * {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}[unit])
        except Exception:
            return None
    return None


def _cgroup_mem(name: str) -> int | None:
    out = _docker(
        "exec", name, "cat", "/sys/fs/cgroup/memory.current", check=False
    ).stdout.strip()
    return int(out) if out.isdigit() else None


def _docker_mem_string(name: str) -> str | None:
    out = _docker(
        "stats", "--no-stream", "--format", "{{.MemUsage}}", name, check=False
    ).stdout.strip()
    return out or None


# --- lifecycle ---------------------------------------------------------------
def stop(variant: str, remove: bool = True) -> None:
    name = container_name(variant)
    _assert_ours(name)
    if not _exists(name):
        print(f"{name}: not present")
        return
    _docker("stop", "-t", "10", name, check=False)
    if remove:
        _docker("rm", "-f", name, check=False)
    print(f"{name}: stopped")


def stop_all() -> None:
    out = _docker(
        "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}", "--format", "{{.Names}}"
    ).stdout.split()
    for name in out:
        _assert_ours(name)
        _docker("rm", "-f", name, check=False)
        print(f"removed {name}")
    if not out:
        print("no benchmark containers")


def status() -> None:
    out = _docker(
        "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}",
        "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}",
    ).stdout
    print("--- benchmark containers ---")
    print(out.strip() or "(none)")
    print("--- variants prepared ---")
    if OTP_DIR.exists():
        for d in sorted(OTP_DIR.iterdir()):
            g = d / "graph.obj"
            print(
                f"{d.name:24s} graph.obj={'%.1f MB' % (g.stat().st_size/1e6) if g.exists() else 'MISSING'}"
            )
    print("--- project services (must be untouched) ---")
    print(f"  host :8080 free={_port_free(8080)}  :8090 free={_port_free(8090)}")


# --- CLI ---------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Isolated OTP runner for benchmark variants")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_variant(p, port=False):
        p.add_argument("--variant", required=True, help="e.g. spacing_500m or fixed")
        p.add_argument("--xmx", default=DEFAULT_XMX)
        if port:
            p.add_argument("--port", type=int, default=DEFAULT_PORT)
        return p

    add_variant(sub.add_parser("prepare")).add_argument("--force", action="store_true")
    add_variant(sub.add_parser("build"))
    p = add_variant(sub.add_parser("serve"), port=True)
    p.add_argument("--warmup", type=int, default=5)
    p = add_variant(sub.add_parser("up"), port=True)
    p.add_argument("--warmup", type=int, default=5)
    p = sub.add_parser("stop")
    p.add_argument("--variant", required=True)
    sub.add_parser("stop-all")
    sub.add_parser("status")

    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        prepare(a.variant, force=a.force)
    elif a.cmd == "build":
        build(a.variant, xmx=a.xmx)
    elif a.cmd == "serve":
        serve(a.variant, port=a.port, xmx=a.xmx, warmup=a.warmup)
    elif a.cmd == "up":
        build(a.variant, xmx=a.xmx)
        serve(a.variant, port=a.port, xmx=a.xmx, warmup=a.warmup)
    elif a.cmd == "stop":
        stop(a.variant)
    elif a.cmd == "stop-all":
        stop_all()
    elif a.cmd == "status":
        status()


if __name__ == "__main__":
    main()
