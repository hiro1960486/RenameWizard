from datetime import datetime
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.models import RenameRule, apply_rule
from app.operations import (
    copy_without_overwrite, file_sha256, move_without_overwrite, undo_copy,
    undo_move, write_execution_log, write_undo_log,
)
from app.rename import build_new_name


class RenameRuleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 27, 10, 30)

    def test_plain_replacement_and_japanese_name(self):
        rule = RenameRule(find="写真", replace="画像")
        self.assertEqual(apply_rule(Path("写真1.jpg"), rule, 0, self.now), "画像1.jpg")

    def test_regex_is_optional(self):
        rule = RenameRule(find=r"\d+", replace="番号", regex=True)
        self.assertEqual(apply_rule(Path("資料123.docx"), rule, 0, self.now), "資料番号.docx")

    def test_date_prefix_suffix_and_formats(self):
        first = RenameRule(add_date=True, date_position="先頭", date_format="%Y-%m-%d")
        last = RenameRule(add_date=True, date_position="末尾")
        self.assertEqual(apply_rule(Path("report.xlsx"), first, 0, self.now), "2026-09-27_report.xlsx")
        self.assertEqual(apply_rule(Path("report.xlsx"), last, 0, self.now), "report_20260927.xlsx")

    def test_sequences_positions_and_padding(self):
        prefix = RenameRule(add_sequence=True, sequence_position="先頭", sequence_start=10, sequence_digits=3)
        suffix = RenameRule(add_sequence=True, sequence_position="末尾", sequence_start=1, sequence_digits=2)
        self.assertEqual(apply_rule(Path("a.pptx"), prefix, 0, self.now), "010_a.pptx")
        self.assertEqual(apply_rule(Path("a.pptx"), suffix, 1, self.now), "a_02.pptx")

    def test_date_sequence_and_other_transforms(self):
        rule = RenameRule(prefix="X", suffix="Y", add_date=True, add_sequence=True,
                          remove_spaces=True, case_mode="大文字")
        self.assertEqual(apply_rule(Path("my file.doc"), rule, 2, self.now), "20260927_XMYFILEY_003.doc")

    def test_windows_invalid_characters_are_replaced(self):
        rule = RenameRule(find="before", replace="bad/name")
        self.assertEqual(apply_rule(Path("before.txt"), rule, 0, self.now), "bad_name.txt")
        rule = RenameRule(prefix="a/b")
        self.assertEqual(apply_rule(Path("x.txt"), rule, 0, self.now), "a_bx.txt")
        self.assertEqual(apply_rule(Path("CON.txt"), RenameRule(), 0, self.now), "_CON.txt")

    def test_long_unicode_and_office_image_extensions_are_preserved(self):
        rule = RenameRule(suffix="_done")
        for ext in (".pptx", ".xlsx", ".docx", ".png", ".jpg"):
            name = "日本語" + "x" * 220 + ext
            self.assertTrue(apply_rule(Path(name), rule, 0, self.now).endswith("_done" + ext))

    def test_legacy_excel_engine_keeps_v04_date_rule(self):
        config = {"先頭文字": "", "末尾文字": "", "日付追加": True,
                  "日付形式": "%Y%m%d", "日付位置": "末尾"}
        class FixedDateTime:
            @staticmethod
            def now(): return self.now
        with patch("app.rename.datetime", FixedDateTime):
            self.assertEqual(build_new_name(Path("legacy.xlsm"), config, 0), "legacy_20260927.xlsm")


class FileOperationTests(unittest.TestCase):
    def test_copy_preserves_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source=root/"a.txt"; dest=root/"out.txt"
            source.write_text("original", encoding="utf-8")
            copy_without_overwrite(source, dest)
            self.assertEqual(source.read_text(encoding="utf-8"), "original")
            self.assertEqual(dest.read_text(encoding="utf-8"), "original")
            self.assertEqual(file_sha256(source), file_sha256(dest))
            dest.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError): copy_without_overwrite(source, dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), "keep")

    def test_move_restores_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source=root/"a.txt"; dest=root/"sub"/"a.txt"
            dest.parent.mkdir(); source.write_text("move", encoding="utf-8")
            move_without_overwrite(source, dest)
            self.assertFalse(source.exists()); self.assertEqual(dest.read_text(encoding="utf-8"), "move")
            restore=root/"restored.txt"
            move_without_overwrite(dest, restore)
            self.assertFalse(dest.exists()); self.assertEqual(restore.read_text(encoding="utf-8"), "move")

    def test_copy_undo_and_modified_copy_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); copied=root/"copy.docx"
            copied.write_text("test-data",encoding="utf-8")
            digest=file_sha256(copied)
            undo_copy(copied,digest)
            self.assertFalse(copied.exists())
            copied.write_text("changed",encoding="utf-8")
            with self.assertRaises(ValueError): undo_copy(copied,digest)
            self.assertTrue(copied.exists())

    def test_move_undo_refuses_to_overwrite_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); moved=root/"out"/"sheet.xlsx"; original=root/"sheet.xlsx"
            moved.parent.mkdir(); moved.write_text("moved",encoding="utf-8")
            original.write_text("keep",encoding="utf-8")
            with self.assertRaises(FileExistsError): undo_move(moved,original,file_sha256(moved))
            self.assertEqual(original.read_text(encoding="utf-8"),"keep")
            self.assertEqual(moved.read_text(encoding="utf-8"),"moved")

    def test_excel_compatible_execution_and_undo_csv_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); run=root/"result.csv"; undo=root/"undo.csv"
            row={"状態":"OK","作業名":"テスト作業","実行日時":"2026-09-27T10:00:00",
                 "変更前":"元.txt","変更後":"先.txt","処理方式":"コピー","結果":"成功","理由":"","出力SHA256":"abc"}
            write_execution_log(run,[row])
            self.assertTrue(run.read_bytes().startswith(b"\xef\xbb\xbf"))
            with run.open(encoding="utf-8-sig",newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["作業名"],"テスト作業")
            write_undo_log(undo,[{"状態":"OK","元ファイル":"元.txt","Undo対象":"先.txt","理由":"Undo完了"}])
            with undo.open(encoding="utf-8-sig",newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["状態"],"OK")

    def test_dummy_office_and_image_files_are_copied_and_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); output=root/"output"; output.mkdir()
            extensions=(".pptx", ".xlsx", ".docx", ".png", ".jpg")
            for index,ext in enumerate(extensions):
                source=root/f"dummy{index}{ext}"; source.write_bytes(b"harmless test data")
                copied=output/source.name
                copy_without_overwrite(source,copied)
                self.assertTrue(source.exists()); self.assertEqual(file_sha256(source),file_sha256(copied))
                undo_copy(copied,file_sha256(source)); self.assertTrue(source.exists())
                destination=output/f"moved{index}{ext}"
                move_without_overwrite(source,destination)
                undo_move(destination,source,file_sha256(destination))
                self.assertTrue(source.exists()); self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
