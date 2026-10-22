"""Offline OCR backends. Paddle lives in an isolated, bundled Python process."""
from __future__ import annotations
import atexit
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

import numpy as np
from PIL import Image, ImageOps
from .core import MixTeX, app_root


def normalize_formula(image):
    image = ImageOps.exif_transpose(image)
    if image.mode == 'RGBA' or 'transparency' in image.info:
        layer = image.convert('RGBA')
        image = Image.new('RGBA', layer.size, 'white')
        image.alpha_composite(layer)
    image = image.convert('RGB')
    gray = np.asarray(image.convert('L'))
    border = np.concatenate([gray[0], gray[-1], gray[:, 0], gray[:, -1]])
    if np.median(border) < 128:
        image = ImageOps.invert(image)
    return ImageOps.autocontrast(image, cutoff=0)


def selected_config():
    path = app_root() / 'models' / 'selected.json'
    if path.is_file():
        config = json.loads(path.read_text(encoding='utf-8'))
        if config.get('size') in ('M', 'L'):
            return config
    return None


def make_engine(settings):
    config = selected_config()
    if settings.get('engine', 'formula' if config else 'mixtex') == 'formula' and config:
        return FormulaNet(config['size'], normalize=config.get('normalize', True))
    path = Path(settings.get('model_dir', 'onnx'))
    model = MixTeX(path if path.is_absolute() else app_root() / path)
    model.name = 'MixTeX'
    return model


class FormulaNet:
    def __init__(self, size, normalize=True, root=None, timeout=180):
        if size not in ('M', 'L'):
            raise ValueError('未知 FormulaNet 模型')
        self.name = 'PP-FormulaNet_plus-' + size
        self.root = Path(root) if root else app_root()
        self.normalize = normalize
        self.timeout = timeout
        self.process = None
        self.temp = None
        self.log = None
        atexit.register(self.close)

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if process.stdin:
                process.stdin.close()
        if self.log:
            self.log.close()
            self.log = None
        if self.temp:
            self.temp.cleanup()
            self.temp = None

    def _start(self):
        if self.process and self.process.poll() is None:
            return
        self.close()
        python = self.root / 'formula-runtime' / 'python.exe'
        worker = self.root / 'source' / 'formula_worker.py'
        model = self.root / 'models' / self.name
        for required in (python, worker, model / 'inference.pdiparams', model / 'inference.json', model / 'inference.yml'):
            if not required.is_file():
                raise FileNotFoundError(f'缺少本地识别组件：{required}\n请保留完整软件文件夹，或在设置中切换到 MixTeX。')
        self.temp = tempfile.TemporaryDirectory(prefix='mixsnip-formula-')
        self.log = (Path(self.temp.name) / 'worker.log').open('wb')
        env = os.environ.copy()
        for key in ('PYTHONHOME', 'PYTHONPATH'):
            env.pop(key, None)
        env.update(DISABLE_MODEL_SOURCE_CHECK='True', PADDLE_PDX_MODEL_SOURCE='BOS',
                   HF_HUB_OFFLINE='1', OMP_NUM_THREADS='4', PYTHONIOENCODING='utf-8')
        # PyInstaller sets a DLL directory inherited by children. Use the worker's own DLLs.
        reset_dll = sys.platform == 'win32' and getattr(sys, 'frozen', False)
        if reset_dll:
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            self.process = subprocess.Popen(
                [str(python), '-I', str(worker), '--model', str(model), '--name', self.name],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log,
                cwd=str(self.root), env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        finally:
            if reset_dll:
                ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)

    def recognize(self, image, cancel, progress=None):
        started = time.perf_counter()
        if cancel.is_set():
            return '', 'cancelled', 0.0, '已取消'
        prepared = normalize_formula(image) if self.normalize else image.convert('RGB')
        # Uniform crops have no recoverable formula. Do not let a generative decoder invent one.
        if np.ptp(np.asarray(prepared.convert('L'))) < 3:
            return '', 'empty', time.perf_counter()-started, '截图为空白，请重新框选公式'
        self._start()
        key = uuid.uuid4().hex
        source = Path(self.temp.name) / (key + '.png')
        target = Path(self.temp.name) / (key + '.json')
        prepared.save(source)
        try:
            self.process.stdin.write((json.dumps({'image':str(source), 'result':str(target)})+'\n').encode('utf-8'))
            self.process.stdin.flush()
            while not target.exists():
                if cancel.wait(0.05):
                    self.close()
                    return '', 'cancelled', time.perf_counter()-started, '已取消'
                if self.process.poll() is not None:
                    self.log.flush()
                    detail = (Path(self.temp.name)/'worker.log').read_text(encoding='utf-8',errors='replace')[-2000:]
                    self.close()
                    raise RuntimeError('本地 FormulaNet 进程退出，可重试或切换 MixTeX。\n'+detail)
                if time.perf_counter()-started > self.timeout:
                    self.close()
                    raise TimeoutError('本地识别超时，已停止，可缩小截图后重试。')
            result = json.loads(target.read_text(encoding='utf-8'))
            if 'error' in result:
                raise RuntimeError(result['error'])
            elapsed = time.perf_counter()-started
            text = result['latex'].strip()
            note = f'{self.name} · 本地 CPU · {elapsed:.1f} 秒'
            return text, 'done' if text else 'empty', elapsed, note
        finally:
            source.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
