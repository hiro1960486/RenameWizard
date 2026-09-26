# v0.5.0 統合記録とGitHub反映手順

## 統合方針

- 現行プロジェクトを基準にし、従来の `app/rename.py`、`app/undo.py`、Excel設定、PowerPoint UI資料と旧起動BATを残しました。
- GUIは参考実装から `app/main.py` と `app/models.py` を取り込み、ファイル操作の排他作成・ハッシュ確認はテスト可能な `app/operations.py` に切り出しました。
- ルートの起動スクリプトは `run_gui.py` としました。`app.py` と `app/` ディレクトリーはPythonのimport名が衝突するためです。
- ユーザー設定は `config/gui_settings.json` へ保存し、Git管理対象から外しています。
- 添付アイコンを各PNGサイズおよびマルチサイズICOへ変換しました。

## 変更・追加ファイル

- 追加: `app/main.py`, `app/models.py`, `app/operations.py`, `run_gui.py`, `run_app.bat`, `setup_dev.bat`, `build_exe.bat`, `requirements.txt`, `requirements-build.txt`, `assets/*`, `docs/*`, `tests/test_core.py`, `LICENSE`
- 更新: `.gitignore`, `README.md`
- 維持: `app/rename.py`, `app/undo.py`, `config/RenameConfig.xlsx`, `ui/RenameUI.pptm`, `ui/UI設計メモ.md`, `run_preview.bat`, `run_undo.bat`, `.gitkeep`各種
- 削除: 誤記ファイル `.gitignor`。正しい `.gitignore` に置換しました。

## ローカル確認

- `python -m unittest discover -s tests -v`: 14件成功
- `python -m compileall -q .`: 成功
- ICO: 16、24、32、48、64、128、256 px の7サイズを確認
- 実行環境: Python 3.12.14、pip 26.2.1、Pillow 12.3.0、openpyxl 3.1.5
- 利用者確認: GUIとUndoのWindows実機確認が完了し、重大不具合は見つかっていません。
- 未確認: この作業環境にPySide6とPyInstallerがないため、こちらでのEXEビルドは実行できていません。Windows EXEの起動とアイコン表示も残っています。

## GitHubでの反映

1. 実際のGitHub作業フォルダーで `git status --short --branch` と `git log --oneline -5` を確認します。
2. 初回コミット前の既存コードは、秘密情報・実行ログ・`output/`・`target/`・生成物を確認し除外したうえで `v0.4.0 Existing RenameWizard baseline` としてコミットします。
3. `git switch -c feature/v0.5-multi-job-ui` を実行します。
4. 本統合内容を差分として反映し、Windowsで `setup_dev.bat`、テスト、`run_app.bat`、`build_exe.bat` を確認します。
5. 差分を確認し、`v0.5.0 Add multi-job beginner-friendly GUI` でコミットします。
6. 動作確認後に `v0.5.0` タグを作成し、EXEとSHA256をリリース添付候補にします。

この配布用作業フォルダーには元アーカイブの `.git` 履歴を持ち込んでいません。既存GitHub作業フォルダーへ統合するときは、既存履歴を維持してください。

## v0.5.1へ繰り越した改善

利用者の確認に基づき、アクセントカラー、サンプルファイル名、プレースホルダー、ツールチップ、状態バー改善、PowerPoint UIとのデザイン調整は `docs/v0.5.1_backlog.md` に分けました。v0.5.0の機能修正には含めません。
