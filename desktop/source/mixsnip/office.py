"""Offline Office Math export. No images, macros, Office COM or cloud services."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from html import escape
import os
from pathlib import Path
import re
import tempfile
import zipfile

from lxml import etree as ET

MML = 'http://www.w3.org/1998/Math/MathML'
OMML = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
WORD = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML = 'http://www.w3.org/XML/1998/namespace'
NS = {'m': OMML, 'w': WORD}


def split_latex(text):
    """Keep prose and inline/display math in order; undelimited input is math."""
    text = text.strip()
    if not text:
        raise ValueError('当前没有公式。')
    if len(text) > 30000:
        raise ValueError('内容过长，请分成较短的公式导出。')
    pattern = re.compile(r'(?<!\\)(\$\$[\s\S]*?(?<!\\)\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$(?!\$)(?:\\.|[^$])*?(?<!\\)\$)')
    result, end = [], 0
    for match in pattern.finditer(text):
        if match.start() > end:
            result.append({'kind': 'text', 'text': text[end:match.start()]})
        value = match.group()
        block = value.startswith(('$$', r'\['))
        n = 2 if value.startswith(('$$', r'\[', r'\(')) else 1
        result.append({'kind': 'math', 'text': value[n:-n], 'display': block})
        end = match.end()
    if not result:
        return [{'kind': 'math', 'text': text, 'display': True}]
    if end < len(text):
        result.append({'kind': 'text', 'text': text[end:]})
    return result


def parse_mathml(value):
    if '<!DOCTYPE' in value.upper() or '<!ENTITY' in value.upper():
        raise ValueError('公式包含不允许的 XML 声明。')
    root = ET.fromstring(value.encode('utf-8'), ET.XMLParser(resolve_entities=False, no_network=True))
    if root.tag != f'{{{MML}}}math':
        raise ValueError('未得到有效 MathML 公式。')
    if root.xpath('.//*[local-name()="merror"] | .//*[@data-mjx-error] | .//*[@mathcolor="red"]'):
        raise ValueError('公式存在无法识别的 LaTeX 命令，请点击顶部键盘图标修正。')
    # Remove MathJax-only metadata, retaining semantic MathML attributes.
    for node in root.iter():
        for name in list(node.attrib):
            if name.startswith('data-') or name in ('class', 'id'):
                del node.attrib[name]
    return root


def validated_parts(parts):
    result = []
    for part in parts:
        item = dict(part)
        if item['kind'] == 'math':
            item['mathml'] = ET.tostring(parse_mathml(item['mathml']), encoding='unicode')
        result.append(item)
    if not any(p['kind'] == 'math' for p in result):
        raise ValueError('当前内容没有可导出的公式。')
    return result


def clipboard_payload(parts):
    """Return HTML and a single MathML document accepted by Office's clipboard."""
    parts = validated_parts(parts)
    fragment = ''.join(p['mathml'] if p['kind'] == 'math' else escape(p['text']).replace('\n', '<br>') for p in parts)
    if len(parts) == 1 and parts[0]['kind'] == 'math':
        mathml = parts[0]['mathml']
    else:
        # A single MathML root also permits PowerPoint to import mixed snippets.
        root = ET.Element(f'{{{MML}}}math', nsmap={None: MML}, display='block')
        table = ET.SubElement(root, f'{{{MML}}}mtable', columnalign='left')
        cell = None
        def new_row():
            return ET.SubElement(ET.SubElement(table, f'{{{MML}}}mtr'), f'{{{MML}}}mtd')
        for part in parts:
            if part['kind'] == 'text':
                for index, line in enumerate(part['text'].split('\n')):
                    if index or cell is None: cell = new_row()
                    if line: ET.SubElement(cell, f'{{{MML}}}mtext').text = line
            else:
                if cell is None or part.get('display'): cell = new_row()
                row = ET.SubElement(cell, f'{{{MML}}}mrow')
                for child in parse_mathml(part['mathml']): row.append(deepcopy(child))
                if part.get('display'): cell = None
        mathml = ET.tostring(root, encoding='unicode')
    return mathml, '<html><head><meta charset="utf-8"></head><body>'+fragment+'</body></html>'


def copy_office(parts):
    from PySide6.QtCore import QMimeData, QByteArray
    from PySide6.QtWidgets import QApplication
    mathml, html = clipboard_payload(parts)
    mime = QMimeData()
    # Unicode MathML is the documented Office clipboard encoding. Qt exposes
    # registered Windows clipboard formats through this MIME convention.
    native = QByteArray((mathml+'\0').encode('utf-16le'))
    for name in ('MathML', 'MathML Presentation'):
        mime.setData(f'application/x-qt-windows-mime;value="{name}"', native)
    mime.setData('application/mathml+xml', mathml.encode('utf-8'))
    mime.setHtml(html)
    mime.setText(mathml)
    QApplication.clipboard().setMimeData(mime)


@lru_cache(maxsize=1)
def office_transform():
    """Use the locally installed Microsoft transform, without redistributing it."""
    candidates = []
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE', 0, winreg.KEY_READ | view) as key:
                        candidates.append(Path(winreg.QueryValue(key, None)).parent/'MML2OMML.XSL')
                except OSError:
                    pass
    for env in ('ProgramFiles', 'ProgramFiles(x86)'):
        base = os.environ.get(env)
        if base:
            for folder in ('Microsoft Office/root/Office16', 'Microsoft Office/Office16', 'Microsoft Office/Office15'):
                candidates.append(Path(base)/folder/'MML2OMML.XSL')
    for path in candidates:
        if path.is_file():
            return ET.XSLT(ET.parse(str(path)), access_control=ET.XSLTAccessControl.DENY_ALL)
    return None


def to_omml(mathml):
    root = parse_mathml(mathml)
    transform = office_transform()
    if transform is not None:
        result = transform(root).getroot()
    else:
        import mathml2omml
        value = mathml2omml.convert(ET.tostring(root, encoding='unicode'))
        # Some converters omit the namespace declaration from their output.
        wrapper = ET.fromstring(('<root xmlns:m="'+OMML+'" xmlns:w="'+WORD+'">'+value+'</root>').encode())
        result = wrapper[0]
    math = result if result.tag == f'{{{OMML}}}oMath' else result.find('.//m:oMath', NS)
    if math is None or not list(math):
        raise ValueError('无法生成可编辑 Office 公式，请检查 LaTeX。')
    return deepcopy(math)


def write_docx(parts, destination):
    """Write a real OOXML package containing native m:oMath, atomically."""
    parts = validated_parts(parts)
    document = ET.Element(f'{{{WORD}}}document', nsmap=NS)
    body = ET.SubElement(document, f'{{{WORD}}}body')
    paragraph = None
    def new_paragraph(center=False):
        p = ET.SubElement(body, f'{{{WORD}}}p')
        if center:
            prop = ET.SubElement(p, f'{{{WORD}}}pPr')
            ET.SubElement(prop, f'{{{WORD}}}jc', {f'{{{WORD}}}val': 'center'})
        return p
    for part in parts:
        if part['kind'] == 'text':
            for index, line in enumerate(part['text'].split('\n')):
                if paragraph is None or index: paragraph = new_paragraph()
                if line:
                    run = ET.SubElement(paragraph, f'{{{WORD}}}r')
                    ET.SubElement(run, f'{{{WORD}}}t', {f'{{{XML}}}space': 'preserve'}).text = line
        else:
            if paragraph is None or part.get('display'): paragraph = new_paragraph(part.get('display', False))
            math = to_omml(part['mathml'])
            # Inline and display both remain native, independently editable math.
            if part.get('display'):
                container = ET.SubElement(paragraph, f'{{{OMML}}}oMathPara')
                container.append(math)
                paragraph = None
            else:
                paragraph.append(math)
    section = ET.SubElement(body, f'{{{WORD}}}sectPr')
    ET.SubElement(section, f'{{{WORD}}}pgSz', {f'{{{WORD}}}w': '11906', f'{{{WORD}}}h': '16838'})
    ET.SubElement(section, f'{{{WORD}}}pgMar', {f'{{{WORD}}}{k}': '1440' for k in ('top','right','bottom','left')})
    content_types = '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
    rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    doc_rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    styles = f'''<w:styles xmlns:w="{WORD}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math" w:eastAsia="等线"/><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>'''
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as package:
            for path, content in {'[Content_Types].xml':content_types, '_rels/.rels':rels, 'word/document.xml':ET.tostring(document, xml_declaration=True, encoding='UTF-8', standalone=True), 'word/styles.xml':styles, 'word/_rels/document.xml.rels':doc_rels}.items():
                package.writestr(path, content)
        os.replace(temporary, destination)
    finally:
        if temporary and temporary.exists(): temporary.unlink()
    return destination
