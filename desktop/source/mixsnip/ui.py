from __future__ import annotations

import ctypes
from ctypes import wintypes
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QSize, QBuffer, QIODevice
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPainter, QPixmap, QKeySequence, QShortcut, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QLineEdit,
    QPlainTextEdit, QListWidget, QListWidgetItem, QHBoxLayout, QVBoxLayout,
    QSplitter, QComboBox, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
    QMessageBox, QSystemTrayIcon, QMenu, QProgressBar, QFormLayout,
    QSizePolicy,
)
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

from .core import History, MixTeX, app_root, asset_root, copy_text
from .engines import make_engine, selected_config
from .capture import CaptureController


def pil_from_qimage(image: QImage) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    rgba = Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')
    opaque = Image.new('RGBA', rgba.size, 'white')
    opaque.alpha_composite(rgba)
    return opaque.convert('RGB')


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#3275ef'))
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(Qt.GlobalColor.white)
    painter.setFont(QFont('Segoe UI', 32, QFont.Weight.DemiBold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, '∑')
    painter.end()
    return QIcon(pixmap)


class OfflineOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() not in ('file', 'data', 'about', 'qrc'):
            info.block(True)


class OCRWorker(QThread):
    partial = Signal(str)
    completed = Signal(str, str, float, str)

    def __init__(self, engine, image, parent=None):
        super().__init__(parent)
        self.engine, self.image = engine, image
        self.cancelled = threading.Event()

    def run(self):
        try:
            result = self.engine.recognize(self.image, self.cancelled, self.partial.emit)
            self.completed.emit(*result)
        except Exception as error:
            logging.exception('Recognition failed')
            self.completed.emit('', 'error', 0, str(error))


class ImageLabel(QLabel):
    def __init__(self):
        super().__init__('点击「截图」或粘贴图片\n也可以把图片拖到这里')
        self.setObjectName('SourceImage')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.original = QPixmap()

    def set_image(self, path):
        self.original = QPixmap(str(path)) if path else QPixmap()
        self.refresh()

    def refresh(self):
        if self.original.isNull():
            self.clear()
            self.setText('点击「截图」或粘贴图片\n也可以把图片拖到这里')
        else:
            self.setPixmap(self.original.scaled(max(1,min(self.width()-32,self.original.width())), max(1,min(self.height()-28,self.original.height())),
                           Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


class SettingsDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.setWindowTitle('设置 · MixSnip')
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        form = QFormLayout()
        form.setVerticalSpacing(18)
        self.engine_choice = QComboBox()
        config = selected_config()
        if config:
            self.engine_choice.addItem('PP-FormulaNet_plus-'+config['size']+'（本地）', 'formula')
        self.engine_choice.addItem('MixTeX（本地）', 'mixtex')
        self.engine_choice.setCurrentIndex(max(0, self.engine_choice.findData(settings.get('engine','formula' if config else 'mixtex'))))
        form.addRow('识别模型', self.engine_choice)
        self.hotkey = QComboBox()
        self.hotkey.addItems(['Ctrl+Alt+M', 'Ctrl+Shift+M', 'Ctrl+Alt+S'])
        self.hotkey.setCurrentText(settings['hotkey'])
        form.addRow('全局截图快捷键', self.hotkey)
        self.auto = QCheckBox('识别完成后，自动复制到剪贴板')
        self.auto.setChecked(settings['auto_copy'])
        form.addRow('', self.auto)
        self.tray = QCheckBox('关闭窗口时继续在托盘运行')
        self.tray.setChecked(settings['close_to_tray'])
        form.addRow('', self.tray)
        self.autostart = QCheckBox('开机自启动（登录 Windows 后在托盘运行）')
        self.autostart.setChecked(settings.get('autostart',False))
        self.autostart.setEnabled(sys.platform=='win32')
        form.addRow('', self.autostart)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.model = QLineEdit(str(settings['model_dir']))
        choose = QPushButton('选择')
        choose.clicked.connect(self.browse)
        h.addWidget(self.model, 1)
        h.addWidget(choose)
        form.addRow('MixTeX 模型目录', row)
        layout.addLayout(form)
        tip = QLabel('模型均在本地运行。FormulaNet 会自动将深色截图转为白底；首次加载较慢，后续截图复用模型。截图与识别结果保存在 data 目录。')
        tip.setWordWrap(True)
        tip.setObjectName('Muted')
        layout.addWidget(tip)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, '选择 MixTeX onnx 文件夹', self.model.text())
        if path:
            self.model.setText(path)

    def validate(self):
        path = Path(self.model.text()).expanduser()
        if self.engine_choice.currentData() == 'mixtex' and not all((path / name).is_file() for name in ('encoder_model.onnx', 'decoder_model_merged.onnx', 'tokenizer.json')):
            QMessageBox.warning(self, '模型目录不完整', '请选择包含编码器、解码器和 tokenizer.json 的 onnx 文件夹。')
            return
        self.accept()


class MainWindow(QMainWindow):
    HOTKEY_ID = 0x4D58

    def __init__(self, data_dir=None):
        super().__init__()
        self.setWindowTitle('MixSnip · 本地公式识别')
        self.setWindowIcon(app_icon())
        self.resize(1020, 820)
        self.setMinimumSize(830, 690)
        self.setAcceptDrops(True)
        self.data_dir = Path(data_dir) if data_dir else app_root() / 'data'
        self.history = History(self.data_dir)
        self.settings_path = self.data_dir / 'settings.json'
        self.settings = {'hotkey':'Ctrl+Alt+M','auto_copy':True,'close_to_tray':True,'model_dir':'onnx','copy_mode':'bare'}
        if self.settings_path.exists():
            try:
                self.settings.update(json.loads(self.settings_path.read_text(encoding='utf-8')))
            except (ValueError, OSError):
                logging.exception('Cannot read settings; using defaults')
        self.engine = make_engine(self.settings)
        self.current_id = None
        self.busy = False
        self.worker = None
        self.quitting = False
        self.preview_ready = False
        self.hotkey_registered = False
        self.capture_pending = False
        self.capture = CaptureController(self)
        self.capture.captured.connect(self.on_capture)
        self.capture.cancelled.connect(self.capture_cancelled)
        self.edit_timer = QTimer(self)
        self.edit_timer.setSingleShot(True)
        self.edit_timer.setInterval(350)
        self.edit_timer.timeout.connect(self.save_and_preview)
        self.build_ui()
        self.build_tray()
        self.refresh_history()
        rows = self.history.list()
        if rows:
            self.select(rows[0]['id'])
        QShortcut(QKeySequence('Ctrl+Shift+V'), self, activated=self.paste_image)
        QShortcut(QKeySequence('Ctrl+O'), self, activated=self.import_image)
        QShortcut(QKeySequence('Ctrl+Shift+C'), self, activated=self.copy_latex)
        QShortcut(QKeySequence('Ctrl+Q'), self, activated=self.quit_app)
        self.statusBar().showMessage('本地识别 · 首次识别需要加载模型')
        QTimer.singleShot(200, self.register_hotkey)

    def model_path(self):
        path = Path(self.settings['model_dir'])
        return path if path.is_absolute() else app_root()/path

    def button(self, text, callback, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName('Primary')
        button.clicked.connect(callback)
        return button

    def label(self, text, name=None):
        label = QLabel(text)
        if name:
            label.setObjectName(name)
        return label

    def build_ui(self):
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame()
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(245)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 24, 18, 16)
        side.setSpacing(12)
        side.addWidget(self.label('∑  MixSnip', 'Brand'))
        side.addWidget(self.label('POWERED BY MIXTEX', 'Subtitle'))
        side.addSpacing(12)
        self.snip_button = self.button('＋  截图', self.start_capture, True)
        self.snip_button.setMinimumHeight(42)
        side.addWidget(self.snip_button)
        self.hotkey_label = self.label(self.settings['hotkey'], 'Muted')
        self.hotkey_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(self.hotkey_label)
        side.addSpacing(14)
        side.addWidget(self.label('截图历史', 'Section'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索公式或日期')
        self.search.textChanged.connect(self.refresh_history)
        side.addWidget(self.search)
        self.history_list = QListWidget()
        self.history_list.setIconSize(QSize(72, 44))
        self.history_list.currentItemChanged.connect(self.history_changed)
        side.addWidget(self.history_list, 1)
        self.history_count = self.label('0 条记录', 'Muted')
        side.addWidget(self.history_count)
        self.settings_button = self.button('设置', self.open_settings)
        side.addWidget(self.settings_button)
        info = self.button('关于 MixSnip', self.about)
        info.setObjectName('Quiet')
        side.addWidget(info)
        outer.addWidget(sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(26, 24, 26, 16)
        main.setSpacing(13)
        heading = QHBoxLayout()
        heading.addWidget(self.label('公式识别', 'Heading'))
        heading.addStretch()
        heading.addWidget(self.label('●  本地离线', 'Badge'))
        main.addLayout(heading)
        actions = QHBoxLayout()
        self.paste_button = self.button('粘贴图片', self.paste_image)
        self.paste_button.setToolTip('Ctrl+Shift+V')
        self.import_button = self.button('导入图片', self.import_image)
        self.import_button.setToolTip('Ctrl+O')
        self.retry_button = self.button('重新识别', self.retry)
        self.cancel_button = self.button('取消识别', self.cancel_recognition)
        self.cancel_button.hide()
        for button in [self.paste_button,self.import_button,self.retry_button,self.cancel_button]:
            actions.addWidget(button)
        actions.addStretch()
        self.delete_button = self.button('删除', self.delete_current)
        self.delete_button.setObjectName('Quiet')
        actions.addWidget(self.delete_button)
        main.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        main.addWidget(self.progress)

        source_title = QHBoxLayout()
        source_title.addWidget(self.label('原始截图', 'Section'))
        source_title.addStretch()
        self.image_info = self.label('', 'Muted')
        source_title.addWidget(self.image_info)
        main.addLayout(source_title)
        self.image_label = ImageLabel()
        self.image_label.setMaximumHeight(195)
        main.addWidget(self.image_label)
        self.detail_label = self.label('框选单个公式或一小段文字，可获得更好的识别效果。', 'Muted')
        self.detail_label.setWordWrap(True)
        main.addWidget(self.detail_label)

        lower = QSplitter(Qt.Orientation.Vertical)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.label('公式预览', 'Section'))
        self.preview = QWebEngineView()
        self.interceptor = OfflineOnly(self.preview)
        self.preview.page().profile().setUrlRequestInterceptor(self.interceptor)
        self.preview.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.preview.loadFinished.connect(self.preview_loaded)
        self.preview.setUrl(QUrl.fromLocalFile(str(asset_root()/'preview.html')))
        preview_layout.addWidget(self.preview, 1)
        lower.addWidget(preview_panel)
        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.label('LaTeX', 'Section'))
        row.addStretch()
        row.addWidget(self.label('可直接编辑 · 自动保存', 'Muted'))
        editor_layout.addLayout(row)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('识别结果会显示在这里，也可输入 LaTeX 进行预览。')
        self.editor.textChanged.connect(lambda: self.edit_timer.start())
        self.editor.setMinimumHeight(100)
        editor_layout.addWidget(self.editor, 1)
        lower.addWidget(editor_panel)
        lower.setSizes([210, 170])
        lower.setChildrenCollapsible(False)
        main.addWidget(lower, 1)

        footer = QHBoxLayout()
        self.auto_copy = QCheckBox('自动复制')
        self.auto_copy.setChecked(self.settings['auto_copy'])
        self.auto_copy.toggled.connect(self.auto_changed)
        footer.addWidget(self.auto_copy)
        footer.addStretch()
        self.copy_mode = QComboBox()
        for title, value in [('LaTeX','bare'),('$ 行内公式 $','inline'),('$$ 独立公式 $$','display'),('保留原文','original')]:
            self.copy_mode.addItem(title, value)
        self.copy_mode.setCurrentIndex(max(0,self.copy_mode.findData(self.settings['copy_mode'])))
        self.copy_mode.currentIndexChanged.connect(self.mode_changed)
        footer.addWidget(self.copy_mode)
        self.copy_button = self.button('复制 LaTeX', self.copy_latex, True)
        self.copy_button.setToolTip('Ctrl+Shift+C')
        self.copy_button.setMinimumWidth(125)
        footer.addWidget(self.copy_button)
        main.addLayout(footer)
        outer.addLayout(main, 1)
        self.setCentralWidget(root)
        self.update_controls()

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('MixSnip · 本地公式识别')
        menu = QMenu()
        menu.addAction('截图', self.start_capture)
        menu.addAction('显示窗口', self.show_window)
        menu.addSeparator()
        menu.addAction('退出', self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def save_settings(self):
        temporary = self.settings_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.settings_path)

    def auto_changed(self, value):
        self.settings['auto_copy'] = value
        self.save_settings()

    def mode_changed(self):
        self.settings['copy_mode'] = self.copy_mode.currentData()
        self.save_settings()

    def refresh_history(self, *args):
        self.history_list.blockSignals(True)
        self.history_list.clear()
        rows = self.history.list(self.search.text())
        for row in rows:
            excerpt = ' '.join(row['latex'].split())[:30] or {'running':'识别中…','error':'识别失败','cancelled':'已取消','interrupted':'识别被中断'}.get(row['status'],'暂无结果')
            item = QListWidgetItem(f"{row['created'][5:16]}\n{excerpt}")
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setToolTip(row['latex'][:500] or row['note'])
            item.setIcon(QIcon(str(self.data_dir/row['image'])))
            item.setSizeHint(QSize(200, 72))
            self.history_list.addItem(item)
            if row['id'] == self.current_id:
                self.history_list.setCurrentItem(item)
        self.history_count.setText(f'{len(rows)} 条记录')
        self.history_list.blockSignals(False)

    def history_changed(self, item, previous):
        if item and not self.busy:
            self.select(item.data(Qt.ItemDataRole.UserRole))

    def select(self, key):
        self.save_and_preview()
        row = self.history.get(key)
        if row is None:
            return
        self.current_id = key
        self.image_label.set_image(self.data_dir/row['image'])
        pix = self.image_label.original
        self.image_info.setText(f'{pix.width()} × {pix.height()} px')
        self.set_editor(row['latex'])
        self.detail_label.setText(row['note'] or f"{row['created']}  ·  MixTeX  ·  {row['elapsed']:.1f} 秒")
        self.refresh_history()
        self.update_controls()

    def set_editor(self, text):
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self.render_preview()

    def save_and_preview(self):
        self.edit_timer.stop()
        if self.current_id and not self.busy:
            self.history.edit(self.current_id, self.editor.toPlainText())
        self.render_preview()
        self.copy_button.setEnabled(bool(self.editor.toPlainText().strip()) and not self.busy)

    def preview_loaded(self, ok):
        self.preview_ready = ok
        if ok:
            self.render_preview()
        else:
            self.statusBar().showMessage('预览资源加载失败，请检查 assets 文件夹')

    def render_preview(self):
        if self.preview_ready:
            text = json.dumps(self.editor.toPlainText(), ensure_ascii=True)
            self.preview.page().runJavaScript(f'window.renderLatex({text});')

    def update_controls(self):
        for widget in [self.snip_button,self.paste_button,self.import_button,self.settings_button,self.history_list,self.search]:
            widget.setEnabled(not self.busy)
        self.retry_button.setEnabled(bool(self.current_id) and not self.busy)
        self.delete_button.setEnabled(bool(self.current_id) and not self.busy)
        self.copy_button.setEnabled(bool(self.editor.toPlainText().strip()) and not self.busy)
        self.editor.setReadOnly(self.busy)
        self.progress.setVisible(self.busy)
        self.cancel_button.setVisible(self.busy)
        self.cancel_button.setEnabled(self.busy)

    def start_capture(self):
        if self.busy or self.capture_pending:
            return
        self.save_and_preview()
        self.capture_pending = True
        self.hide()
        # Give the desktop compositor time to remove our window from the screenshot.
        QTimer.singleShot(220, self.capture.start)

    def capture_cancelled(self):
        self.capture_pending = False
        self.show_window()
        self.statusBar().showMessage('截图已取消', 3000)

    def on_capture(self, image):
        self.capture_pending = False
        self.show_window()
        self.recognize_image(pil_from_qimage(image))

    def paste_image(self):
        if self.busy:
            return
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if not image.isNull():
            self.recognize_image(pil_from_qimage(image))
        elif clipboard.mimeData().hasUrls():
            urls = clipboard.mimeData().urls()
            if urls and urls[0].isLocalFile():
                self.open_image(urls[0].toLocalFile())
        else:
            self.statusBar().showMessage('剪贴板中没有图片，请先截图或复制图片。', 6000)

    def import_image(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, '导入公式图片', '', '图片 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)')
        if path:
            self.open_image(path)

    def open_image(self, path):
        if self.busy:
            return
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                if image.width*image.height > 40_000_000:
                    raise ValueError('图片过大，请先裁剪要识别的公式区域。')
                if image.mode == 'RGBA' or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    image = Image.new('RGBA', rgba.size, 'white')
                    image.alpha_composite(rgba)
                self.recognize_image(image.convert('RGB'))
        except Exception as error:
            QMessageBox.warning(self, '无法打开图片', str(error))

    def recognize_image(self, image, existing_id=None):
        if self.busy:
            return
        self.save_and_preview()
        self.current_id = existing_id or self.history.add(image)
        self.busy = True
        self.history.result(self.current_id, '', 'running', 0)
        self.image_label.set_image(self.data_dir/self.history.get(self.current_id)['image'])
        self.image_info.setText(f'{image.width} × {image.height} px')
        self.set_editor('')
        self.detail_label.setText('正在本地识别…首次加载模型可能稍慢。')
        self.statusBar().showMessage(self.engine.name+' 正在识别 · 可取消')
        self.refresh_history()
        self.update_controls()
        self.worker = OCRWorker(self.engine, image.copy(), self)
        self.worker.partial.connect(self.partial_result)
        self.worker.completed.connect(self.recognition_done)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def partial_result(self, text):
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)

    def recognition_done(self, text, status, elapsed, note):
        self.history.result(self.current_id, text, status, elapsed, note)
        self.set_editor(text)
        self.detail_label.setText(note or f'识别完成  ·  {self.engine.name}  ·  {elapsed:.1f} 秒')
        self.last_status = status
        if status == 'error':
            self.statusBar().showMessage('识别失败，可在设置中检查模型目录。')
        elif status == 'done':
            self.statusBar().showMessage(f'识别完成，用时 {elapsed:.1f} 秒')
        else:
            self.statusBar().showMessage(note)

    def worker_finished(self):
        self.busy = False
        self.worker.deleteLater()
        self.worker = None
        self.update_controls()
        self.refresh_history()
        if getattr(self, 'last_status', '') == 'done' and self.settings['auto_copy']:
            self.copy_latex()
        if self.quitting:
            self.quit_app()

    def cancel_recognition(self):
        if self.worker:
            self.worker.cancelled.set()
            self.cancel_button.setEnabled(False)
            self.detail_label.setText('正在取消，等待当前计算结束…')

    def retry(self):
        if self.current_id and not self.busy:
            row = self.history.get(self.current_id)
            with Image.open(self.data_dir/row['image']) as image:
                self.recognize_image(image.convert('RGB'), existing_id=self.current_id)

    def copy_latex(self):
        if self.busy:
            return
        text = copy_text(self.editor.toPlainText(), self.copy_mode.currentData())
        if text:
            QApplication.clipboard().setText(text)
            self.statusBar().showMessage('已复制到剪贴板', 4000)
            self.copy_button.setText('已复制 ✓')
            QTimer.singleShot(1500, lambda: self.copy_button.setText('复制 LaTeX'))

    def delete_current(self):
        if not self.current_id or self.busy:
            return
        if QMessageBox.question(self, '删除截图', '删除这条历史记录及其原始截图？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.edit_timer.stop()
        self.history.delete(self.current_id)
        self.current_id = None
        self.set_editor('')
        self.image_label.set_image(None)
        self.image_info.clear()
        self.detail_label.setText('记录已删除')
        self.refresh_history()
        self.update_controls()

    def open_settings(self):
        if self.busy:
            return
        from . import startup
        values = {**self.settings, 'model_dir':str(self.model_path()), 'autostart':startup.enabled()}
        dialog = SettingsDialog(values, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                if dialog.autostart.isChecked()!=values['autostart']:
                    startup.set_enabled(dialog.autostart.isChecked())
            except OSError as error:
                QMessageBox.warning(self,'无法修改开机自启动',str(error))
                return
            model_dir = Path(dialog.model.text()).resolve()
            default_model = (app_root()/'onnx').resolve()
            changed = model_dir != self.model_path().resolve() or dialog.engine_choice.currentData() != self.settings.get('engine', 'formula' if selected_config() else 'mixtex')
            self.settings.update(hotkey=dialog.hotkey.currentText(), auto_copy=dialog.auto.isChecked(),
                                 close_to_tray=dialog.tray.isChecked(), model_dir='onnx' if model_dir==default_model else str(model_dir), engine=dialog.engine_choice.currentData())
            self.auto_copy.setChecked(self.settings['auto_copy'])
            self.save_settings()
            if changed:
                if hasattr(self.engine, 'close'):
                    self.engine.close()
                self.engine = make_engine(self.settings)
                if hasattr(self, 'engine_badge'):
                    self.engine_badge.setText(' '+self.engine.name+' ')
            self.register_hotkey()

    def register_hotkey(self):
        self.hotkey_label.setText(self.settings['hotkey'])
        if sys.platform != 'win32':
            self.statusBar().showMessage('全局快捷键仅支持 Windows；可点击截图按钮。')
            return
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        hwnd = int(self.winId())
        if self.hotkey_registered:
            user32.UnregisterHotKey(hwnd, self.HOTKEY_ID)
        choices = {'Ctrl+Alt+M':(0x0002|0x0001,ord('M')), 'Ctrl+Shift+M':(0x0002|0x0004,ord('M')), 'Ctrl+Alt+S':(0x0002|0x0001,ord('S'))}
        requested = self.settings['hotkey']
        self.hotkey_registered = False
        for shortcut in [requested] + [value for value in choices if value != requested]:
            modifiers, key = choices.get(shortcut, (3, ord('M')))
            if user32.RegisterHotKey(hwnd, self.HOTKEY_ID, modifiers|0x4000, key):
                self.hotkey_registered = True
                self.settings['hotkey'] = shortcut
                self.hotkey_label.setText(shortcut)
                if shortcut != requested:
                    self.save_settings()
                    self.statusBar().showMessage(f'{requested} 已被占用，截图快捷键已改为 {shortcut}')
                break
            logging.warning('Hotkey %s failed: Windows error %s', shortcut, ctypes.get_last_error())
        if not self.hotkey_registered:
            self.hotkey_label.setText('快捷键被占用，请到设置中更换')
            self.statusBar().showMessage('全局快捷键注册失败，仍可点击截图按钮。')

    def nativeEvent(self, event_type, message):
        if sys.platform == 'win32':
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.HOTKEY_ID:
                QTimer.singleShot(0, self.start_capture)
                return True, 0
        return super().nativeEvent(event_type, message)

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_image(url.toLocalFile())
                event.acceptProposedAction()
                break

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def about(self):
        from . import __version__
        QMessageBox.about(self, '关于 MixSnip', f'MixSnip {__version__}\n\n当前模型：{self.engine.name}\n本地公式识别、MathJax 预览与 Office 可编辑公式导出，无需 API。\n\nMixTeX：Renqing Luo / RQLuo\nPP-FormulaNet：PaddlePaddle / PaddleOCR\n本程序源码位于 source，授权说明位于 licenses。\n\n请对照原图核对关键符号与标点。')

    def closeEvent(self, event):
        self.save_and_preview()
        if not self.quitting and self.settings['close_to_tray'] and self.tray.isVisible():
            self.hide()
            event.ignore()
            return
        event.ignore()
        self.quit_app()

    def quit_app(self):
        self.quitting = True
        if self.busy:
            self.cancel_recognition()
            return
        self.save_and_preview()
        self.capture.clear()
        if self.hotkey_registered and sys.platform == 'win32':
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), self.HOTKEY_ID)
            self.hotkey_registered = False
        self.tray.hide()
        if hasattr(self.engine, 'close'):
            self.engine.close()
        QApplication.instance().quit()
