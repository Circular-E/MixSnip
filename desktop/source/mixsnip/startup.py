"""Current-user Windows logon startup; changes only MixSnip's own entry."""
from pathlib import Path
import subprocess
import sys

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'MixSnip'


def command():
    if getattr(sys, 'frozen', False):
        args = [str(Path(sys.executable).resolve()), '--background']
    else:
        python = Path(sys.executable).resolve()
        windowless = python.with_name('pythonw.exe')
        args = [str(windowless if windowless.is_file() else python),
                str(Path(__file__).resolve().parents[1]/'main.py'), '--background']
    return subprocess.list2cmdline(args)


def enabled():
    if sys.platform != 'win32':
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
        return kind == winreg.REG_SZ and value == command()
    except OSError:
        return False


def set_enabled(enable):
    if sys.platform != 'win32':
        raise OSError('开机自启动目前仅支持 Windows。')
    import winreg
    if enable:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
