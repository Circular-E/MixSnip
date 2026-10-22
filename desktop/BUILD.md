# 开发与打包

使用 Windows x64、Python 3.12，从仓库根目录执行：

```powershell
py -3.12 -m venv desktop/.venv
desktop/.venv/Scripts/python.exe -m pip install -r desktop/source/build-requirements.lock.txt
desktop/.venv/Scripts/python.exe -m unittest discover -s desktop/source -p 'test_*.py' -v
```

将正式 Release 中的 `onnx/`、`formula-runtime/`、`models/PP-FormulaNet_plus-M/` 复制到 `desktop/`，然后执行 `desktop/.venv/Scripts/python.exe desktop/source/main.py`。不要复制个人 data。

## 从官方资源准备本地依赖

- MixTeX：[官方 v3.2.4 发布包](https://github.com/RQLuo/MixTeX-Latex-OCR/releases/tag/MixTeX-v3.2.4)，使用完整 `onnx/`。
- FormulaNet M：[官方模型归档](https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-FormulaNet_plus-M_infer.tar)。解压后将三个 inference 文件放在 `desktop/models/PP-FormulaNet_plus-M/`，校验值见 `licenses/formula/model-provenance.json`。
- Python：[CPython 3.12.10 x64 embeddable](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip)，完整解压到 `desktop/formula-runtime/`。
- 在另一个标准 Python 3.12 venv 安装 `source/formula-requirements.lock.txt`，将其 `Lib/site-packages` 复制到 `formula-runtime/Lib/site-packages`，排除 pip 和 __pycache__，保留许可证及 dist-info。
- `formula-runtime/python312._pth` 内容：

```text
python312.zip
.
Lib/site-packages
import site
```

验证：`desktop/formula-runtime/python.exe -I -c "import paddle; print(paddle.__version__)"`。该环境不依赖系统 Python 或 PATH，执行 `source/formula_worker.py`。

## 桌面打包

```powershell
desktop/.venv/Scripts/python.exe -m PyInstaller --noconfirm --workpath desktop/.build --distpath desktop/dist desktop/source/MixSnip.spec
```

将 `onnx/`、`models/`、`formula-runtime/`、`source/`、`licenses/`、`examples/` 和本目录 README.md 复制到 `desktop/dist/MixSnip/`。**source/formula_worker.py 是运行时组件，不可省略。** PyInstaller 输出不要指向正在运行的软件或个人数据目录。

```powershell
desktop/.venv/Scripts/python.exe desktop/scripts/package_release.py --app desktop/dist/MixSnip --output desktop/releases/MixSnip-0.3.0-windows-x64-portable.zip
```

打包脚本使用组件白名单，排除个人 data、日志、字节码与凭据文件，验证 ZIP CRC 和组件，并生成 SHA-256。`git archive --format=zip HEAD` 可生成完整对应源码包。模型、运行库和 ZIP 只放 GitHub Releases，不放 Git 历史。
