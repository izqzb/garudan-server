"""Docker container management routes."""
import docker
import docker.errors
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from ..config import settings
from .auth import verify_token

router = APIRouter(prefix="/api/docker", tags=["docker"])


def _client() -> docker.DockerClient:
    try:
        return docker.DockerClient(base_url=f"unix://{settings.docker_socket}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")


def _fmt_container(c) -> dict:
    ports: dict = {}
    if c.ports:
        for container_port, host_bindings in c.ports.items():
            if host_bindings:
                ports[container_port] = [b["HostPort"] for b in host_bindings]

    return {
        "id": c.short_id,
        "full_id": c.id,
        "name": c.name,
        "image": c.image.tags[0] if c.image.tags else c.image.short_id,
        "status": c.status,
        "state": c.attrs.get("State", {}),
        "ports": ports,
        "created": c.attrs.get("Created", ""),
        "labels": c.labels,
        "restart_policy": c.attrs.get("HostConfig", {}).get("RestartPolicy", {}),
        "networks": list(c.attrs.get("NetworkSettings", {}).get("Networks", {}).keys()),
    }


@router.get("/containers")
async def list_containers(
    all: bool = Query(default=True),
    _: str = Depends(verify_token),
):
    client = _client()
    try:
        containers = client.containers.list(all=all)
        return [_fmt_container(c) for c in containers]
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containers/{container_id}/logs")
async def container_logs(
    container_id: str = Path(...),
    tail: int = Query(default=100, le=1000),
    _: str = Depends(verify_token),
):
    client = _client()
    try:
        c = client.containers.get(container_id)
        logs = c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        return {"id": container_id, "logs": logs}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")


@router.get("/containers/{container_id}/stats")
async def container_stats(
    container_id: str = Path(...),
    _: str = Depends(verify_token),
):
    client = _client()
    try:
        c = client.containers.get(container_id)
        raw = c.stats(stream=False)
        # Calculate CPU %
        cpu_delta = raw["cpu_stats"]["cpu_usage"]["total_usage"] - \
                    raw["precpu_stats"]["cpu_usage"]["total_usage"]
        sys_delta = raw["cpu_stats"].get("system_cpu_usage", 0) - \
                    raw["precpu_stats"].get("system_cpu_usage", 0)
        cpus = len(raw["cpu_stats"]["cpu_usage"].get("percpu_usage") or [1])
        cpu_pct = (cpu_delta / sys_delta * cpus * 100.0) if sys_delta > 0 else 0

        mem = raw.get("memory_stats", {})
        mem_used = mem.get("usage", 0) - mem.get("stats", {}).get("cache", 0)
        mem_limit = mem.get("limit", 1)

        net_rx, net_tx = 0, 0
        for iface in raw.get("networks", {}).values():
            net_rx += iface.get("rx_bytes", 0)
            net_tx += iface.get("tx_bytes", 0)

        return {
            "id": container_id,
            "cpu_percent": round(cpu_pct, 2),
            "mem_used": mem_used,
            "mem_limit": mem_limit,
            "mem_percent": round(mem_used / mem_limit * 100, 2) if mem_limit else 0,
            "net_rx": net_rx,
            "net_tx": net_tx,
        }
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")


class ActionRequest(BaseModel):
    action: str  # start | stop | restart | pause | unpause | remove


@router.post("/containers/{container_id}/action")
async def container_action(
    container_id: str = Path(...),
    body: ActionRequest = ...,
    _: str = Depends(verify_token),
):
    allowed = {"start", "stop", "restart", "pause", "unpause", "remove"}
    if body.action not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown action '{body.action}'")

    client = _client()
    try:
        c = client.containers.get(container_id)
        if body.action == "start":
            c.start()
        elif body.action == "stop":
            c.stop(timeout=10)
        elif body.action == "restart":
            c.restart(timeout=10)
        elif body.action == "pause":
            c.pause()
        elif body.action == "unpause":
            c.unpause()
        elif body.action == "remove":
            c.remove(force=True)
        return {"ok": True, "action": body.action, "container": container_id}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.APIError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/images")
async def list_images(_: str = Depends(verify_token)):
    client = _client()
    images = client.images.list()
    return [
        {
            "id": img.short_id,
            "tags": img.tags,
            "size": img.attrs.get("Size", 0),
            "created": img.attrs.get("Created", ""),
        }
        for img in images
    ]


@router.get("/networks")
async def list_networks(_: str = Depends(verify_token)):
    client = _client()
    networks = client.networks.list()
    return [
        {
            "id": n.short_id,
            "name": n.name,
            "driver": n.attrs.get("Driver", ""),
            "scope": n.attrs.get("Scope", ""),
        }
        for n in networks
    ]
