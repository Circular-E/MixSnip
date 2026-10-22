"""Compact Snip View layout modeled on the user's Mathpix screenshot."""
import json
import logging
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageChops
from PySide6.QtCore import Qt,QSize,QUrl,QByteArray,Signal
from PySide6.QtGui import QPainter,QPen,QColor,QImage,QPixmap,QDesktopServices
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,QWidget,QFrame,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QToolButton,
    QLineEdit,QPlainTextEdit,QListWidget,QDialog,QDialogButtonBox,QStackedWidget,
    QButtonGroup,QComboBox,QCheckBox,QProgressBar,QMessageBox,QFileDialog,QScrollArea,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from .core import asset_root,copy_text,strip_math
from .ui import MainWindow,ImageLabel,OfflineOnly,pil_from_qimage
from .icons import icon


def variant(text,mode):
    if mode=='equation':
        bare=copy_text(text,'bare')
        if not bare:return ''
        if bare.startswith(r'\begin{equation}') and bare.endswith(r'\end{equation}'):
            return bare
        if bare==text.strip() and any(mark in bare for mark in [r'\[',r'\(', '$']):
            return bare
        return '\\begin{equation}\n'+bare+'\n\\end{equation}'
    return copy_text(text,mode)


class CodeLine(QLineEdit):
    activated=Signal()
    def mousePressEvent(self,event):
        self.activated.emit()
        super().mousePressEvent(event)


class DrawingCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(760,330)
        self.canvas=QImage(760,330,QImage.Format.Format_RGB32)
        self.canvas.fill(Qt.GlobalColor.white)
        self.last=None
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.drawImage(0,0,self.canvas)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.last=event.position().toPoint()
    def mouseMoveEvent(self,event):
        if self.last is not None:
            painter=QPainter(self.canvas)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(Qt.GlobalColor.black,3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            point=event.position().toPoint()
            painter.drawLine(self.last,point)
            painter.end()
            self.last=point
            self.update()
    def mouseReleaseEvent(self,event):
        self.last=None
    def clear(self):
        self.canvas.fill(Qt.GlobalColor.white)
        self.update()


class SnipWindow(MainWindow):
    MODES=['bare','inline','display','equation']

    def __init__(self,data_dir=None):
        super().__init__(data_dir)
        self.setWindowTitle('MixSnip Snipping Tool - Snip View')
        self.setMinimumSize(760,570)
        self.resize(1010,665)
        self.statusBar().hide()
        self.statusBar().messageChanged.connect(self.status_note.setText)
        self.refresh_navigation()

    def tool(self,name,tip,callback=None,size=32):
        button=QToolButton()
        button.setObjectName('IconTool')
        button.setIcon(icon(name,size=size))
        button.setIconSize(QSize(size,size))
        button.setFixedSize(43,43)
        button.setToolTip(tip)
        if callback:button.clicked.connect(callback)
        return button

    def make_preview(self):
        preview=QWebEngineView()
        guard=OfflineOnly(preview)
        preview._guard=guard
        preview.page().profile().setUrlRequestInterceptor(guard)
        preview.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False)
        preview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        return preview

    def build_ui(self):
        self.current_tab=0
        self.data_source=None
        self.data_parts=[]
        self.data_generation=0
        root=QWidget()
        root.setObjectName('SnipRoot')
        layout=QVBoxLayout(root)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        toolbar=QFrame()
        toolbar.setObjectName('TopToolbar')
        toolbar.setFixedHeight(52)
        tools=QHBoxLayout(toolbar)
        tools.setContentsMargins(18,3,16,3)
        tools.setSpacing(5)
        self.snip_button=self.tool('snip','截图 · 全局快捷键',self.start_capture)
        self.import_button=self.tool('image','导入图片 · Ctrl+O',self.import_image)
        self.draw_button=self.tool('draw','手写输入 · 使用当前本地模型识别',self.draw_formula)
        self.type_button=self.tool('keyboard','输入或编辑 LaTeX',lambda:self.edit_variant('bare'))
        self.history_button=self.tool('history','截图历史',self.open_history)
        self.pdf_button=self.tool('pdf','当前版本处理单张截图，尚未提供整篇 PDF 转换')
        self.pdf_button.setEnabled(False)
        for button in [self.snip_button,self.import_button,self.draw_button,self.type_button,self.history_button,self.pdf_button]:tools.addWidget(button)
        tools.addStretch(1)
        self.nav_buttons=[]
        for text,direction in [('«','first'),('‹','previous')]:
            button=QPushButton(text)
            button.setObjectName('NavButton')
            button.clicked.connect(lambda checked=False,d=direction:self.navigate(d))
            tools.addWidget(button)
            self.nav_buttons.append(button)
        self.counter=QLabel('0 / 0')
        self.counter.setObjectName('Counter')
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter.setMinimumWidth(116)
        tools.addWidget(self.counter)
        for text,direction in [('›','next'),('»','last')]:
            button=QPushButton(text)
            button.setObjectName('NavButton')
            button.clicked.connect(lambda checked=False,d=direction:self.navigate(d))
            tools.addWidget(button)
            self.nav_buttons.append(button)
        tools.addStretch(4)
        self.delete_button=self.tool('trash','删除当前截图',self.delete_current)
        self.settings_button=self.tool('settings','设置',self.open_settings)
        tools.addWidget(self.delete_button)
        tools.addWidget(self.settings_button)
        layout.addWidget(toolbar)

        tabs_frame=QFrame()
        tabs_frame.setObjectName('TabsBar')
        tabs=QHBoxLayout(tabs_frame)
        tabs.setContentsMargins(0,0,12,0)
        tabs.setSpacing(0)
        self.tab_group=QButtonGroup(self)
        self.tab_buttons=[]
        for index,title in enumerate(['OCR','Data','Original']):
            button=QPushButton(title)
            button.setObjectName('TabButton')
            button.setCheckable(True)
            button.setFixedWidth([72,74,96][index])
            self.tab_group.addButton(button,index)
            self.tab_buttons.append(button)
            tabs.addWidget(button)
        self.tab_buttons[0].setChecked(True)
        tabs.addSpacing(30)
        local=QLabel('Local OCR: unlimited')
        local.setObjectName('LocalLabel')
        tabs.addWidget(local)
        tabs.addSpacing(12)
        badge=self.engine_badge=QLabel(' '+self.engine.name+' ')
        badge.setObjectName('EngineBadge')
        tabs.addWidget(badge)
        tabs.addStretch()
        self.hotkey_label=QLabel(self.settings['hotkey'])
        self.hotkey_label.setObjectName('HotkeyHint')
        tabs.addWidget(self.hotkey_label)
        layout.addWidget(tabs_frame)

        self.pages=QStackedWidget()
        ocr=QWidget()
        ocr_layout=QVBoxLayout(ocr)
        ocr_layout.setContentsMargins(14,0,14,0)
        ocr_layout.setSpacing(0)
        self.preview_bar=QFrame()
        self.preview_bar.setObjectName('PreviewBar')
        self.preview_bar.setFixedHeight(36)
        ocr_bar=QHBoxLayout(self.preview_bar)
        ocr_bar.setContentsMargins(0,0,0,0)
        self.show_original=QPushButton('Show Original ﹀')
        self.show_original.setObjectName('TextAction')
        self.show_original.setCheckable(True)
        self.show_original.clicked.connect(self.toggle_original)
        ocr_bar.addWidget(self.show_original)
        ocr_bar.addStretch()
        self.up_button=self.tool('up','标记识别正确（只保存在本地）',lambda:self.feedback('good'),26)
        self.down_button=self.tool('down','标记需要修正（只保存在本地）',lambda:self.feedback('bad'),26)
        self.up_button.setFixedSize(36,36)
        self.down_button.setFixedSize(36,36)
        ocr_bar.addWidget(self.up_button)
        ocr_bar.addWidget(self.down_button)
        ocr_layout.addWidget(self.preview_bar)
        self.inline_original=ImageLabel()
        self.inline_original.setMinimumHeight(70)
        self.inline_original.setMaximumHeight(110)
        self.inline_original.hide()
        ocr_layout.addWidget(self.inline_original)
        self.preview=self.make_preview()
        self.preview.loadFinished.connect(self.preview_loaded)
        self.preview.setUrl(QUrl.fromLocalFile(str(asset_root()/'preview.html')))
        ocr_layout.addWidget(self.preview,1)
        self.pages.addWidget(ocr)

        # The existing controller uses this editor as its text model. User
        # editing remains available through the keyboard / row edit buttons.
        self.editor=QPlainTextEdit(root)
        self.editor.setPlaceholderText('识别结果会显示在这里。可编辑 LaTeX，修改后自动保存。')
        self.editor.textChanged.connect(lambda:self.edit_timer.start())
        self.editor.hide()
        self.detail_label=QLabel('',root)
        self.detail_label.setWordWrap(True)
        self.detail_label.hide()

        original_page=QWidget()
        original_layout=QVBoxLayout(original_page)
        original_layout.setContentsMargins(15,8,15,8)
        self.image_label=ImageLabel()
        original_layout.addWidget(self.image_label,1)
        self.image_info=QLabel('')
        original_layout.addWidget(self.image_info)
        self.pages.addWidget(original_page)
        self.tab_group.idClicked.connect(self.switch_tab)
        layout.addWidget(self.pages,1)

        exports=QFrame()
        self.exports_frame=exports
        exports.setObjectName('ExportBar')
        export_row=QHBoxLayout(exports)
        export_row.setContentsMargins(13,1,12,1)
        export_row.setSpacing(12)
        self.office_buttons=[]
        for name,title,open_doc in [('word','Copy MS Word',False),('open','Open DOCX',True)]:
            button=QPushButton(title)
            button.setObjectName('ExportAction')
            button.setIcon(icon(name,size=23))
            button.setIconSize(QSize(23,23))
            button.setToolTip('生成并打开含可编辑公式的 DOCX' if open_doc else '复制 Office 公式，在 Word 或 PowerPoint 中按 Ctrl+V 粘贴')
            button.setAccessibleName(title)
            button.clicked.connect(lambda checked=False,open_file=open_doc:self.export_office(open_file))
            self.office_buttons.append(button)
            export_row.addWidget(button)
        self.word_copy,self.docx_open=self.office_buttons
        help_button=QPushButton('ⓘ')
        help_button.setObjectName('TextAction')
        help_button.setToolTip('版本功能说明')
        help_button.clicked.connect(self.about)
        export_row.addWidget(help_button)
        export_row.addStretch()
        self.png_copy=QPushButton('Copy PNG')
        self.png_copy.setObjectName('ExportAction')
        self.png_copy.setIcon(icon('copy',size=23))
        self.png_copy.clicked.connect(lambda:self.export_png(False))
        self.png_open=QPushButton('Open PNG')
        self.png_open.setObjectName('ExportAction')
        self.png_open.setIcon(icon('open',size=23))
        self.png_open.clicked.connect(lambda:self.export_png(True))
        export_row.addWidget(self.png_copy)
        export_row.addWidget(self.png_open)
        self.format_button=self.tool('sliders','复制选项与本地识别设置',self.open_settings,24)
        self.format_button.setFixedSize(32,32)
        export_row.addWidget(self.format_button)
        layout.addWidget(exports)

        self.codes_frame=QFrame()
        self.codes_frame.setObjectName('CodesPanel')
        codes=QHBoxLayout(self.codes_frame)
        codes.setContentsMargins(15,16,15,16)
        codes.setSpacing(10)
        left=QFrame()
        left.setObjectName('CodeTable')
        rows=QVBoxLayout(left)
        rows.setContentsMargins(0,0,0,0)
        rows.setSpacing(0)
        right=QVBoxLayout()
        right.setContentsMargins(0,2,0,2)
        right.setSpacing(7)
        self.code_lines=[]
        self.row_buttons=[]
        self.active_mode='bare'
        for index,mode in enumerate(self.MODES):
            line=CodeLine()
            line.setObjectName('CodeLine')
            line.setReadOnly(True)
            line.setFixedHeight(57)
            line.setPlaceholderText(['LaTeX','$ LaTeX $','$$ LaTeX $$',r'\begin{equation} … \end{equation}'][index])
            line.setProperty('position','first' if index==0 else ('last' if index==3 else 'middle'))
            line.setProperty('active',index==0)
            line.activated.connect(lambda m=mode:self.activate_variant(m))
            rows.addWidget(line)
            self.code_lines.append(line)
            buttons=QHBoxLayout()
            buttons.setSpacing(9)
            group=[]
            for action,tip,callback in [
                ('copy','复制这一格式',lambda checked=False,m=mode:self.copy_variant(m)),
                ('edit','编辑 LaTeX',lambda checked=False,m=mode:self.edit_variant(m)),
                ('zoom','放大查看',lambda checked=False,m=mode:self.zoom_variant(m))]:
                button=QPushButton()
                button.setObjectName('RowAction')
                button.setIcon(icon(action,color='#888892',size=26))
                button.setIconSize(QSize(26,26))
                button.setFixedSize(50,50)
                button.setToolTip(tip)
                button.clicked.connect(callback)
                buttons.addWidget(button)
                group.append(button)
            right.addLayout(buttons)
            self.row_buttons.append(group)
        codes.addWidget(left,1)
        codes.addLayout(right)
        layout.addWidget(self.codes_frame)

        self.data_panel=QScrollArea()
        self.data_panel.setObjectName('DataPanel')
        self.data_panel.setWidgetResizable(True)
        self.data_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.data_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.data_panel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.data_panel.setFixedHeight(300)
        data_content=QWidget()
        data_content.setObjectName('DataContent')
        data_rows=QVBoxLayout(data_content)
        data_rows.setContentsMargins(8,6,8,12)
        data_rows.setSpacing(6)
        docx_heading=QHBoxLayout()
        docx_heading.setContentsMargins(14,0,0,0)
        heading=QLabel('DOCX(MS WORD)')
        heading.setObjectName('DataHeading')
        docx_heading.addWidget(heading)
        help_docx=QPushButton('ⓘ')
        help_docx.setObjectName('TextAction')
        help_docx.setFixedWidth(26)
        help_docx.setToolTip('生成并打开含可编辑 Office 公式的 Word 文档')
        help_docx.clicked.connect(lambda:QMessageBox.information(self,'DOCX (MS Word)','点击 Open DOCX 生成并打开 Word 文档。\n公式以原生 Office Math 格式保存，可直接编辑。'))
        docx_heading.addWidget(help_docx)
        docx_heading.addStretch()
        data_rows.addLayout(docx_heading)
        self.data_docx=QPushButton('Open DOCX')
        self.data_docx.setObjectName('DataDocx')
        self.data_docx.setFixedHeight(57)
        self.data_docx.clicked.connect(lambda:self.export_office(True))
        self.office_buttons.append(self.data_docx)
        data_rows.addWidget(self.data_docx)
        self.data_lines=[]
        self.data_copy_buttons=[]
        for index,title in enumerate(['MathML (MS Word)','MathML']):
            heading=QLabel(title)
            heading.setObjectName('DataHeading')
            heading.setContentsMargins(14,0,0,0)
            data_rows.addWidget(heading)
            row=QHBoxLayout()
            row.setSpacing(10)
            line=QLineEdit()
            line.setObjectName('DataCode')
            line.setReadOnly(True)
            line.setFixedHeight(57)
            line.setPlaceholderText('识别或输入公式后显示 MathML')
            line.setAccessibleName(title)
            row.addWidget(line,1)
            button=QPushButton()
            button.setObjectName('RowAction')
            button.setIcon(icon('copy',color='#888892',size=26))
            button.setIconSize(QSize(26,26))
            button.setFixedSize(50,50)
            button.setToolTip('复制可粘贴到 Word / PPT 的公式' if index==0 else '复制标准 MathML 源码')
            button.setAccessibleName('复制 '+title)
            button.clicked.connect(lambda checked=False,i=index:self.copy_data(i))
            row.addWidget(button)
            data_rows.addLayout(row)
            self.data_lines.append(line)
            self.data_copy_buttons.append(button)
        self.data_panel.setWidget(data_content)
        self.data_panel.hide()
        layout.addWidget(self.data_panel)

        footer=QFrame()
        footer.setObjectName('Footer')
        footer_layout=QVBoxLayout(footer)
        footer_layout.setContentsMargins(15,6,15,12)
        footer_layout.setSpacing(6)
        info=QHBoxLayout()
        self.state_title=QLabel('识别状态')
        self.state_title.setObjectName('StateTitle')
        self.state_title.setToolTip('本地模型不提供校准置信度；下方仅显示任务处理状态。')
        info.addWidget(self.state_title)
        self.status_note=QLabel('准备就绪 · 本地识别')
        self.status_note.setObjectName('StatusNote')
        info.addStretch()
        info.addWidget(self.status_note)
        self.cancel_button=QPushButton('取消识别')
        self.cancel_button.setObjectName('TextAction')
        self.cancel_button.clicked.connect(self.cancel_recognition)
        self.cancel_button.hide()
        info.addWidget(self.cancel_button)
        footer_layout.addLayout(info)
        self.progress=QProgressBar()
        self.progress.setObjectName('RecognitionProgress')
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        self.progress.setRange(0,1)
        self.progress.setValue(0)
        footer_layout.addWidget(self.progress)
        layout.addWidget(footer)
        self.setCentralWidget(root)

        # History remains a real searchable window, opened by the toolbar list icon.
        self.history_dialog=QDialog(self)
        self.history_dialog.setWindowTitle('Snip History · 截图历史')
        self.history_dialog.resize(550,520)
        hist=QVBoxLayout(self.history_dialog)
        self.search=QLineEdit()
        self.search.setPlaceholderText('搜索公式或日期')
        self.search.textChanged.connect(self.refresh_history)
        self.history_list=QListWidget()
        self.history_list.setIconSize(QSize(90,52))
        self.history_list.currentItemChanged.connect(self.history_changed)
        self.history_list.itemDoubleClicked.connect(lambda item:self.history_dialog.accept())
        self.history_count=QLabel('0 条记录')
        hist.addWidget(self.search)
        hist.addWidget(self.history_list,1)
        hist.addWidget(self.history_count)
        self.paste_button=QPushButton(self)
        self.paste_button.hide()
        self.retry_button=QPushButton(self)
        self.retry_button.hide()
        self.copy_button=self.row_buttons[0][0]
        self.auto_copy=QCheckBox(self)
        self.auto_copy.setChecked(self.settings['auto_copy'])
        self.auto_copy.toggled.connect(self.auto_changed)
        self.auto_copy.hide()
        self.copy_mode=QComboBox(self)
        for mode in ['bare','inline','display','original']:self.copy_mode.addItem(mode,mode)
        self.copy_mode.setCurrentIndex(max(0,self.copy_mode.findData(self.settings['copy_mode'])))
        self.copy_mode.currentIndexChanged.connect(self.mode_changed)
        self.copy_mode.hide()
        menu=self.import_button
        from PySide6.QtWidgets import QMenu
        import_menu=QMenu(menu)
        import_menu.addAction('导入图片…',self.import_image)
        import_menu.addAction('粘贴图片  Ctrl+Shift+V',self.paste_image)
        menu.setMenu(import_menu)
        menu.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        from PySide6.QtGui import QAction
        for title,handler in [('重新识别',self.retry),('粘贴图片',self.paste_image),('关于',self.about)]:
            action=QAction(title,self)
            action.triggered.connect(handler)
            self.addAction(action)
        self.update_controls()

    def refresh_history(self,*args):
        super().refresh_history(*args)
        self.refresh_navigation()

    def refresh_navigation(self):
        if not hasattr(self,'counter'):return
        rows=list(reversed(self.history.list()))
        ids=[row['id'] for row in rows]
        index=ids.index(self.current_id) if self.current_id in ids else -1
        self.counter.setText(f'{index+1} / {len(ids)}')
        for i,button in enumerate(self.nav_buttons):
            button.setEnabled(not self.busy and (index>0 if i<2 else 0<=index<len(ids)-1))

    def navigate(self,direction):
        if self.busy:return
        ids=[row['id'] for row in reversed(self.history.list())]
        if not ids:return
        index=ids.index(self.current_id) if self.current_id in ids else 0
        index={'first':0,'previous':max(0,index-1),'next':min(len(ids)-1,index+1),'last':len(ids)-1}[direction]
        self.select(ids[index])

    def select(self,key):
        super().select(key)
        row=self.history.get(key)
        if row:self.inline_original.set_image(self.data_dir/row['image'])
        self.refresh_navigation()
        self.update_feedback()

    def recognize_image(self,image,existing_id=None):
        super().recognize_image(image,existing_id)
        if self.current_id:self.inline_original.set_image(self.data_dir/self.history.get(self.current_id)['image'])
        self.switch_tab(0)

    def render_preview(self):
        super().render_preview()
        if hasattr(self,'code_lines'):
            text=self.editor.toPlainText()
            for line,mode in zip(self.code_lines,self.MODES):
                line.setText(variant(text,mode).replace('\n',' '))
                line.setCursorPosition(0)
                line.setToolTip(variant(text,mode))
        if self.current_tab==1:self.refresh_data()

    def partial_result(self,text):
        super().partial_result(text)
        for line,mode in zip(self.code_lines,self.MODES):
            line.setText(variant(text,mode).replace('\n',' '))
            line.setCursorPosition(0)

    def save_and_preview(self):
        super().save_and_preview()
        self.update_controls()

    def update_controls(self):
        super().update_controls()
        ready=bool(self.editor.toPlainText().strip()) and not self.busy
        for group in self.row_buttons:
            for button in group:button.setEnabled(ready)
        for button in [self.draw_button,self.type_button,self.history_button,self.format_button]:button.setEnabled(not self.busy)
        for button in [self.png_copy,self.png_open,self.up_button,self.down_button]:button.setEnabled(ready)
        for button in self.office_buttons:button.setEnabled(ready and not getattr(self,'office_pending',False))
        data_ready=ready and self.data_source==self.editor.toPlainText() and bool(self.data_parts)
        for button in self.data_copy_buttons:button.setEnabled(data_ready)
        self.show_original.setEnabled(bool(self.current_id))
        self.progress.show()
        self.progress.setRange(0,0 if self.busy else 1)
        row=self.history.get(self.current_id) if self.current_id else None
        self.progress.setValue(1 if ready and row and row['status'] in ('done','manual') else 0)
        self.refresh_navigation()

    def switch_tab(self,index):
        self.current_tab=index
        self.tab_buttons[index].setChecked(True)
        self.pages.setCurrentIndex(1 if index==2 else 0)
        is_data=index==1
        self.exports_frame.setVisible(not is_data)
        self.codes_frame.setVisible(not is_data)
        self.data_panel.setVisible(is_data)
        self.up_button.setVisible(not is_data)
        self.down_button.setVisible(not is_data)
        self.preview_bar.setFixedHeight(44 if is_data else 36)
        self.preview_bar.setProperty('dataMode',is_data)
        self.preview_bar.style().unpolish(self.preview_bar)
        self.preview_bar.style().polish(self.preview_bar)
        if is_data:self.refresh_data()

    def refresh_data(self):
        from .office import split_latex
        text=self.editor.toPlainText()
        self.data_generation+=1
        generation=self.data_generation
        self.data_source=None
        self.data_parts=[]
        for line in self.data_lines:
            line.clear()
            line.setToolTip('')
            line.setPlaceholderText('正在生成 MathML…' if text.strip() else '识别或输入公式后显示 MathML')
        self.update_controls()
        if not text.strip():return
        try:
            parts=split_latex(text)
        except ValueError as error:
            self.data_failed(str(error))
            return
        script='window.officeMath?window.officeMath('+json.dumps(parts)+'):JSON.stringify({error:"公式引擎正在加载，请稍后重试。"})'
        self.preview.page().runJavaScript(script,lambda value:self.data_ready(value,text,generation))

    def data_ready(self,value,source,generation):
        if generation!=self.data_generation or source!=self.editor.toPlainText():return
        try:
            from .office import clipboard_payload,validated_parts
            result=json.loads(value or '{}')
            if result.get('error'):raise ValueError(result['error'])
            parts=validated_parts(result.get('parts',[]))
            word_mathml,_=clipboard_payload(parts)
            raw_mathml='\n'.join(p['mathml'] for p in parts if p['kind']=='math')
            self.data_values=[word_mathml,raw_mathml]
            self.data_source=source
            self.data_parts=parts
            for line,text in zip(self.data_lines,self.data_values):
                line.setText(text.replace('\n',' '))
                line.setCursorPosition(0)
                line.setToolTip(text)
        except Exception as error:
            self.data_failed(str(error))
        self.update_controls()

    def data_failed(self,error):
        for line in self.data_lines:
            line.setPlaceholderText('无法生成 MathML，请点击顶部键盘图标修正公式')
            line.setToolTip(error)
        self.statusBar().showMessage(error,5000)

    def copy_data(self,index):
        if self.busy or self.data_source!=self.editor.toPlainText() or not self.data_parts:return
        if index==0:
            from .office import copy_office
            copy_office(self.data_parts)
            self.statusBar().showMessage('已复制 Office 公式 · 在 Word / PPT 中按 Ctrl+V',6000)
        else:
            QApplication.clipboard().setText(self.data_values[1])
            self.statusBar().showMessage('已复制 MathML 源码',4000)

    def activate_variant(self,mode):
        self.active_mode=mode
        for line,current in zip(self.code_lines,self.MODES):
            line.setProperty('active',current==mode)
            line.style().unpolish(line)
            line.style().polish(line)

    def copy_variant(self,mode):
        if self.busy:return
        text=variant(self.editor.toPlainText(),mode)
        if text:
            QApplication.clipboard().setText(text)
            self.activate_variant(mode)
            self.statusBar().showMessage('已复制 LaTeX',4000)

    def copy_latex(self):
        self.copy_variant(self.copy_mode.currentData())

    def edit_variant(self,mode):
        if self.busy:return
        dialog=QDialog(self)
        dialog.setWindowTitle('Edit LaTeX')
        dialog.resize(680,340)
        layout=QVBoxLayout(dialog)
        edit=QPlainTextEdit(variant(self.editor.toPlainText(),mode))
        layout.addWidget(edit)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            text=edit.toPlainText().strip()
            if text.startswith(r'\begin{equation}') and text.endswith(r'\end{equation}'):
                text=text[len(r'\begin{equation}'):-len(r'\end{equation}')].strip()
            else:text=strip_math(text)
            if not self.current_id:
                self.current_id=self.history.add(Image.new('RGB',(448,160),'white'))
                self.history.result(self.current_id,text,'manual',0,'手动输入 LaTeX')
            self.set_editor(text)
            self.save_and_preview()
            self.refresh_history()

    def zoom_variant(self,mode):
        dialog=QDialog(self)
        dialog.setWindowTitle('Snip · 放大查看')
        dialog.resize(820,480)
        layout=QVBoxLayout(dialog)
        preview=self.make_preview()
        preview.loadFinished.connect(lambda ok:preview.page().runJavaScript('window.renderLatex('+json.dumps(self.editor.toPlainText())+');') if ok else None)
        preview.setUrl(QUrl.fromLocalFile(str(asset_root()/'preview.html')))
        layout.addWidget(preview,1)
        code=QPlainTextEdit(variant(self.editor.toPlainText(),mode))
        code.setReadOnly(True)
        code.setMaximumHeight(120)
        layout.addWidget(code)
        copy=QPushButton('复制 LaTeX')
        copy.clicked.connect(lambda:self.copy_variant(mode))
        layout.addWidget(copy)
        dialog.exec()

    def open_history(self):
        self.save_and_preview()
        self.refresh_history()
        self.history_dialog.exec()

    def toggle_original(self,checked):
        self.inline_original.setVisible(checked)
        self.show_original.setText('Hide Original ﹀' if checked else 'Show Original ﹀')

    def feedback(self,value):
        if not self.current_id:return
        feedback=self.settings.setdefault('feedback',{})
        if feedback.get(self.current_id)==value:feedback.pop(self.current_id)
        else:feedback[self.current_id]=value
        self.save_settings()
        self.update_feedback()
        self.statusBar().showMessage('标记已保存在本地',3000)

    def update_feedback(self):
        value=self.settings.get('feedback',{}).get(self.current_id)
        self.up_button.setIcon(icon('up','#0b6667' if value=='good' else '#858591',26))
        self.down_button.setIcon(icon('down','#0b6667' if value=='bad' else '#858591',26))

    def draw_formula(self):
        dialog=QDialog(self)
        dialog.setWindowTitle('手写输入 · '+self.engine.name)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('用鼠标或触控笔书写单个公式，完成后点击识别。'))
        canvas=DrawingCanvas()
        layout.addWidget(canvas)
        row=QHBoxLayout()
        clear=QPushButton('清空')
        clear.clicked.connect(canvas.clear)
        row.addWidget(clear)
        row.addStretch()
        cancel=QPushButton('取消')
        cancel.clicked.connect(dialog.reject)
        row.addWidget(cancel)
        recognize=QPushButton('识别')
        recognize.clicked.connect(dialog.accept)
        row.addWidget(recognize)
        layout.addLayout(row)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            image=pil_from_qimage(canvas.canvas)
            box=ImageChops.difference(image,Image.new('RGB',image.size,'white')).getbbox()
            if not box:return
            box=(max(0,box[0]-12),max(0,box[1]-12),min(image.width,box[2]+12),min(image.height,box[3]+12))
            self.recognize_image(image.crop(box))

    def export_png(self,open_file):
        script="""(()=>{const el=document.querySelector('#content svg');if(!el)return '';const s=el.cloneNode(true),r=el.getBoundingClientRect();s.setAttribute('width',r.width);s.setAttribute('height',r.height);return new XMLSerializer().serializeToString(s)})()"""
        self.preview.page().runJavaScript(script,lambda svg:self.png_ready(svg,open_file))

    def export_office(self,open_file):
        if self.busy or getattr(self,'office_pending',False):return
        from .office import split_latex
        text=self.editor.toPlainText()
        try:
            parts=split_latex(text)
        except ValueError as error:
            QMessageBox.warning(self,'Office 公式',str(error))
            return
        self.office_pending=True
        self.update_controls()
        self.statusBar().showMessage('正在生成可编辑 Office 公式…')
        script='window.officeMath?window.officeMath('+json.dumps(parts)+'):JSON.stringify({error:"公式引擎正在加载，请稍后重试。"})'
        self.preview.page().runJavaScript(script,lambda result:self.office_ready(result,open_file,text))

    def office_ready(self,result,open_file,source):
        from .office import copy_office,write_docx
        try:
            if source!=self.editor.toPlainText():
                raise ValueError('公式已更改，请重新点击导出按钮。')
            value=json.loads(result or '{}')
            if value.get('error'):raise ValueError(value['error'])
            if not value.get('parts'):raise ValueError('未得到公式内容，请等待预览加载完成后重试。')
            if open_file:
                stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                path=write_docx(value['parts'],self.data_dir/'exports'/f'Formula-{stamp}.docx')
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                    QMessageBox.information(self,'DOCX 已保存',f'文件已生成，请用 Word 打开：\n{path}')
                self.statusBar().showMessage('已生成可编辑 DOCX：'+path.name,6000)
            else:
                copy_office(value['parts'])
                self.statusBar().showMessage('已复制 Office 公式 · 在 Word / PPT 中按 Ctrl+V',6000)
        except Exception as error:
            logging.exception('Office math export failed')
            self.statusBar().showMessage('Office 公式导出失败',5000)
            QMessageBox.warning(self,'Office 公式导出失败',str(error))
        finally:
            self.office_pending=False
            self.update_controls()

    def png_ready(self,svg,open_file):
        if not svg:
            self.statusBar().showMessage('当前内容没有可导出的公式预览。',4000)
            return
        renderer=QSvgRenderer(QByteArray(svg.encode()))
        if not renderer.isValid():
            self.statusBar().showMessage('无法导出当前公式预览。',4000)
            return
        size=renderer.defaultSize()*3
        size=size.boundedTo(QSize(8000,8000))
        image=QImage(size+QSize(48,48),QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter=QPainter(image)
        from PySide6.QtCore import QRectF
        renderer.render(painter,QRectF(24,24,size.width(),size.height()))
        painter.end()
        if open_file:
            folder=self.data_dir/'exports'
            folder.mkdir(exist_ok=True)
            path=folder/f'{self.current_id or "formula"}.png'
            image.save(str(path))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QApplication.clipboard().setImage(image)
            self.statusBar().showMessage('已复制公式 PNG',4000)

    def register_hotkey(self):
        super().register_hotkey()
        self.snip_button.setToolTip('截图 · '+self.settings['hotkey'])

