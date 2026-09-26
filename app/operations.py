"""Filesystem operations shared by the GUI and its safety tests."""
from __future__ import annotations

import hashlib
import csv
import os
import shutil
import stat
from pathlib import Path


def _unlink_writable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    except OSError:
        pass
    path.unlink()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_without_overwrite(source: Path, destination: Path) -> None:
    """Create a destination exclusively so an existing file is never replaced."""
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, destination)
    except Exception:
        try:
            if destination.exists(): _unlink_writable(destination)
        finally:
            raise


def move_without_overwrite(source: Path, destination: Path) -> None:
    """Move across volumes without replacing an existing destination."""
    copy_without_overwrite(source, destination)
    try:
        _unlink_writable(source)
    except Exception:
        if destination.exists(): _unlink_writable(destination)
        raise


def undo_copy(destination: Path, expected_sha256: str = "") -> None:
    if not destination.is_file():
        raise FileNotFoundError(f"Undo対象が見つかりません: {destination}")
    if expected_sha256 and file_sha256(destination) != expected_sha256:
        raise ValueError(f"実行後に内容が変更されています: {destination}")
    _unlink_writable(destination)


def undo_move(destination: Path, source: Path, expected_sha256: str = "") -> None:
    if not destination.is_file():
        raise FileNotFoundError(f"Undo対象が見つかりません: {destination}")
    if source.exists():
        raise FileExistsError(f"元の場所に同名ファイルがあります: {source}")
    if expected_sha256 and file_sha256(destination) != expected_sha256:
        raise ValueError(f"実行後に内容が変更されています: {destination}")
    move_without_overwrite(destination, source)


def write_execution_log(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["状態", "作業名", "実行日時", "変更前", "変更後", "処理方式", "結果", "理由", "出力SHA256"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_undo_log(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["状態", "元ファイル", "Undo対象", "理由"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
