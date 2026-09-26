from __future__ import annotations
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget
)

from app.models import RenameJob, RenameRule, PreviewItem, apply_rule
from app.operations import (
    copy_without_overwrite, file_sha256, move_without_overwrite, undo_copy,
    undo_move, write_execution_log, write_undo_log,
)

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
DEFAULT_OUTPUT = ROOT / "output"
SETTINGS_FILE = ROOT / "config" / "gui_settings.json"
ASSET_ROOT = Path(getattr(sys, "_MEIPASS", ROOT)) / "assets"
ICON = ASSET_ROOT / "renamewizard_icon.ico"


def open_in_explorer(path: Path) -> None:
    path = path if path.is_dir() else path.parent
    if sys.platform == "win32":
        os.startfile(str(path))
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class DropLineEdit(QLineEdit):
    def __init__(self, *args, path_kind="dir", **kwargs):
        super().__init__(*args, **kwargs)
        self.path_kind = path_kind
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        if paths:
            p = paths[0]
            if self.path_kind == "dir" and p.is_file(): p = p.parent
            self.setText(str(p))
            event.acceptProposedAction()

    def _menu(self, pos):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        copy_action = menu.addAction("パスをコピー")
        open_action = menu.addAction("対象フォルダーを開く")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == copy_action:
            QApplication.clipboard().setText(self.text())
        elif chosen == open_action and self.text():
            open_in_explorer(Path(self.text()))


class FileTable(QTableWidget):
    def __init__(self):
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(["使用", "元のファイル", "種類", "サイズ", "元のフォルダー"])
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.on_drop = None

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        if self.on_drop:
            self.on_drop([Path(u.toLocalFile()) for u in e.mimeData().urls()])
            e.acceptProposedAction()

    def _menu(self, pos):
        row = self.rowAt(pos.y())
        if row < 0: return
        path = Path(self.item(row, 1).data(Qt.UserRole))
        menu = QMenu(self)
        copy_name = menu.addAction("ファイル名をコピー")
        copy_path = menu.addAction("ファイルパスをコピー")
        open_parent = menu.addAction("親フォルダーを開く")
        remove = menu.addAction("リストから削除")
        include = menu.addAction("対象に含める")
        exclude = menu.addAction("対象から外す")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == copy_name: QApplication.clipboard().setText(path.name)
        elif chosen == copy_path: QApplication.clipboard().setText(str(path))
        elif chosen == open_parent: open_in_explorer(path)
        elif chosen == remove: self.removeRow(row)
        elif chosen == include: self.item(row, 0).setCheckState(Qt.Checked)
        elif chosen == exclude: self.item(row, 0).setCheckState(Qt.Unchecked)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RenameWizard v0.5.0")
        self.setMinimumSize(1180, 760)
        if ICON.exists(): self.setWindowIcon(QIcon(str(ICON)))
        self.jobs: list[RenameJob] = []
        self.current_job = -1
        self._build_ui()
        self.load_settings()
        self.include_subfolders.stateChanged.connect(lambda _v: self.save_settings())
        self.extensions.editingFinished.connect(self.save_settings)
        if not self.jobs:
            self.add_job()
        self.statusBar().showMessage("準備完了")

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QHBoxLayout(root)
        splitter = QSplitter(); main.addWidget(splitter)

        left = QWidget(); ll = QVBoxLayout(left)
        ll.addWidget(QLabel("リネーム作業"))
        self.job_list = QListWidget(); self.job_list.currentRowChanged.connect(self.load_job)
        ll.addWidget(self.job_list)
        row = QHBoxLayout()
        for text, fn in [("＋追加", self.add_job), ("複製", self.duplicate_job), ("削除", self.delete_job)]:
            b=QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        ll.addLayout(row)
        splitter.addWidget(left)

        tabs = QTabWidget(); splitter.addWidget(tabs); splitter.setStretchFactor(1, 1)
        tabs.addTab(self._source_tab(), "1. 対象ファイル")
        tabs.addTab(self._rule_tab(), "2. リネーム設定")
        tabs.addTab(self._preview_tab(), "3. プレビュー・実行")

    def _source_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        tools=QHBoxLayout()
        for text, fn in [("ファイルを追加", self.pick_files), ("フォルダーを追加", self.pick_folder), ("クリア", self.clear_sources)]:
            b=QPushButton(text); b.clicked.connect(fn); tools.addWidget(b)
        l.addLayout(tools)
        options=QHBoxLayout()
        self.include_subfolders=QCheckBox("サブフォルダーも含める")
        self.extensions=QLineEdit("*"); self.extensions.setPlaceholderText("例: .jpg,.png（* はすべて）")
        options.addWidget(self.include_subfolders); options.addWidget(QLabel("対象拡張子")); options.addWidget(self.extensions)
        l.addLayout(options)
        self.files=FileTable(); self.files.on_drop=self.add_paths; l.addWidget(self.files)
        self.files.itemChanged.connect(lambda _item: (self.save_job(), self.save_settings()))
        return w

    def _rule_tab(self):
        w=QWidget(); form=QFormLayout(w)
        self.job_name=QLineEdit(); self.job_name.textChanged.connect(self.rename_job); form.addRow("作業名", self.job_name)
        self.find=QLineEdit(); self.replace=QLineEdit(); form.addRow("置換前", self.find); form.addRow("置換後", self.replace)
        self.regex=QCheckBox("正規表現を使用（上級者向け）"); form.addRow("", self.regex)
        self.prefix=QLineEdit(); self.suffix=QLineEdit(); form.addRow("先頭に追加", self.prefix); form.addRow("末尾に追加", self.suffix)
        self.date_on=QCheckBox(); self.date_format=QComboBox(); self.date_format.setEditable(True); self.date_format.addItems(["%Y%m%d", "%Y-%m-%d", "%Y%m%d_%H%M"])
        self.date_pos=QComboBox(); self.date_pos.addItems(["先頭","末尾"])
        r=QHBoxLayout(); r.addWidget(self.date_on); r.addWidget(self.date_format); r.addWidget(self.date_pos); form.addRow("実行日を追加", r)
        self.seq_on=QCheckBox(); self.seq_start=QSpinBox(); self.seq_start.setRange(0,999999); self.seq_start.setValue(1)
        self.seq_digits=QSpinBox(); self.seq_digits.setRange(1,12); self.seq_digits.setValue(3)
        self.seq_pos=QComboBox(); self.seq_pos.addItems(["先頭","末尾"])
        r=QHBoxLayout(); r.addWidget(self.seq_on); r.addWidget(QLabel("開始")); r.addWidget(self.seq_start); r.addWidget(QLabel("桁")); r.addWidget(self.seq_digits); r.addWidget(self.seq_pos); form.addRow("連番を追加", r)
        self.remove_spaces=QCheckBox(); form.addRow("空白を削除", self.remove_spaces)
        self.case=QComboBox(); self.case.addItems(["変更なし","大文字","小文字"]); form.addRow("英字の大小", self.case)
        self.invalid=QLineEdit("_"); form.addRow("禁止文字の置換", self.invalid)
        auto=QPushButton("選択ファイルに合わせて設定を提案"); auto.clicked.connect(self.auto_adjust); form.addRow("", auto)
        return w

    def _preview_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        outrow=QHBoxLayout(); self.output=DropLineEdit(str(DEFAULT_OUTPUT), path_kind="dir")
        browse=QPushButton("出力先を選択"); browse.clicked.connect(self.pick_output)
        outrow.addWidget(QLabel("出力先")); outrow.addWidget(self.output); outrow.addWidget(browse); l.addLayout(outrow)
        self.output.editingFinished.connect(lambda: (self.save_job(), self.save_settings()))
        self.mode=QComboBox(); self.mode.addItems(["コピー","移動"]); l.addWidget(self.mode)
        buttons=QHBoxLayout()
        prev=QPushButton("プレビュー更新"); prev.clicked.connect(self.refresh_preview)
        run=QPushButton("リネームを実行"); run.clicked.connect(self.execute)
        undo=QPushButton("直前の処理をUndo"); undo.clicked.connect(self.undo)
        for b in (prev,run,undo): buttons.addWidget(b)
        l.addLayout(buttons)
        self.preview=QTableWidget(0,6); self.preview.setHorizontalHeaderLabels(["変更前","変更後","状態・理由","元の場所","出力先","方式"]); l.addWidget(self.preview)
        self.preview.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview.horizontalHeader().setStretchLastSection(True)
        return w

    def add_job(self):
        self.save_job()
        n=len(self.jobs)+1; job=RenameJob(f"作業 {n}", output_dir=DEFAULT_OUTPUT)
        self.jobs.append(job); self.job_list.addItem(job.name); self.job_list.setCurrentRow(len(self.jobs)-1)
        self.save_settings()

    def duplicate_job(self):
        if self.current_job < 0: return
        self.save_job(); src=self.jobs[self.current_job]
        clone=RenameJob(src.name+" コピー", list(src.sources), src.output_dir, src.mode, RenameRule(**asdict(src.rule)), list(src.excluded_sources))
        self.jobs.append(clone); self.job_list.addItem(clone.name); self.job_list.setCurrentRow(len(self.jobs)-1)
        self.save_settings()

    def delete_job(self):
        if len(self.jobs)<=1: return
        row=self.job_list.currentRow(); self.jobs.pop(row); self.job_list.takeItem(row); self.job_list.setCurrentRow(max(0,row-1))
        self.save_settings()

    def rename_job(self, text):
        if self.current_job>=0: self.jobs[self.current_job].name=text or f"作業 {self.current_job+1}"; self.job_list.item(self.current_job).setText(self.jobs[self.current_job].name)

    def save_job(self):
        if self.current_job<0 or self.current_job>=len(self.jobs): return
        j=self.jobs[self.current_job]
        j.sources=[Path(self.files.item(r,1).data(Qt.UserRole)) for r in range(self.files.rowCount())]
        j.excluded_sources=[Path(self.files.item(r,1).data(Qt.UserRole)) for r in range(self.files.rowCount()) if self.files.item(r,0).checkState()!=Qt.Checked]
        j.output_dir=Path(self.output.text()) if hasattr(self,'output') and self.output.text() else DEFAULT_OUTPUT
        j.mode=self.mode.currentText() if hasattr(self,'mode') else "コピー"
        r=j.rule
        for attr, widget in [('find',self.find),('replace',self.replace),('prefix',self.prefix),('suffix',self.suffix),('invalid_replacement',self.invalid)]: setattr(r,attr,widget.text())
        r.regex=self.regex.isChecked(); r.add_date=self.date_on.isChecked(); r.date_format=self.date_format.currentText(); r.date_position=self.date_pos.currentText()
        r.add_sequence=self.seq_on.isChecked(); r.sequence_start=self.seq_start.value(); r.sequence_digits=self.seq_digits.value(); r.sequence_position=self.seq_pos.currentText()
        r.remove_spaces=self.remove_spaces.isChecked(); r.case_mode=self.case.currentText()

    def save_settings(self):
        if not hasattr(self, "job_list"):
            return
        self.save_job()
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        jobs = [{"name": j.name, "sources": [str(p) for p in j.sources],
                 "excluded_sources": [str(p) for p in j.excluded_sources],
                 "output_dir": str(j.output_dir or DEFAULT_OUTPUT), "mode": j.mode,
                 "rule": asdict(j.rule)} for j in self.jobs]
        data = {"jobs": jobs, "include_subfolders": self.include_subfolders.isChecked(), "extensions": self.extensions.text()}
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_FILE)

    def load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.include_subfolders.setChecked(bool(data.get("include_subfolders", False)))
                self.extensions.setText(data.get("extensions", "*"))
                items = data.get("jobs", [])
            else:  # 読込中の旧版設定との互換
                items = data
            for item in items:
                sources = [Path(p) for p in item.get("sources", []) if Path(p).is_file()]
                excluded = [Path(p) for p in item.get("excluded_sources", []) if Path(p).is_file()]
                rule_data = item.get("rule", {})
                rule = RenameRule(**{k: v for k, v in rule_data.items() if k in RenameRule.__dataclass_fields__})
                self.jobs.append(RenameJob(item.get("name") or f"作業 {len(self.jobs)+1}", sources,
                                           Path(item.get("output_dir") or DEFAULT_OUTPUT),
                                           item.get("mode", "コピー"), rule, excluded))
                self.job_list.addItem(self.jobs[-1].name)
            if self.jobs:
                self.job_list.setCurrentRow(0)
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "設定の読込", f"保存設定を読み込めませんでした。初期設定で起動します。\n{exc}")

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def load_job(self,row):
        self.save_job(); self.current_job=row
        if row<0:return
        j=self.jobs[row]; self.job_name.setText(j.name); self._populate_files(j.sources, j.excluded_sources); self.output.setText(str(j.output_dir or DEFAULT_OUTPUT)); self.mode.setCurrentText(j.mode)
        r=j.rule; self.find.setText(r.find); self.replace.setText(r.replace); self.regex.setChecked(r.regex); self.prefix.setText(r.prefix); self.suffix.setText(r.suffix)
        self.date_on.setChecked(r.add_date); self.date_format.setCurrentText(r.date_format); self.date_pos.setCurrentText(r.date_position)
        self.seq_on.setChecked(r.add_sequence); self.seq_start.setValue(r.sequence_start); self.seq_digits.setValue(r.sequence_digits); self.seq_pos.setCurrentText(r.sequence_position)
        self.remove_spaces.setChecked(r.remove_spaces); self.case.setCurrentText(r.case_mode); self.invalid.setText(r.invalid_replacement)

    def pick_files(self):
        files,_=QFileDialog.getOpenFileNames(self,"対象ファイルを選択")
        self.add_paths([Path(p) for p in files])
    def pick_folder(self):
        p=QFileDialog.getExistingDirectory(self,"対象フォルダーを選択")
        if p:self.add_paths([Path(p)])
    def pick_output(self):
        p=QFileDialog.getExistingDirectory(self,"出力先を選択",self.output.text())
        if p:self.output.setText(p)
    def clear_sources(self):
        self.files.setRowCount(0)
        self.save_job(); self.save_settings()

    def add_paths(self, paths):
        existing={Path(self.files.item(r,1).data(Qt.UserRole)) for r in range(self.files.rowCount())}
        found=[]
        for p in paths:
            if p.is_dir():
                walker=p.rglob('*') if self.include_subfolders.isChecked() else p.iterdir()
                found.extend(x for x in walker if x.is_file())
            elif p.is_file(): found.append(p)
        ext_text=self.extensions.text().strip()
        allowed={x.strip().lower() if x.strip().startswith('.') else '.'+x.strip().lower() for x in ext_text.split(',') if x.strip() and x.strip()!='*'}
        if ext_text and ext_text!='*': found=[p for p in found if p.suffix.lower() in allowed]
        for p in found:
            if p not in existing: existing.add(p)
        self._populate_files(sorted(existing, key=lambda x:(x.name.lower(), str(x).lower())))
        self.save_job(); self.save_settings()

    def _populate_files(self, paths, excluded=()):
        self.files.blockSignals(True)
        self.files.setRowCount(0)
        for p in paths:
            row=self.files.rowCount(); self.files.insertRow(row)
            check=QTableWidgetItem(); check.setCheckState(Qt.Unchecked if p in excluded else Qt.Checked); self.files.setItem(row,0,check)
            name=QTableWidgetItem(p.name); name.setData(Qt.UserRole,str(p)); self.files.setItem(row,1,name)
            self.files.setItem(row,2,QTableWidgetItem(p.suffix.lower() or "ファイル"))
            try: size = p.stat().st_size
            except OSError: size = 0
            self.files.setItem(row,3,QTableWidgetItem(f"{size/1024/1024:.2f} MB"))
            self.files.setItem(row,4,QTableWidgetItem(str(p.parent)))
        self.files.blockSignals(False)

    def auto_adjust(self):
        paths=[Path(self.files.item(r,1).data(Qt.UserRole)) for r in range(self.files.rowCount()) if self.files.item(r,0).checkState()==Qt.Checked]
        if not paths:return
        stems=[p.stem for p in paths]
        import os as _os
        common=_os.path.commonprefix(stems)
        common_suffix=_os.path.commonprefix([stem[::-1] for stem in stems])[::-1] if stems else ""
        if common and len(common)>=3 and not self.find.text(): self.find.setText(common)
        if len(paths)>1: self.seq_on.setChecked(True); self.seq_digits.setValue(max(3,len(str(len(paths)))))
        self.output.setText(str(paths[0].parent / "renamed_output"))
        self.statusBar().showMessage(f"{len(paths)}件に合わせて設定を提案しました")
        from collections import Counter
        extensions=Counter(p.suffix.lower() for p in paths if p.suffix)
        numeric=sum(bool(re.search(r"\d+", stem)) for stem in stems)
        date_like=sum(bool(re.search(r"(?:19|20)\d{2}[-_.年]?(?:0?[1-9]|1[0-2])(?:[-_.月]?(?:0?[1-9]|[12]\d|3[01]))?", stem)) for stem in stems)
        repeated=len({p.stem.lower() for p in paths})<len(paths)
        notes=[f"対象ファイル: {len(paths)}件"]
        if common: notes.append(f"共通する先頭文字: {common}")
        if common_suffix: notes.append(f"共通する末尾文字: {common_suffix}")
        if extensions: notes.append("拡張子の傾向: "+", ".join(f"{ext} {n}件" for ext,n in extensions.most_common(4)))
        notes.append(f"数字を含む名前: {numeric}件 / 日付らしい部分: {date_like}件 / 空白あり: {sum(any(ch.isspace() for ch in stem) for stem in stems)}件")
        if repeated: notes.append("同じ名前のファイルが含まれます。プレビューで重複を確認してください。")
        notes.append("連番と出力先を提案しました。内容を確認して必要に応じて変更してください。")
        QMessageBox.information(self,"設定の提案","\n".join(notes))

    def current_rule(self): self.save_job(); return self.jobs[self.current_job].rule
    def make_plan(self):
        self.save_job(); j=self.jobs[self.current_job]; out=Path(self.output.text()); now=datetime.now(); plan=[]; seen=set()
        if not str(out).strip():
            return [PreviewItem(Path(""), Path(""), "ERROR", "出力先が指定されていません")]
        active_sources=[p for p in j.sources if p not in j.excluded_sources]
        for i,p in enumerate(active_sources):
            try:
                if out.exists() and not out.is_dir():
                    raise ValueError("出力先に指定した場所はフォルダーではありません")
                if not p.exists() or not p.is_file():
                    raise ValueError("対象ファイルが見つからないか、通常ファイルではありません")
                if not os.access(p, os.R_OK):
                    raise ValueError("対象ファイルを読み取れません")
                new=apply_rule(p,j.rule,i,now); dest=out/new
                status="OK"; reason=""
                key=str(dest).lower()
                if key in seen: status="ERROR"; reason="変更後の名前が重複"
                elif dest.exists(): status="ERROR"; reason="出力先に同名ファイルあり"
                elif p.resolve()==dest.resolve(): status="ERROR"; reason="元と出力先が同じ"
                elif len(str(dest)) > 240: status="ERROR"; reason="出力先のパスが長すぎます"
                else:
                    parent=out
                    while not parent.exists() and parent.parent!=parent: parent=parent.parent
                    if parent.exists() and not os.access(parent, os.W_OK): status="ERROR"; reason="出力先へ書き込めません"
                seen.add(key)
            except Exception as exc:
                dest=out/p.name; status="ERROR"; reason=str(exc)
            plan.append(PreviewItem(p,dest,status,reason))
        return plan

    def refresh_preview(self):
        plan=self.make_plan(); self.preview.setRowCount(0)
        for p in plan:
            r=self.preview.rowCount(); self.preview.insertRow(r)
            for c,v in enumerate([p.source.name,p.destination.name,p.status if not p.reason else f"{p.status}: {p.reason}",str(p.source.parent),str(p.destination.parent),self.mode.currentText()]): self.preview.setItem(r,c,QTableWidgetItem(v))
        self.statusBar().showMessage(f"対象 {len(plan)}件 / 実行可能 {sum(x.status=='OK' for x in plan)}件 / エラー {sum(x.status!='OK' for x in plan)}件")
        return plan

    def execute(self):
        plan=self.refresh_preview()
        if not plan or any(p.status!='OK' for p in plan): QMessageBox.warning(self,"実行不可","エラーを解消してから実行してください。"); return
        out=Path(self.output.text())
        if not out.exists() and QMessageBox.question(self,"出力先の作成",f"出力先フォルダーがありません。作成しますか？\n{out}")!=QMessageBox.Yes:return
        if QMessageBox.question(self,"最終確認",f"対象: {len(plan)}件\n実行可能: {len(plan)}件\nエラー: 0件\n方式: {self.mode.currentText()}\n出力先: {out}\n\n実行しますか？")!=QMessageBox.Yes:return
        out.mkdir(parents=True,exist_ok=True); LOGS.mkdir(exist_ok=True)
        if not os.access(out, os.W_OK): QMessageBox.warning(self,"実行不可","出力先に書き込めません。"); return
        results=[]
        for p in plan:
            try:
                if p.destination.exists(): raise FileExistsError(f"出力先に同名ファイルがあります: {p.destination}")
                if self.mode.currentText()=="コピー": copy_without_overwrite(p.source,p.destination)
                else: move_without_overwrite(p.source,p.destination)
                results.append({"状態":"OK","作業名":self.jobs[self.current_job].name,"実行日時":datetime.now().isoformat(timespec="seconds"),"変更前":str(p.source),"変更後":str(p.destination),"処理方式":self.mode.currentText(),"結果":"成功","理由":"","出力SHA256":file_sha256(p.destination)})
            except Exception as exc: results.append({"状態":"ERROR","作業名":self.jobs[self.current_job].name,"実行日時":datetime.now().isoformat(timespec="seconds"),"変更前":str(p.source),"変更後":str(p.destination),"処理方式":self.mode.currentText(),"結果":"失敗","理由":str(exc)})
        log=LOGS/f"result_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
        write_execution_log(log, results)
        succeeded=sum(row["状態"]=="OK" for row in results); failed=len(results)-succeeded
        QMessageBox.information(self,"完了",f"成功: {succeeded}件 / 失敗: {failed}件\nログ: {log.name}")
        self.save_settings()

    def undo(self):
        logs=sorted(LOGS.glob('result_*.csv'), key=lambda p:p.stat().st_mtime, reverse=True)
        if not logs: QMessageBox.information(self,"Undo","Undo対象のログがありません。"); return
        with logs[0].open(encoding='utf-8-sig', newline='') as f:
            rows=list(csv.DictReader(f))
        rows=[row for row in rows if row.get('状態') == 'OK']
        if not rows:
            QMessageBox.warning(self,"Undo","Undoできる成功項目がありません。")
            return
        for row in rows:
            src, dst = Path(row['変更前']), Path(row['変更後'])
            mode = row.get('処理方式','コピー')
            if not dst.exists() or not dst.is_file() or (mode=='移動' and src.exists()):
                QMessageBox.warning(self,"Undo",f"安全確認に失敗しました。ファイルは変更していません。\n{dst}")
                return
            expected_hash=row.get('出力SHA256','').strip()
            if expected_hash and file_sha256(dst)!=expected_hash:
                QMessageBox.warning(self,"Undo",f"実行後にファイル内容が変わっています。安全のためUndoを止めました。\n{dst}")
                return
        names="\n".join(Path(row['変更後']).name for row in rows[:10])
        if len(rows)>10: names += f"\nほか {len(rows)-10}件"
        if QMessageBox.question(self,"Undo確認",f"直前の成功 {len(rows)}件を元に戻します。\n\n{names}\n\n続けますか？")!=QMessageBox.Yes:return
        errors=[]; undo_results=[]
        for row in rows:
            src=Path(row['変更前']); dst=Path(row['変更後']); mode=row.get('処理方式','コピー')
            expected_hash=row.get('出力SHA256','').strip()
            try:
                if mode=='コピー': undo_copy(dst, expected_hash)
                elif mode=='移動': undo_move(dst,src,expected_hash)
                undo_results.append({"状態":"OK","元ファイル":str(src),"Undo対象":str(dst),"理由":"Undo完了"})
            except Exception as exc:
                errors.append(str(exc))
                undo_results.append({"状態":"ERROR","元ファイル":str(src),"Undo対象":str(dst),"理由":str(exc)})
        undo_log=LOGS/f"undo_{datetime.now():%Y%m%d_%H%M%S_%f}_result.csv"
        write_undo_log(undo_log, undo_results)
        if not errors:
            logs[0].rename(logs[0].with_name("undone_"+logs[0].name))
        QMessageBox.information(self,"Undo完了",("Undoが完了しました。" if not errors else "一部失敗:\n"+'\n'.join(errors))+f"\nUndoログ: {undo_log.name}")


def main():
    app=QApplication(sys.argv); app.setApplicationName("RenameWizard")
    if ICON.exists(): app.setWindowIcon(QIcon(str(ICON)))
    w=MainWindow(); w.show(); return app.exec()

if __name__=='__main__': raise SystemExit(main())
