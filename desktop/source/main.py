from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading

# All model assets are local; keep optional libraries offline as well.
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'


def main():
    parser = argparse.ArgumentParser(description='MixSnip local formula OCR desktop app')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--recognize', type=Path, help='Recognize an image without showing the GUI')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--background', action='store_true', help='Start quietly in the system tray')
    parser.add_argument('--autostart', choices=['enable','disable'], help='Configure current-user Windows logon startup')
    args = parser.parse_args()
    if args.autostart:
        from mixsnip.startup import set_enabled
        set_enabled(args.autostart=='enable')
        return 0
    from mixsnip.core import app_root, asset_root, MixTeX
    data_dir = args.data_dir or app_root()/'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data_dir/'app.log', level=logging.INFO, encoding='utf-8',
                        format='%(asctime)s %(levelname)s %(message)s')
    if args.recognize:
        from PIL import Image
        from mixsnip.engines import make_engine
        settings_path = data_dir/'settings.json'
        settings = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
        engine = make_engine(settings)
        with Image.open(args.recognize) as image:
            try:
                text, status, elapsed, note = engine.recognize(image, threading.Event())
            finally:
                if hasattr(engine, 'close'):
                    engine.close()
        result = json.dumps(dict(latex=text,status=status,elapsed=elapsed,note=note), ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(result, encoding='utf-8')
        elif sys.stdout:
            print(result)
        return 0 if status=='done' else 1
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
    from mixsnip.snipview import SnipWindow as MainWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName('MixSnip')
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(data_dir/'app.lock'))
    if not lock.tryLock(100):
        if not args.background:
            QMessageBox.information(None,'MixSnip 已运行','请点击系统托盘中的 MixSnip 图标，或使用已设置的截图快捷键。')
        return 0
    app.setStyle('Fusion')
    app.setStyleSheet((asset_root()/'style.qss').read_text(encoding='utf-8'))
    window = MainWindow(data_dir)
    if not args.background or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
    result = app.exec()
    window.history.close()
    lock.unlock()
    return result


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        logging.exception('Application failed')
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f'启动失败：{error}\n请查看 data/app.log。', 'MixSnip', 0x10)
        raise
