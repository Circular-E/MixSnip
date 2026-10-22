import tempfile
import threading
import unittest
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QRect,QSize
from mixsnip.core import History, prepare_image, copy_text, strip_math, MixTeX
from mixsnip.capture import pixel_rect


class CoreTests(unittest.TestCase):
    def test_copy_does_not_corrupt_multiple_equations(self):
        text=r'\[a=b\] and \[c=d\]'
        self.assertEqual(copy_text(text,'bare'),text)
        self.assertEqual(copy_text(text,'display'),text)
        self.assertEqual(copy_text('$$x^2$$','bare'),'x^2')
        self.assertEqual(copy_text(r'\[x^2\]','inline'),'$x^2$')
        self.assertEqual(copy_text('x^2','display'),'$$\nx^2\n$$')

    def test_transparent_images_are_white_and_aspect_is_preserved(self):
        image=Image.new('RGBA',(896,112),(0,0,0,0))
        image.paste((0,0,0,255),(0,0,448,112))
        result=prepare_image(image)
        self.assertEqual(result.size,(448,448))
        self.assertEqual(result.getpixel((0,0)),(255,255,255))
        self.assertEqual(result.getpixel((10,220)),(0,0,0))
        self.assertEqual(result.getpixel((400,220)),(255,255,255))

    def test_history_survives_restart_and_interrupt(self):
        with tempfile.TemporaryDirectory() as folder:
            history=History(Path(folder))
            key=history.add(Image.new('RGB',(32,32),'white'))
            interrupted=history.add(Image.new('RGB',(32,32),'white'))
            history.result(key,r'\alpha=1','done',2.3)
            history.edit(key,r'\alpha=2')
            history.close()
            history=History(Path(folder))
            self.assertEqual(history.get(key)['latex'],r'\alpha=2')
            self.assertEqual(history.get(interrupted)['status'],'interrupted')
            self.assertEqual(len(history.list('alpha')),1)
            path=Path(folder)/history.get(key)['image']
            history.delete(key)
            self.assertFalse(path.exists())
            self.assertIsNone(history.get(key))
            history.close()

    def test_dpi_crop_maps_logical_to_physical_pixels(self):
        self.assertEqual(pixel_rect(QRect(10,20,100,50),QSize(1000,800),QSize(1500,1200)),QRect(15,30,150,75))
        self.assertEqual(pixel_rect(QRect(-10,0,40,20),QSize(100,100),QSize(200,200)),QRect(0,0,60,40))

    def test_missing_model_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(FileNotFoundError,'onnx'):
                MixTeX(Path(folder)).load()


if __name__=='__main__':
    unittest.main()
