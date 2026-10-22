import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from mixsnip.office import (MML,NS,ET,split_latex,parse_mathml,clipboard_payload,
                            to_omml,write_docx)

FRACTION=f'<math xmlns="{MML}" display="block"><mfrac><mi>α</mi><msup><mi>x</mi><mn>2</mn></msup></mfrac></math>'
MATRIX=f'<math xmlns="{MML}"><mfenced open="(" close=")"><mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi></mtd><mtd><mi>d</mi></mtd></mtr></mtable></mfenced></math>'

def formula(value=FRACTION,display=True):
    return {'kind':'math','mathml':value,'display':display}


class OfficeTests(unittest.TestCase):
    def test_split_preserves_prose_and_delimiters(self):
        parts=split_latex(r'当 $x>0$ 时，\[f(x)=\frac{1}{x}\]')
        self.assertEqual([p['kind'] for p in parts],['text','math','text','math'])
        self.assertFalse(parts[1]['display'])
        self.assertTrue(parts[3]['display'])
        self.assertEqual(parts[3]['text'],r'f(x)=\frac{1}{x}')
        self.assertEqual(split_latex('$$x$$')[0]['text'],'x')
        self.assertEqual(split_latex(r'\(x\)')[0]['text'],'x')
        self.assertEqual(split_latex(r'\begin{equation}x\end{equation}')[0]['kind'],'math')

    def test_xml_entities_errors_and_foreign_roots_are_rejected(self):
        for xml in ['<!DOCTYPE math><math/>','<html/>',f'<math xmlns="{MML}"><merror><mtext>bad</mtext></merror></math>',f'<math xmlns="{MML}"><mtext mathcolor="red">bad</mtext></math>']:
            with self.assertRaises(ValueError):parse_mathml(xml)

    def test_clipboard_contains_math_structure_and_escaped_prose(self):
        mathml,html=clipboard_payload([{'kind':'text','text':'<script>中文</script>'},formula()])
        parsed=parse_mathml(mathml)
        self.assertTrue(parsed.xpath('.//*[local-name()="mfrac"]'))
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertNotIn('<img',html)

    def test_docx_contains_real_native_math_not_picture(self):
        with tempfile.TemporaryDirectory() as directory:
            path=write_docx([{'kind':'text','text':'行内 '},formula(display=False),formula(MATRIX)],Path(directory)/'test.docx')
            with zipfile.ZipFile(path) as archive:
                doc=ET.fromstring(archive.read('word/document.xml'))
                self.assertEqual(len(doc.xpath('.//m:oMath',namespaces=NS)),2)
                self.assertEqual(len(doc.xpath('.//m:f',namespaces=NS)),1)
                self.assertTrue(doc.xpath('.//m:m',namespaces=NS))
                self.assertFalse(doc.xpath('.//*[local-name()="drawing" or local-name()="object"]'))
                self.assertFalse(any('media/' in name for name in archive.namelist()))
                self.assertIn('α',''.join(doc.itertext()))

    def test_no_office_installed_fallback_retains_math_structure(self):
        with patch('mixsnip.office.office_transform',return_value=None):
            self.assertEqual(len(to_omml(FRACTION).xpath('.//m:f',namespaces=NS)),1)
            self.assertEqual(len(to_omml(MATRIX).xpath('.//m:m',namespaces=NS)),1)

    def test_failed_export_leaves_existing_file_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'existing.docx'
            path.write_bytes(b'untouched')
            with self.assertRaises(ValueError):write_docx([formula('<math/>')],path)
            self.assertEqual(path.read_bytes(),b'untouched')


if __name__=='__main__':unittest.main()
