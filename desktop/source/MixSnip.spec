# Build with: python -m PyInstaller --clean --noconfirm MixSnip.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs

src = Path(SPECPATH)
a = Analysis(
    [str(src/'main.py')],
    pathex=[str(src)],
    binaries=collect_dynamic_libs('onnxruntime'),
    datas=[(str(src/'assets'),'assets')],
    hiddenimports=['onnxruntime','tokenizers'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['torch','tensorflow','transformers','matplotlib','IPython','pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='MixSnip',debug=False,
          bootloader_ignore_signals=False,strip=False,upx=False,console=False,
          icon=str(src/'assets/app.ico'))
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='MixSnip')
