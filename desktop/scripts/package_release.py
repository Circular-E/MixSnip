"""Create a clean offline portable ZIP, excluding personal OCR history."""
from pathlib import Path
import argparse
import hashlib
import zipfile

FOLDERS={'_internal','onnx','models','formula-runtime','source','licenses','examples'}
FILES={'MixSnip.exe','README.md','使用说明.md','界面预览.png','Data界面预览.png'}


def allowed(relative):
    if relative.parts[0] not in FOLDERS and not (len(relative.parts)==1 and relative.name in FILES):
        return False
    return not any(p in {'__pycache__','.git','.env'} for p in relative.parts) and relative.suffix.lower() not in {'.pyc','.pyo','.log','.sqlite3','.tmp'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();app=args.app.resolve();output=args.output.resolve()
    if output.is_relative_to(app):raise ValueError('Output must be outside app folder')
    required=['MixSnip.exe','source/main.py','source/formula_worker.py','source/MixSnip.spec',
              'formula-runtime/python.exe','models/selected.json','models/PP-FormulaNet_plus-M/inference.pdiparams',
              'onnx/encoder_model.onnx','onnx/decoder_model_merged.onnx','licenses/MixTeX-upstream-terms.md']
    for name in required:
        if not (app/name).is_file():raise FileNotFoundError(name)
    paths=sorted(p for p in app.rglob('*') if p.is_file() and allowed(p.relative_to(app)))
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.partial')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for i,path in enumerate(paths):
            if path.is_symlink():raise ValueError('Release may not contain symlinks')
            archive.write(path,'MixSnip/'+path.relative_to(app).as_posix())
            if i%2000==0:print(f'{i}/{len(paths)} files',flush=True)
    with zipfile.ZipFile(temporary) as archive:
        assert not any(n.startswith('MixSnip/data/') for n in archive.namelist())
        assert all('MixSnip/'+p in archive.namelist() for p in required)
        error=archive.testzip()
        if error:raise IOError('ZIP CRC error: '+error)
    temporary.replace(output)
    with output.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(f'Verified {len(paths)} files, {output.stat().st_size} bytes, SHA256 {digest}',flush=True)


if __name__=='__main__':main()
