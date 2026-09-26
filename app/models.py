from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import re

INVALID_WINDOWS = r'[<>:"/\\|?*]'

@dataclass
class RenameRule:
    find: str = ""
    replace: str = ""
    regex: bool = False
    prefix: str = ""
    suffix: str = ""
    add_date: bool = False
    date_format: str = "%Y%m%d"
    date_position: str = "先頭"
    add_sequence: bool = False
    sequence_start: int = 1
    sequence_digits: int = 3
    sequence_position: str = "末尾"
    remove_spaces: bool = False
    case_mode: str = "変更なし"
    invalid_replacement: str = "_"

@dataclass
class RenameJob:
    name: str
    sources: list[Path] = field(default_factory=list)
    output_dir: Path | None = None
    mode: str = "コピー"
    rule: RenameRule = field(default_factory=RenameRule)
    excluded_sources: list[Path] = field(default_factory=list)

@dataclass
class PreviewItem:
    source: Path
    destination: Path
    status: str
    reason: str = ""


def apply_rule(path: Path, rule: RenameRule, index: int, executed_at: datetime | None = None) -> str:
    executed_at = executed_at or datetime.now()
    stem, suffix = path.stem, path.suffix
    if rule.find:
        try:
            stem = re.sub(rule.find, rule.replace, stem) if rule.regex else stem.replace(rule.find, rule.replace)
        except re.error as exc:
            raise ValueError(f"正規表現が正しくありません: {exc}") from exc
    if rule.remove_spaces:
        stem = re.sub(r"\s+", "", stem)
    stem = f"{rule.prefix}{stem}{rule.suffix}"
    if rule.add_date:
        date_text = executed_at.strftime(rule.date_format or "%Y%m%d")
        stem = f"{date_text}_{stem}" if rule.date_position == "先頭" else f"{stem}_{date_text}"
    if rule.add_sequence:
        seq = str(rule.sequence_start + index).zfill(rule.sequence_digits)
        stem = f"{seq}_{stem}" if rule.sequence_position == "先頭" else f"{stem}_{seq}"
    if rule.case_mode == "大文字":
        stem = stem.upper()
    elif rule.case_mode == "小文字":
        stem = stem.lower()
    replacement = re.sub(INVALID_WINDOWS, "", rule.invalid_replacement or "_") or "_"
    stem = re.sub(INVALID_WINDOWS, replacement, stem).rstrip(" .")
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", stem):
        stem = "_" + stem
    if not stem:
        raise ValueError("変更後のファイル名が空です")
    return stem + suffix
