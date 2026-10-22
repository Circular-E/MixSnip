"""Persistent offline Paddle worker; launched only by MixSnip's engine adapter."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['OMP_NUM_THREADS'] = '4'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--name', required=True, choices=['PP-FormulaNet_plus-M','PP-FormulaNet_plus-L'])
    args = parser.parse_args()
    model_path = Path(args.model).resolve()
    if not (model_path/'inference.pdiparams').is_file():
        raise FileNotFoundError(model_path)
    from paddleocr import FormulaRecognition
    model = FormulaRecognition(model_name=args.name, model_dir=str(model_path),
                               device='cpu', cpu_threads=4, enable_mkldnn=False)
    for line in sys.stdin.buffer:
        job = json.loads(line.decode('utf-8'))
        target = Path(job['result'])
        try:
            result = list(model.predict(input=job['image'], batch_size=1))[0]
            payload = {'latex':result['rec_formula']}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            payload = {'error':str(error)}
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        temporary.replace(target)


if __name__ == '__main__':
    main()
