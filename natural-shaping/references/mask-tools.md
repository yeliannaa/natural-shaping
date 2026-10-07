# 可选的本地主体蒙版

[build_subject_mask.py](../scripts/build_subject_mask.py)只生成可见主体的覆盖率蒙版，不重写源照片 RGB、不上传照片、不恢复遮挡后的身体或服装。它用于局部调整和背景处理的起稿；已有可靠蒙版时无需重复推理。

## 环境重建

本包不包含 Python 环境、模型权重或模型缓存。先按[移植说明](portability.md)解析当前技能根、授权任务根和缓存位置。在任务目录建立独立环境，避免改系统 Python 包。

- [mask-requirements-lock.txt](../scripts/mask-requirements-lock.txt)是历史 Windows / Python 3.13.2 / CPU 环境的完整版本快照，主要依赖为 `rembg==2.0.85` 与 `onnxruntime==1.30.0`。它是复现起点，不代表所有平台都可安装或这些版本永远最新。
- 同平台可先使用锁文件；其他平台或 Python 版本若无兼容 wheel，按官方支持范围重新解析依赖，在新环境验证后记录自己的锁文件，不能宣称沿用原验证结果。
- 默认明确选择 `birefnet-general-lite`，历史权重约 214 MiB，SHA-256 为 `5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333`。首次使用可能下载权重；随后推理在本机进行。下载、许可及缓存位置按当前环境处理。
- 不安装 CUDA、不使用默认云后端。脚本也支持 `birefnet-portrait` 与 `u2netp`，但不能把 lite 的质量和耗时证据归给其他模型。

下面安装示例存为任务目录中的 `.ps1`，通过参数传入目录；运行前确认安装和下载属于当前授权范围。不要每次修图重复安装。

```powershell
param(
  [Parameter(Mandatory=$true)][string]$SkillRoot,
  [Parameter(Mandatory=$true)][string]$JobRoot
)
$retouchSkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$retouchJobRoot = (Resolve-Path -LiteralPath $JobRoot).Path
$maskEnv = Join-Path $retouchJobRoot '.mask-venv'
python -m venv $maskEnv
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
$maskPython = Join-Path $maskEnv 'Scripts/python.exe' # POSIX: bin/python
& $maskPython -m pip install -r (Join-Path $retouchSkillRoot 'scripts/mask-requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Mask dependency installation failed' }
```

来源：[rembg 固定版本说明](https://github.com/danielgatis/rembg/blob/v2.0.85/README.md)、[rembg 2.0.85](https://pypi.org/project/rembg/2.0.85/)、[BiRefNet 许可证](https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE)、[ONNX SessionOptions](https://onnxruntime.ai/docs/api/python/api_summary.html#onnxruntime.SessionOptions)。链接供核对，打包不等于当前会话已经访问来源。

## 调用与验收

先用 `--help` 查看参数；正常任务 `--repeat 1`，只在测同进程 session 复用时设为 2。多张输入可同一次 `--input` 传入；两次 CLI 调用不会共享 session。

```powershell
param(
  [Parameter(Mandatory=$true)][string]$SkillRoot,
  [Parameter(Mandatory=$true)][string]$JobRoot,
  [Parameter(Mandatory=$true)][string]$InputPhoto,
  [Parameter(Mandatory=$true)][string]$MaskPython
)
$retouchSkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$retouchJobRoot = (Resolve-Path -LiteralPath $JobRoot).Path
$maskInput = (Resolve-Path -LiteralPath $InputPhoto).Path
$maskOutput = Join-Path $retouchJobRoot 'mask-run-01'
if (Test-Path -LiteralPath $maskOutput) { throw 'Use a new mask run directory' }
& $MaskPython (Join-Path $retouchSkillRoot 'scripts/build_subject_mask.py') `
  --input $maskInput --output-dir $maskOutput `
  --cache-dir (Join-Path $retouchJobRoot 'model-cache') `
  --model birefnet-general-lite --memory-mode bounded --threads 2
if ($LASTEXITCODE -ne 0) { throw 'Mask run failed; inspect its report before retrying' }
```

输出为按源 EXIF 方向对齐的原尺寸 `L` / 8 位软蒙版，以及小尺寸、色彩管理后的检查预览和 `mask-run.json`。蒙版表示覆盖率，不是颜色，不嵌 ICC，也不得套用色彩转换。源文件的 EXIF、ICC 与像素只读。需要原尺寸细部证据时，用 `--roi name:left,top,right,bottom` 提供实际画布坐标。

首份蒙版和报告在重复推理前写盘；后续 warm 测试失败时可保留首份结果，但整体运行会报告失败。默认 bounded 策略关闭 ONNX arena/pattern 缓存并采用顺序执行，以减少与大型 PSD 同开时的内存竞争；不保证任意机器均无内存问题。

历史单张 3072×4080 测试中，lite 的默认 bounded / 2线程首遍约 10.8 秒；这些秒数不包含下载、导入、预览、PS 补边和验收，也不是朋友机器上的性能承诺。原始测试记录不随共享包分发；迁移后应记录自己的完整耗时与结果。

采用前检查头发、蕾丝、服装缎带、手、道具、鞋底和接地。近零背景残余、灰色纸片误选、边缘色污染都可能存在；软 alpha 不等于真实半透明发丝，不能自动二值化整张蒙版。导入 PS 时验证尺寸、方向与坐标，把蒙版放到可撤销图层或 Alpha 通道，保留源图。
