"""System stats — CPU, RAM, disk, network, processes."""
import asyncio
import time
from typing import Any

import psutil
from fastapi import APIRouter, Depends, Query

from .auth import verify_token

router = APIRouter(prefix="/api/system", tags=["system"])

# Cache stats for 1s so rapid polling doesn't spike the server
_cache: dict[str, Any] = {}
_cache_ts: float = 0
_CACHE_TTL = 1.0


def _get_stats() -> dict[str, Any]:
    global _cache, _cache_ts
    now = time.monotonic()
    if now - _cache_ts < _CACHE_TTL and _cache:
        return _cache

    cpu_per_core = psutil.cpu_percent(percpu=True)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    boot_time = psutil.boot_time()
    load_avg = psutil.getloadavg()
    temps: dict[str, list[dict]] = {}
    try:
        for k, v in psutil.sensors_temperatures().items():
            temps[k] = [{"label": e.label, "current": e.current, "high": e.high} for e in v]
    except Exception:
        pass

    _cache = {
        "cpu": {
            "percent": psutil.cpu_percent(),
            "per_core": cpu_per_core,
            "cores_logical": psutil.cpu_count(),
            "cores_physical": psutil.cpu_count(logical=False),
            "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None,
            "load_avg": list(load_avg),
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "percent": swap.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "boot_time": boot_time,
        "uptime_seconds": time.time() - boot_time,
        "temperatures": temps,
    }
    _cache_ts = now
    return _cache


@router.get("/stats")
async def get_stats(_: str = Depends(verify_token)):
    return _get_stats()


@router.get("/processes")
async def get_processes(
    limit: int = Query(default=30, le=200),
    sort: str = Query(default="cpu"),
    _: str = Depends(verify_token),
):
    """Return top processes sorted by cpu or memory."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent", "status", "cmdline", "create_time"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "username": info.get("username", ""),
                "cpu": round(info.get("cpu_percent") or 0, 1),
                "mem": round(info.get("memory_percent") or 0, 1),
                "status": info.get("status", ""),
                "cmd": " ".join(info.get("cmdline") or [])[:120],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    key = "cpu" if sort == "cpu" else "mem"
    procs.sort(key=lambda p: p[key], reverse=True)
    return procs[:limit]


@router.post("/processes/{pid}/kill")
async def kill_process(pid: int, _: str = Depends(verify_token)):
    try:
        p = psutil.Process(pid)
        p.terminate()
        return {"ok": True, "message": f"Sent SIGTERM to PID {pid}"}
    except psutil.NoSuchProcess:
        return {"ok": False, "message": "Process not found"}
    except psutil.AccessDenied:
        return {"ok": False, "message": "Permission denied"}


@router.get("/network/interfaces")
async def network_interfaces(_: str = Depends(verify_token)):
    interfaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=True)
    for name, addr_list in addrs.items():
        iface_io = io.get(name)
        iface_stat = stats.get(name)
        interfaces.append({
            "name": name,
            "addresses": [{"family": str(a.family), "address": a.address} for a in addr_list],
            "is_up": iface_stat.isup if iface_stat else False,
            "speed_mbps": iface_stat.speed if iface_stat else 0,
            "bytes_sent": iface_io.bytes_sent if iface_io else 0,
            "bytes_recv": iface_io.bytes_recv if iface_io else 0,
        })
    return interfaces
