import sys
import unittest
from unittest.mock import patch,MagicMock
from pathlib import Path
import subprocess
from mixsnip import startup


class StartupTests(unittest.TestCase):
    def test_packaged_command_quotes_spaces_and_starts_in_background(self):
        exe=str(Path('C:/My Apps/MixSnip/MixSnip.exe').resolve())
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',exe):
            self.assertEqual(startup.command(),subprocess.list2cmdline([exe,'--background']))

    @unittest.skipUnless(sys.platform=='win32','Windows registry')
    def test_enable_writes_only_current_user_mixsnip_entry(self):
        import winreg
        with patch.object(winreg,'CreateKey') as create,patch.object(winreg,'SetValueEx') as write:
            startup.set_enabled(True)
            create.assert_called_once_with(winreg.HKEY_CURRENT_USER,startup.RUN_KEY)
            self.assertEqual(write.call_args.args[1:],('MixSnip',0,winreg.REG_SZ,startup.command()))

    @unittest.skipUnless(sys.platform=='win32','Windows registry')
    def test_disable_removes_only_mixsnip_value(self):
        import winreg
        with patch.object(winreg,'OpenKey'),patch.object(winreg,'DeleteValue') as delete:
            startup.set_enabled(False)
            self.assertEqual(delete.call_args.args[1],'MixSnip')
        with patch.object(winreg,'OpenKey',side_effect=FileNotFoundError):
            startup.set_enabled(False)

    @unittest.skipUnless(sys.platform=='win32','Windows registry')
    def test_enabled_detects_exact_current_installation(self):
        import winreg
        with patch.object(winreg,'OpenKey'),patch.object(winreg,'QueryValueEx',return_value=(startup.command(),winreg.REG_SZ)):
            self.assertTrue(startup.enabled())
        with patch.object(winreg,'OpenKey'),patch.object(winreg,'QueryValueEx',return_value=('another.exe',winreg.REG_SZ)):
            self.assertFalse(startup.enabled())


if __name__=='__main__':unittest.main()
