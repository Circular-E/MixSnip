"""Qt region picker. One overlay per screen preserves each screen's DPI."""
from PySide6.QtCore import Qt, QRect, Signal, QObject
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QApplication


def pixel_rect(rect: QRect, logical_size, pixel_size):
    sx, sy = pixel_size.width()/logical_size.width(), pixel_size.height()/logical_size.height()
    x, y = round(rect.x()*sx), round(rect.y()*sy)
    right, bottom = round((rect.x()+rect.width())*sx), round((rect.y()+rect.height())*sy)
    return QRect(x, y, right-x, bottom-y).intersected(QRect(0, 0, pixel_size.width(), pixel_size.height()))


class RegionOverlay(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen, pixmap):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window)
        self.setWindowTitle('MixSnip · 框选截图')
        self.snapshot = pixmap.toImage()
        self.setGeometry(screen.geometry())
        self.origin = None
        self.selection = QRect()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawImage(self.rect(), self.snapshot)
        p.fillRect(self.rect(), QColor(12, 20, 35, 105))
        if not self.selection.isNull():
            p.save()
            p.setClipRect(self.selection)
            p.drawImage(self.rect(), self.snapshot)
            p.restore()
            p.setPen(QPen(QColor('#3984ff'), 2))
            p.drawRect(self.selection)
        p.setPen(Qt.GlobalColor.white)
        p.fillRect(QRect(20, 20, 450, 42), QColor(24, 32, 48, 220))
        p.drawText(QRect(32, 20, 430, 42), Qt.AlignmentFlag.AlignVCenter,
                   '拖动框选公式 · 松开鼠标识别 · Esc / 右键取消')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.selection = QRect(self.origin, self.origin)
            self.grabMouse()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.origin is None:
            return
        self.releaseMouse()
        self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
        self.origin = None
        if self.selection.width() < 5 or self.selection.height() < 5:
            self.cancelled.emit()
            return
        crop = pixel_rect(self.selection, self.size(), self.snapshot.size())
        result = self.snapshot.copy(crop)
        result.setDevicePixelRatio(1.0)
        self.selected.emit(result)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()


class CaptureController(QObject):
    captured = Signal(object)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays = []

    def start(self):
        # Capture all screens before any overlay becomes visible.
        snapshots = [(screen, screen.grabWindow(0)) for screen in QApplication.screens()]
        if not snapshots or any(pixmap.isNull() for _, pixmap in snapshots):
            self.cancelled.emit()
            return
        for screen, pixmap in snapshots:
            overlay = RegionOverlay(screen, pixmap)
            overlay.selected.connect(self.finish)
            overlay.cancelled.connect(self.abort)
            self.overlays.append(overlay)
        for overlay in self.overlays:
            overlay.show()
        from PySide6.QtGui import QCursor
        for overlay in self.overlays:
            if overlay.geometry().contains(QCursor.pos()):
                overlay.activateWindow()
                overlay.setFocus()

    def clear(self):
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def finish(self, image):
        self.clear()
        self.captured.emit(image)

    def abort(self):
        self.clear()
        self.cancelled.emit()
