"""Local recognition adapted from RQLuo/MixTeX-Latex-OCR (AGPL-3.0).

Uses the original v3.2.4 weights and greedy ONNX decoding. No network calls.
See ../licenses in the distribution for upstream attribution and terms.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from threading import Event

import numpy as np
from PIL import Image, ImageOps


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def asset_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[1] / "assets"


def strip_math(text: str) -> str:
    """Remove one complete outer math wrapper, never inner/multiple equations."""
    text = text.strip()
    for left, right in [(r"\[", r"\]"), (r"\(", r"\)"), ("$$", "$$"), ("$", "$")]:
        if text.startswith(left) and text.endswith(right) and len(text) >= len(left) + len(right):
            inner = text[len(left):-len(right)]
            if left not in inner and right not in inner:
                return inner.strip()
    return text


def copy_text(text: str, mode: str) -> str:
    text = text.strip()
    if mode == "original":
        return text
    bare = strip_math(text)
    # Never wrap mixed prose/multiple delimited equations in an extra math block.
    if re.search(r"(?<!\\)\$|\\[\[\]()]", bare):
        return text
    if mode == "inline":
        return f"${bare}$" if bare else ""
    if mode == "display":
        return "$$\n" + bare + "\n$$" if bare else ""
    return bare


class History:
    def __init__(self, directory: Path):
        self.directory = directory
        (directory / "images").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "history.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS snips (
            id TEXT PRIMARY KEY, created TEXT NOT NULL, image TEXT NOT NULL,
            latex TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
            elapsed REAL NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '')""")
        self.db.execute("UPDATE snips SET status='interrupted', note='上次识别被中断，可重新识别' WHERE status='running'")
        self.db.commit()

    def add(self, image: Image.Image) -> str:
        key = uuid.uuid4().hex
        name = f"images/{key}.png"
        image.save(self.directory / name)
        self.db.execute("INSERT INTO snips(id,created,image,status) VALUES(?,?,?,'running')",
                        (key, time.strftime("%Y-%m-%d %H:%M:%S"), name))
        self.db.commit()
        return key

    def get(self, key: str):
        return self.db.execute("SELECT * FROM snips WHERE id=?", (key,)).fetchone()

    def list(self, query=""):
        return self.db.execute("SELECT * FROM snips WHERE latex LIKE ? OR created LIKE ? ORDER BY created DESC, rowid DESC",
                               (f"%{query}%", f"%{query}%")).fetchall()

    def result(self, key, text, status, elapsed, note=""):
        self.db.execute("UPDATE snips SET latex=?,status=?,elapsed=?,note=? WHERE id=?",
                        (text, status, elapsed, note, key))
        self.db.commit()

    def edit(self, key, text):
        self.db.execute("UPDATE snips SET latex=? WHERE id=?", (text, key))
        self.db.commit()

    def delete(self, key):
        row = self.get(key)
        if row:
            self.db.execute("DELETE FROM snips WHERE id=?", (key,))
            self.db.commit()
            (self.directory / row["image"]).unlink(missing_ok=True)

    def close(self):
        self.db.close()


def prepare_image(image: Image.Image, size=(448, 448)) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode == "RGBA" or "transparency" in image.info:
        layer = image.convert("RGBA")
        image = Image.new("RGBA", layer.size, "white")
        image.alpha_composite(layer)
    image = image.convert("RGB")
    if max(image.size) < 1:
        raise ValueError("图片尺寸无效")
    if image.width > size[0] or image.height > size[1]:
        scale = min(size[0] / image.width, size[1] / image.height)
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "white")
    canvas.paste(image, ((size[0]-image.width)//2, (size[1]-image.height)//2))
    return canvas


class MixTeX:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.encoder = None

    def load(self):
        if self.encoder is not None:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer
        required = ["encoder_model.onnx", "decoder_model_merged.onnx", "tokenizer.json", "preprocessor_config.json", "config.json"]
        missing = [name for name in required if not (self.model_dir / name).is_file()]
        if missing:
            raise FileNotFoundError("缺少 MixTeX 模型文件：" + ", ".join(missing) + "\n请在设置中选择完整的 onnx 文件夹。")
        config = json.loads((self.model_dir / "config.json").read_text(encoding="utf-8"))
        self.processor = json.loads((self.model_dir / "preprocessor_config.json").read_text(encoding="utf-8"))
        self.tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        self.eos = self.tokenizer.token_to_id("</s>")
        self.start = self.tokenizer.encode("<s>").ids
        self.heads = config["decoder"]["n_head"]
        self.head_size = config["decoder"]["n_embd"] // self.heads
        self.max_length = min(512, config["decoder"]["n_positions"] - len(self.start))
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 2)
        options.log_severity_level = 3
        encoder = ort.InferenceSession(str(self.model_dir / "encoder_model.onnx"), options, providers=["CPUExecutionProvider"])
        self.decoder = ort.InferenceSession(str(self.model_dir / "decoder_model_merged.onnx"), options, providers=["CPUExecutionProvider"])
        self.cache_names = [item.name for item in self.decoder.get_inputs() if item.name.startswith("past_key_values.")]
        self.output_names = [item.name for item in self.decoder.get_outputs()]
        self.encoder = encoder

    def recognize(self, image, cancel: Event, progress=None):
        started = time.perf_counter()
        self.load()
        if cancel.is_set():
            return "", "cancelled", time.perf_counter()-started, "已取消"
        size = self.processor.get("size", {"height": 448, "width": 448})
        canvas = prepare_image(image, (size["width"], size["height"]))
        pixels = np.asarray(canvas, dtype=np.float32)
        pixels *= np.float32(self.processor.get("rescale_factor", 1/255))
        mean = np.asarray(self.processor.get("image_mean", [0.5]*3), dtype=np.float32)
        std = np.asarray(self.processor.get("image_std", [0.5]*3), dtype=np.float32)
        pixels = ((pixels-mean)/std).transpose(2, 0, 1)[None, ...]
        hidden = self.encoder.run(None, {"pixel_values": pixels})[0]
        inputs = {"input_ids": np.array([self.start], dtype=np.int64),
                  "encoder_hidden_states": hidden, "use_cache_branch": np.array([True], dtype=bool)}
        inputs.update({name: np.zeros((1, self.heads, 0, self.head_size), dtype=np.float32) for name in self.cache_names})
        ids, text, status, note = [], "", "truncated", "达到模型长度上限，请缩小截图区域后重试"
        for step in range(self.max_length):
            if cancel.is_set():
                status, note = "cancelled", "识别已取消，保留部分结果"
                break
            outputs = self.decoder.run(None, inputs)
            token = int(np.argmax(outputs[0][0, -1]))
            if token == self.eos:
                status, note = "done", ""
                break
            ids.append(token)
            # Decode the complete sequence to preserve multi-token UTF-8 characters.
            text = self.tokenizer.decode(ids, skip_special_tokens=True)
            if progress and step % 5 == 0:
                progress(text)
            if len(ids) >= 24 and any(ids[-n:]*6 == ids[-6*n:] for n in range(1, min(17, len(ids)//6+1))):
                status, note = "truncated", "检测到重复输出，请缩小截图区域或提高图片清晰度"
                break
            inputs["input_ids"] = np.array([[token]], dtype=np.int64)
            for index, name in enumerate(self.cache_names):
                output_name = name.replace("past_key_values", "present")
                out_index = self.output_names.index(output_name) if output_name in self.output_names else index+1
                inputs[name] = outputs[out_index]
        if status == "done" and not text.strip():
            status, note = "empty", "未识别出内容，请框选更清晰的公式"
        return text.strip(), status, time.perf_counter()-started, note
