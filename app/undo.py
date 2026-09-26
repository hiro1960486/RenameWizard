from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
LOGS_DIR = ROOT_DIR / "logs"
OUTPUT_DIR = ROOT_DIR / "output"

CONFIRM_WORD = "UNDO"


def read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    """UTF-8 BOM付き／なしのCSVを読み込む。"""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def get_value(row: dict[str, str], *names: str) -> str:
    """ログの列名に表記揺れがあっても値を取得する。"""
    normalized = {
        str(key).strip().replace(" ", "").replace("_", "").lower():
        (value or "").strip()
        for key, value in row.items()
        if key is not None
    }
    for name in names:
        key = name.strip().replace(" ", "").replace("_", "").lower()
        if key in normalized:
            return normalized[key]
    return ""


def latest_result_log() -> Path:
    """最新の通常実行ログを取得する。Undoログやpreview.csvは除外する。"""
    candidates = [
        p for p in LOGS_DIR.glob("result_*.csv")
        if p.is_file() and not p.name.startswith("undo_")
    ]
    if not candidates:
        raise FileNotFoundError("logsフォルダに result_*.csv がありません。")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_logged_path(value: str, base_dir: Path) -> Path:
    """ログ内の絶対パス／相対パス／ファイル名を安全にPathへ変換する。"""
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def is_inside(path: Path, parent: Path) -> bool:
    """pathがparent配下にあるか確認する。"""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def build_undo_plan(log_path: Path) -> list[dict[str, object]]:
    rows = read_csv_rows(log_path)
    plan: list[dict[str, object]] = []
    seen: set[Path] = set()

    for index, row in enumerate(rows, start=2):
        status = get_value(row, "状態", "status")
        if status and status.upper() not in {"OK", "SUCCESS", "完了"}:
            continue

        source_text = get_value(
            row, "変更前", "コピー元", "元ファイル", "source", "before"
        )
        destination_text = get_value(
            row, "変更後", "コピー先", "出力先", "destination", "after"
        )

        if not destination_text:
            plan.append({
                "status": "ERROR",
                "source": source_text,
                "destination": "",
                "reason": f"{index}行目: 変更後のパスを取得できません。",
            })
            continue

        source = resolve_logged_path(source_text, ROOT_DIR) if source_text else None
        destination = resolve_logged_path(destination_text, OUTPUT_DIR)

        reason = ""
        item_status = "OK"

        if destination in seen:
            item_status = "ERROR"
            reason = "同じコピー先がログ内に重複しています。"
        elif not is_inside(destination, OUTPUT_DIR):
            item_status = "ERROR"
            reason = "コピー先がoutputフォルダ外のため削除しません。"
        elif destination == OUTPUT_DIR.resolve():
            item_status = "ERROR"
            reason = "outputフォルダ自体は削除できません。"
        elif not destination.exists():
            item_status = "ERROR"
            reason = "コピー先ファイルが見つかりません。"
        elif not destination.is_file():
            item_status = "ERROR"
            reason = "コピー先が通常ファイルではありません。"
        elif source is not None and not source.exists():
            item_status = "ERROR"
            reason = "元ファイルが見つからないため、安全のため停止します。"

        seen.add(destination)
        plan.append({
            "status": item_status,
            "source": str(source) if source else source_text,
            "destination": str(destination),
            "reason": reason,
        })

    return plan


def write_undo_log(rows: list[dict[str, str]]) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"undo_{timestamp}_result.csv"
    fieldnames = ["状態", "元ファイル", "削除したコピー", "理由"]
    with log_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return log_path


def main() -> int:
    print("===== Undo 安全プレビュー（この時点では変更しません） =====")
    print("※ コピー方式専用です。targetの元ファイルは変更しません。\n")

    try:
        log_path = latest_result_log()
        plan = build_undo_plan(log_path)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"対象ログ: {log_path.name}\n")

    if not plan:
        print("[ERROR] Undo対象がありません。")
        return 1

    ok_count = 0
    error_count = 0
    for item in plan:
        status = str(item["status"])
        destination = Path(str(item["destination"])) if item["destination"] else None
        if status == "OK":
            ok_count += 1
            print(f"[OK] 削除予定: {destination.name if destination else ''}")
        else:
            error_count += 1
            print(f"[ERROR] {destination.name if destination else '(不明)'}")
            print(f"        理由: {item['reason']}")

    print("\n------------------------------")
    print(f"Undo可能 : {ok_count}件")
    print(f"エラー   : {error_count}件")

    if error_count:
        print("\nエラーがあるためUndoを実行しません。")
        return 1
    if ok_count == 0:
        print("\nUndoできるファイルがありません。")
        return 1

    print(f"\n実行する場合だけ半角大文字で {CONFIRM_WORD} と入力してください。")
    answer = input("> ").strip()
    if answer != CONFIRM_WORD:
        print("キャンセルしました。ファイルは変更していません。")
        return 0

    results: list[dict[str, str]] = []
    for item in plan:
        destination = Path(str(item["destination"]))
        try:
            destination.unlink()
            results.append({
                "状態": "OK",
                "元ファイル": str(item["source"]),
                "削除したコピー": str(destination),
                "理由": "コピー方式のUndoとして出力ファイルを削除",
            })
            print(f"[OK] 削除: {destination.name}")
        except Exception as exc:
            results.append({
                "状態": "ERROR",
                "元ファイル": str(item["source"]),
                "削除したコピー": str(destination),
                "理由": str(exc),
            })
            print(f"[ERROR] {destination.name}: {exc}")

    undo_log = write_undo_log(results)
    failed = sum(1 for row in results if row["状態"] == "ERROR")

    print("\nUndo処理が完了しました。")
    print(f"結果ログ: {undo_log.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nキャンセルしました。")
        raise SystemExit(130)
