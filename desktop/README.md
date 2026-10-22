# MixSnip

Windows 本地公式识别桌面软件，0.3.0 默认使用 PP-FormulaNet_plus-M，设置中可切回 MixTeX。参考 Mathpix Snip 的截图、结果编辑、预览、复制和历史操作流程，使用独立名称与图标。

## 启动

双击本文件旁的 **MixSnip.exe**。请保留整个软件文件夹，包括 `_internal`、`onnx`、`models`、`formula-runtime` 和 `source`，不能只把 exe 单独搬走。无需另装 Python、GPU、LaTeX 或配置 API Key。

**黑底公式可以直接截图识别。** FormulaNet 在内部自动把识别副本转为白底，历史原图和 Original 页仍保留黑底，不需要手动反色。第一次识别需加载模型，本机完整流程约 17～21 秒（首次解包后曾达 40 秒）；后续复用模型，通常约 2～4 秒。退出软件或取消识别会释放该进程，下次需要重新加载。

初始截图快捷键是 **Ctrl+Alt+M**。若已被其他程序占用，会依次尝试 **Ctrl+Shift+M**、**Ctrl+Alt+S**，实际生效的快捷键显示在标签栏右侧，也可在右上角设置中切换。本机测试时生效的是 **Ctrl+Shift+M**。

## 日常操作

1. 按截图快捷键，或点击左上角虚线方框。拖动框选公式，松开鼠标开始识别；Esc 或右键取消。多显示器可在任一屏幕内选区，一次选区不跨屏。
2. OCR 标签显示公式预览；Show Original 展开原图；Original 标签查看完整原图。Data 标签保留公式预览，下方可滚动查看 DOCX、MathML (MS Word) 和 MathML；右侧按钮复制对应格式。修改公式请点击顶部键盘图标，或 OCR 页每行右侧的编辑按钮。
3. 默认自动复制 LaTeX。下方四行依次是不带分隔符、`$…$`、`$$…$$` 和 `equation` 环境，每行右侧分别是复制、编辑、放大查看。多公式混排文本保留原有分隔符，避免错误嵌套。
4. 顶部箭头切换历史记录，数字表示当前位置与总数；列表图标打开可搜索的历史窗口，双击记录打开。右上角垃圾桶删除当前记录。

顶部图片图标导入图片，旁边下拉菜单可粘贴图片；笔迹图标打开手写画板，键盘图标用于直接输入 LaTeX。画板使用设置中选择的本地模型，本次样本不足以验证普遍手写能力。

**Copy MS Word** 复制 Office 可编辑公式：点击后，在 Word 的正文插入点或 PowerPoint 的文本框内直接按 **Ctrl+V**。粘贴后可以点击公式修改符号、分子分母、上下标等，无需先按 Alt+=。这个按钮复制的是 MathML 数学结构；下方四行复制按钮仍复制 LaTeX 文本。

**Open DOCX** 生成含原生 Office Math（OMML）公式的 `.docx`，保存在 `data/exports/`，然后用系统关联程序打开。每次生成独立文件，不覆盖之前打开的文档。导出的公式可在 Word 内编辑，也可从 Word 复制到 PPT。公式与文字混排时，DOCX 保留文字及行内／独立公式顺序。

Office 导出全部在本地完成，不调用 API。已在本机 Word 和 PowerPoint 中确认可编辑；其他 Office 版本尚未逐一验证。不完整公式或未知命令会提示修正，不会把图片伪装成可编辑公式。

**Copy PNG** 复制渲染后的公式图片，**Open PNG** 保存到 `data/exports/` 并打开。PDF 入口仍为灰色，本版尚未支持整篇 PDF 转换。底部绿色条表示任务完成状态，并非模型置信度。赞／踩仅保存为本地标记。

也支持拖入图片，或按 **Ctrl+Shift+V** 粘贴剪贴板图片。**Ctrl+O** 导入图片，**Ctrl+Shift+C** 复制当前结果。编辑框内普通 Ctrl+V 用于粘贴文字。主窗口右键菜单提供「重新识别」。

默认关闭窗口后留在系统托盘，快捷键仍然有效。点击托盘图标恢复窗口，右键托盘选择「退出」结束程序。设置中可以取消关闭到托盘。

右上角设置中的 **开机自启动** 可控制登录 Windows 后自动运行。启用后在托盘启动，不弹出主窗口，截图快捷键仍有效；已经运行时不会重复启动。启动项仅写入当前用户的 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，名称为 `MixSnip`，不需要管理员权限。移动软件目录后请重新勾选此设置。窗口内 **Ctrl+Q** 可彻底退出。

## 本地文件

- `onnx/`：MixTeX v3.2.4 原始模型与分词器。
- `models/PP-FormulaNet_plus-M/`：PaddleOCR 官方原始推理模型；`models/selected.json` 指定默认模型。
- `formula-runtime/`：独立的 CPython 3.12.10 与 Paddle CPU 运行库，不依赖电脑上安装的 Python。
- `_internal/`：桌面运行库与离线 MathJax 预览资源。
- `data/history.sqlite3`：历史记录；`data/images/`：历史原图。
- `data/settings.json`：设置；`data/app.log`：错误日志。
- `source/`：完整应用源码、测试、构建配置和依赖版本。
- `licenses/`：上游协议与依赖授权说明。
- `examples/`：用于实际测试的印刷公式样例。

模型、截图、历史和公式预览均在本地处理；应用没有云端识别、账号登录、遥测或自动更新功能。首次识别会加载模型，之后复用已加载的模型。

## 识别边界

本次用 11 张历史截图比较 MixTeX、PP-FormulaNet_plus-M 与 L。其中 8 张印刷公式覆盖 4 类不同公式；按统一白底预处理比较，严格整式正确数分别为 2/8、7/8、7/8，忽略末尾标点后为 2/8、8/8、8/8。M/L 均在最后一张多生成逗号；M 的 CPU 热运行中位数 3.26 秒，L 为 6.54 秒，因此选择 M。详细原图、预测和判定见同级交付目录「识别模型对比」。这不是通用准确率，也不能据此宣称达到 Mathpix 水平。

FormulaNet 擅长公式，纯文字建议切换 MixTeX。历史记录不会自动覆盖，可打开旧记录后右键「重新识别」。软件检测纯色空白图，避免生成不存在的公式；极低质量或复杂截图仍可能误识别。请框选完整单个公式，核对关键符号和末尾标点。预览能正常排版不代表识别正确。

公式预览与 Office 导出使用 MathJax，覆盖常用数学 LaTeX；完整 TeX 文档、自定义宏包或复杂 `tabular` 不等同于 TeX 编译器支持。Office 对部分间距、对齐和字体的显示可能与预览略有不同。本版不含整篇 PDF 排版转换或云同步。

## 从源码运行和构建

在独立 Python 3.12 环境安装 `source/requirements.txt` 后，运行 `python source/main.py`。源码与打包版使用同级 `models` / `formula-runtime`；MixTeX 使用 `onnx/`。FormulaNet 通过隐藏的常驻子进程执行，公式识别不访问网络，支持取消和 180 秒超时。

桌面构建环境锁定版本在 `source/build-requirements.lock.txt`。执行 `python -m PyInstaller source/MixSnip.spec --workpath build --distpath dist` 后，把 `onnx/`、`models/`、`formula-runtime/`、`source/` 和 `licenses/` 一并放入 `dist/MixSnip/`。独立识别环境的依赖入口为 `source/formula-requirements.txt`，完整版本见 `source/formula-requirements.lock.txt`；使用官方 CPython 3.12.10 Windows embeddable runtime，`python312._pth` 包含 `Lib/site-packages` 并启用 `import site`。

运行单元测试：进入 `source/`，执行 `python -m unittest -v test_core.py test_office.py test_startup.py test_engines.py`。

Office 导出实现位于 `source/mixsnip/office.py`：MathJax 生成 MathML，复制时提供 Windows MathML、MathML Presentation、HTML 和 Unicode 文本格式；生成 DOCX 时优先使用本机 Office 自带的 MML2OMML.XSL，未安装 Office 时使用随包的开源 mathml2omml-as 转换器。未分发微软的 XSL 文件。

格式参考：[Microsoft MathML 支持](https://learn.microsoft.com/en-us/office/math/mathml)、[Mathpix Copy MS Word 操作说明](https://website.mathpix.com/docs/snip/snip-with-microsoft-word)。

## 上游与授权

MixTeX 项目：https://github.com/RQLuo/MixTeX-Latex-OCR

PP-FormulaNet / PaddleOCR：https://github.com/PaddlePaddle/PaddleOCR 。模型来自官方 BOS 推理模型发布地址；模型配置与权重未修改。PaddleOCR 使用 Apache-2.0，许可证与运行库依赖清单在 `licenses/formula/`。CPython 许可证随 `formula-runtime/` 保留。

参考源码提交：`845d0d75b5f55185ee088cf68dc57d5eb3d0f10b`。模型来自官方 `MixTeX-v3.2.4` 发布包。推理逻辑根据上游代码改造：保留预处理和贪心解码，按模型配置适配层数，增加后台执行、取消与结果状态；整段解码避免中文 UTF-8 拆分问题。

应用衍生代码采用 AGPL-3.0，保留上游作者 Renqing Luo / RQLuo 的署名。上游另外附有“模型衍生品不得用于商业用途”的条款，原文完整保存在 `licenses/MixTeX-upstream-terms.md`。本交付为本地个人使用版本。
