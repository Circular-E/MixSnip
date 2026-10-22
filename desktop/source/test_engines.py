import tempfile
import threading
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from mixsnip.engines import FormulaNet, normalize_formula


class EngineTests(unittest.TestCase):
    def test_dark_formula_and_transparent_strokes_become_black_on_white(self):
        dark = Image.new('RGB',(80,40),(20,20,20))
        ImageDraw.Draw(dark).line((15,20,65,20),fill='white',width=2)
        normalized = normalize_formula(dark)
        self.assertGreaterEqual(min(normalized.getpixel((0,0))),254)
        self.assertEqual(normalized.getpixel((30,20)),(0,0,0))
        transparent = Image.new('RGBA',(80,40),(0,0,0,0))
        ImageDraw.Draw(transparent).line((15,20,65,20),fill=(0,0,0,255),width=2)
        composited=normalize_formula(transparent)
        self.assertEqual(composited.getpixel((0,0)),(255,255,255))
        self.assertEqual(composited.getpixel((30,20)),(0,0,0))

    def test_blank_and_precancelled_requests_do_not_start_worker(self):
        with tempfile.TemporaryDirectory() as root:
            engine = FormulaNet('M',root=root)
            for color in ['white','black']:
                self.assertEqual(engine.recognize(Image.new('RGB',(50,30),color),threading.Event())[1],'empty')
            cancel = threading.Event();cancel.set()
            self.assertEqual(engine.recognize(Image.new('RGB',(50,30),'red'),cancel)[1],'cancelled')
            self.assertIsNone(engine.process)
            engine.close()

    def test_missing_runtime_has_recovery_instructions(self):
        with tempfile.TemporaryDirectory() as root:
            engine = FormulaNet('M',root=Path(root))
            image=Image.new('RGB',(50,30),'white')
            ImageDraw.Draw(image).line((10,15,40,15),fill='black')
            with self.assertRaisesRegex(FileNotFoundError,'MixTeX'):
                engine.recognize(image,threading.Event())
            engine.close()


if __name__=='__main__':unittest.main()
