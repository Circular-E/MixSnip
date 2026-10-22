"""Small editable line icons drawn locally; no external icon assets."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

PATHS = {
 'snip':'<path stroke-dasharray="3 3" d="M17 20H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2v10"/><path d="M19 17v6m-3-3h6"/>',
 'image':'<path d="M17 5H3v16h18V10M4 18l5-6 4 4 3-3 4 5M20 1v8m-4-4 4-4 4 4"/><circle cx="8" cy="8" r="1"/>',
 'draw':'<path d="m4 10 7-7a2.5 2.5 0 0 1 3.5 3.5l-9 9a3 3 0 0 0 4 4l10-10a2 2 0 0 1 3 3l-4 4a2 2 0 0 0 1 4"/>',
 'keyboard':'<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.1M10 9h.1M14 9h.1M18 9h.1M6 12h.1M10 12h.1M14 12h.1M18 12h.1M7 16h10"/>',
 'history':'<path d="M8 5h14M8 12h14M8 19h14M3 5h.1M3 12h.1M3 19h.1"/>',
 'pdf':'<path d="M6 11V2h10l5 5v4M16 2v6h5M5 15h3a2 2 0 1 1 0 4H5m0-4v8M12 15h2a4 4 0 0 1 0 8h-2zm8 8v-8h4m-4 4h3"/>',
 'trash':'<path d="M3 6h18M9 6V2h6v4M5 6l1 16h12l1-16M10 10v8m4-8v8"/>',
 'settings':'<path d="m9 2-.7 3-2 .9-2.8-.8-2 3.5 2.2 2.1v2.6l-2.2 2.1 2 3.5 2.8-.8 2 .9.7 3h4l.7-3 2-.9 2.8.8 2-3.5-2.2-2.1v-2.6l2.2-2.1-2-3.5-2.8.8-2-.9-.7-3Z"/><circle cx="11" cy="12" r="3.1"/>',
 'copy':'<path d="M8 3h8l4 4v14H8zM16 3v5h4M5 6H3v17h13"/>',
 'edit':'<path d="M11 4H3v18h18v-9M8 16v-4L18 2a2 2 0 0 1 4 4L12 16Z"/>',
 'zoom':'<circle cx="10" cy="10" r="7"/><path d="m15 15 7 7"/>',
 'open':'<path d="M11 3H3v18h18v-8M14 2h8v8M10 14 22 2"/>',
 'sliders':'<path d="M2 5h12m4 0h4M2 12h4m4 0h12M2 19h12m4 0h6"/><circle cx="16" cy="5" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="19" r="2"/>',
 'word':'<path d="M7 2h10l4 4v16H7M17 2v5h4M2 6h13v13H2zM4 9l1.5 7L8 11l2 5 1.5-7"/>',
 'up':'<path d="M3 11h4v11H3zm5 10h10a2 2 0 0 0 2-2l2-7a2 2 0 0 0-2-2h-6l1-6a2 2 0 0 0-4-1l-4 9"/>',
 'down':'<g transform="translate(0 24) scale(1 -1)"><path d="M3 11h4v11H3zm5 10h10a2 2 0 0 0 2-2l2-7a2 2 0 0 0-2-2h-6l1-6a2 2 0 0 0-4-1l-4 9"/></g>',
 'refresh':'<path d="M21 4v6h-6M3 20v-6h6M21 10A9 9 0 0 0 5 5M3 14a9 9 0 0 0 16 5"/>',
 'paste':'<path d="M8 4H4v18h16V4h-4M8 2h8v5H8zM8 11h8M8 15h8"/>',
}

def icon(name, color='#757592', size=32):
    body=PATHS.get(name,PATHS['copy'])
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 26"><g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>'
    pix=QPixmap(size*2,size*2)
    pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)
