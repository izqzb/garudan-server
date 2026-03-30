"""File browser — sandboxed to FILE_ROOT."""
import mimetypes
import os
import shutil
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ..config import settings
from .auth import verify_token

router = APIRouter(prefix="/api/files", tags=["files"])

ROOT = Path(settings.file_root).resolve()


def _safe_path(rel: str) -> Path:
    """Resolve path and ensure it is inside ROOT."""
    target = (ROOT / rel.lstrip("/")).resolve()
    if not str(target).startswith(str(ROOT)):
        raise HTTPException(status_code=403, detail="Access denied: path escape attempt")
    return target


@router.get("/list")
async def list_directory(
    path: str = Query(default="/"),
    _: str = Depends(verify_token),
):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    entries = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            stat = entry.stat(follow_symlinks=False)
            entries.append({
                "name": entry.name,
                "path": "/" + str(entry.relative_to(ROOT)),
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else 0,
                "modified": stat.st_mtime,
                "mime": mimetypes.guess_type(entry.name)[0] or "application/octet-stream",
                "readable": os.access(entry, os.R_OK),
                "writable": os.access(entry, os.W_OK),
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "path": path,
        "root": str(ROOT),
        "entries": entries,
    }


@router.get("/download")
async def download_file(
    path: str = Query(...),
    _: str = Depends(verify_token),
):
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    mime, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        target,
        filename=target.name,
        media_type=mime or "application/octet-stream",
    )


@router.post("/upload")
async def upload_file(
    path: str = Query(default="/"),
    file: UploadFile = File(...),
    _: str = Depends(verify_token),
):
    target_dir = _safe_path(path)
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target must be a directory")

    dest = target_dir / file.filename
    max_bytes = settings.max_upload_mb * 1024 * 1024

    async with aiofiles.open(dest, "wb") as f:
        total = 0
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.max_upload_mb}MB limit",
                )
            await f.write(chunk)

    return {"ok": True, "path": "/" + str(dest.relative_to(ROOT)), "size": total}


@router.delete("/delete")
async def delete_entry(
    path: str = Query(...),
    _: str = Depends(verify_token),
):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == ROOT:
        raise HTTPException(status_code=403, detail="Cannot delete root")
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/mkdir")
async def make_directory(
    path: str = Query(...),
    name: str = Query(...),
    _: str = Depends(verify_token),
):
    parent = _safe_path(path)
    new_dir = parent / name
    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "path": "/" + str(new_dir.relative_to(ROOT))}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/rename")
async def rename_entry(
    path: str = Query(...),
    new_name: str = Query(...),
    _: str = Depends(verify_token),
):
    target = _safe_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    dest = target.parent / new_name
    _safe_path("/" + str(dest.relative_to(ROOT)))  # validate dest too
    try:
        target.rename(dest)
        return {"ok": True, "new_path": "/" + str(dest.relative_to(ROOT))}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")


@router.get("/read")
async def read_text_file(
    path: str = Query(...),
    _: str = Depends(verify_token),
):
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.stat().st_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large to read inline (>5MB)")
    try:
        async with aiofiles.open(target, "r", encoding="utf-8", errors="replace") as f:
            content = await f.read()
        return {"path": path, "content": content, "size": target.stat().st_size}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/write")
async def write_text_file(
    path: str = Query(...),
    content: str = "",
    _: str = Depends(verify_token),
):
    target = _safe_path(path)
    try:
        async with aiofiles.open(target, "w", encoding="utf-8") as f:
            await f.write(content)
        return {"ok": True, "size": target.stat().st_size}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
