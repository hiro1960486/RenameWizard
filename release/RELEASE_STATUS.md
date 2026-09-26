# RenameWizard v0.5.0 配布状態

ソース一式、README、LICENSE、テスト結果、指定されたアイコン2点を配置しています。

Windows用EXEとSHA256ファイルは未生成です。作業環境はLinux x86_64で、Windows向けPyInstaller実行環境（PySide6、PyInstaller）がありません。Windows用EXEをLinux上で代替生成したり、SHA256を仮作成したりしていません。

Windows環境で `build_exe.bat` を実行すると、EXE、SHA256、README、LICENSE、テスト結果、アイコンが `release/` に揃うようにしています。EXEを実機で起動し、GUIとアイコンを確認した後に配布してください。

## 配布フォルダー内容

- `RenameWizard_v0.5.0_Windows_x64.exe` — Windows Build後に生成
- `RenameWizard_v0.5.0_Windows_x64.exe.sha256.txt` — Buildスクリプトが生成
- `README.md`
- `LICENSE`
- `test_report.md`
- `assets/renamewizard_icon.png`
- `assets/renamewizard_icon.ico`
