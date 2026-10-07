# natural-shaping · 自然美型

面向人像与 Cos 照的修图 skill，指导构图分析、肤质与五官精修、协调身形、背景与光线处理，以及修后验收。强调保留身份、角色妆造、关节和道具结构；它提供工作方法与辅助脚本，不自带修图软件或像素蛋糕算法。

## 安装与使用

将仓库中的整个 [`natural-shaping/`](natural-shaping/) 文件夹放入目标应用支持的技能目录，保持内部目录结构；不要只复制 `SKILL.md`。不需要另外安装原作者的其他修图 skill。首次使用先阅读[移植说明](natural-shaping/references/portability.md)，确认应用已识别技能，再用合成小图测试实际要用的执行路线。

提供照片、希望改善的地方和保存位置。每张新图或完整重修，都应先解释构图，展示基于原片的标注草图，等你确认当前方案后才开始精修。同一方案内的局部返修沿用已有确认。源图保持只读，产物保存在授权任务目录，不写入技能安装目录。

## 外部能力

- 诊断与验收需要本地文件读取、看图能力。
- 原生精修需要 Photoshop 及能够执行 ExtendScript 的连接；其他版本或环境需先验证。
- 局部生成需要当前应用提供的图像编辑能力；包内不附模型、账户或密钥，不固定生图型号。
- 交互对照需要应用的可视化能力；没有时使用等尺度静态对照。
- PNG 检查需要 PowerShell；无损压缩需要 Python 3.11+。自动主体蒙版是可选功能，其独立环境及模型按[说明](natural-shaping/references/mask-tools.md)另行准备。

## 校验与参考资料

在仓库根目录运行：

```sh
python natural-shaping/scripts/validate_portable.py
```

校验脚本从自身位置定位技能根，检查文件清单、SHA256 和显式本地引用，不联网、不修图、不写包内文件。检查通过不代表图像效果或外部执行环境已经验收；当前包内容以 `natural-shaping/package-manifest.json` 为准。

包内[成片示例](natural-shaping/assets/examples/README.md)、[历史局部案例](natural-shaping/references/cases/README.md)和教程操作帧用于理解风格与失败边界。蕾姆效果以 v12 为入口，旧图单独归入历史过程；新增神里、知更鸟、爱莉希雅及三张狩司司的已保存示例并逐张标注状态。历史记录区分失败、阶段候选、技术检查及用户认可，不能把局部通过当作全图认可，也不能重放旧图坐标。资料按问题读取；保留外部来源链接不等于每次使用都会重新访问或观看。更多流程见 [`SKILL.md`](natural-shaping/SKILL.md)。
