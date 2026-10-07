# natural-shaping · 自然美型

**人像精修与 Cosplay 修图 Skill for Codex · Portrait & cosplay photo retouching**

面向人像修图、漫展场照精修与 Cos 后期的可移植技能：先拆解构图、展示原片标注草图，确认后再精修肤质、五官、身形、光线与背景。保留本人感、角色妆造、关节和道具结构，并主动检查修后瑕疵。

A reusable **photo retouching agent skill** for Codex, focused on **portrait retouching** and **cosplay photo editing**. The workflow is defined in [`natural-shaping/SKILL.md`](natural-shaping/SKILL.md): source-based composition sketches, identity-preserving refinement and visual quality checks, with **Photoshop ExtendScript (JSX)** helpers. Editing requires the tools available in your environment.

[安装与使用](#安装与使用) · [常见修图问题](#常见修图问题faq) · [按问题看案例](#按问题看案例) · [构图草图](#构图草图composition-sketches) · [10 张示例与版本状态](natural-shaping/assets/examples/README.md) · [完整流程](natural-shaping/SKILL.md)

## 能做什么

| 方向 | 工作内容 |
|---|---|
| 构图与沟通 | 分析留白、动作路径、画边与遮挡；给出可比较的原片草图，确认后执行 |
| 人像精修 | 分别判断肤质、五官、肩颈、腰腹及腿脚比例，保护身份和妆造 |
| 光线与背景 | 肤色与彩光衔接、按景深弱化路人、处理具体干扰并保留现场感 |
| 道具与验收 | 联看手、衣带、球拍等完整连接；查新增损伤、原尺寸细节与实际交付文件 |

包内提供方法、参考图和辅助脚本。修图效果取决于执行工具与实际验收；不包含像素蛋糕算法、Photoshop 软件或生图模型。

## 构图草图｜Composition sketches

以下是基于**精修前原片**的完整方案拆解示例：构图、肤质五官、肩颈腰腿、光线背景、衣装道具与验收一起说明。F/W/L 标出检查区域，照片未重新精修；历史已选方案与新增教学建议分别标明。

### Cos 交叠腿坐姿：裁顶补底与腰线协调｜狩司司 114

比较 A/B 裁顶补底；同时拆解肤质五官、肩颈腰线、光色与杂物清理，保留交叠膝和脚形。

[![狩司司114原片A与拟裁顶补底B的构图草图](natural-shaping/assets/evidence/composition/shousisi-114-retouch-plan-v2.png)](natural-shaping/references/composition-and-key-elements.md#狩司司-114-号用-ab-解释裁顶与少量补底)

### Cos 坐姿精修：收腰、腿部比例与球拍保护｜狩司司 110

联看白墙、观众与持拍动线；说明收腰腹、腿部比例、脸颈手光色，以及球拍结构验收。

[![狩司司110原幅构图草图，标注动作路径、背景干扰和保护范围](natural-shaping/assets/evidence/composition/shousisi-110-retouch-plan-v2.png)](natural-shaping/references/composition-and-key-elements.md#狩司司-110-号动线遮挡与道具补全边界)

点击图片阅读[完整拆解与取舍](natural-shaping/references/composition-and-key-elements.md#示例草图的制作与展示)。图片为静态方案示意；具体裁幅、调整范围与历史确认仅适用于对应照片。

## 常见修图问题｜FAQ

### 自然磨皮怎样保留皮肤纹理？｜Skin retouching

先区分局部瑕疵、噪点、真实肌理和角色妆面，再分别处理肤质、明暗与肤色。自然磨皮（skin smoothing）的目标是皮肤细腻且可信，眼妆、唇部纹理与本人特征仍清楚；放大复查涂抹感、灰边及脸颈色差。方法见[肤质与五官精修](natural-shaping/references/portrait-beauty.md)。

### 可以瘦脸、收腰／瘦腰和拉腿吗？｜Body reshaping

支持按本图确认范围评估脸型与身形优化：先区分透视、姿态、光影和真实轮廓，再决定局部几何调整。收腰、拉腿要联看胸腰髋、膝踝、脚形及背景直线，保护衣纹、饰件和关节，不套固定 V 脸或统一幅度。当前辅助脚本没有自动身体识别或液化接口；实际执行取决于连接的编辑工具。见[身形与姿态](natural-shaping/references/shape-and-pose.md)。

### Cos 场照怎样做路人虚化、肤色统一与调色？｜Background blur & color grading

按景深、明暗和色彩弱化路人，让人物更突出并保留现场感。背景虚化（background blur）要检查发缘与道具边界；调色（color grading）联看脸、颈、手、假发和服装，避免肤色断层或彩光来源不合理。具体遮挡是否清理另行判断。见[光色与边缘](natural-shaping/references/tone-and-edges.md)。

### 手、衣带、道具或画边缺失，可以局部补全吗？

优先使用真实原像素与相容参考，缺失内容明确标为推断。按确认范围试修后，检查整条连接、握持、透视、材质和接缝；结构仍不可靠时保留稳定版本并说明问题。见[结构复核与局部生成](natural-shaping/references/structure-review-and-generation.md)。

### 需要哪些工具？能直接一键修图吗？

本包提供流程、参考和辅助脚本。看图诊断需要文件读取和图像查看能力；原生 PS 精修需要 Photoshop 与可执行 ExtendScript 的连接；局部生成需要当前环境另外提供图像编辑能力。安装 skill 不会同时安装 Photoshop 或配置工具连接。支持 Agent Skills 文件格式，不代表所有客户端的实际修图路线都已验证。见[迁移与能力检查](natural-shaping/references/portability.md)。

### 同组照片可以批量修图吗？

先完成代表片，再复用适合该组的基础色调和处理结构。每张照片的构图、曝光、蒙版、几何范围与位移仍需重定并验收，新图草图确认规则继续适用；不承诺自动识别人脸后整组一键同步。见[同组处理方法与边界](natural-shaping/references/pixcake-cos-workflow.md)。

## 按问题看案例

案例包含获认可成片、已保存候选及失败返修；标题表示研究的问题，结果状态逐项标明。

| 想解决的问题 | 处理方式与案例入口 | 已知结果 |
|---|---|---|
| 磨皮之后，五官、身形和整体质感仍不够精致 | [dora 与蕾姆成片示例](natural-shaping/assets/examples/README.md) | 当前示例：dora v7、蕾姆 v20；不作为拉腿效果证明 |
| 彩光调色后出现粉边、颗粒和假发切面 | [蕾姆：按光源和材料校正彩光、接回发缘](natural-shaping/references/personal-cases.md#ns04蕾姆当前效果与历史粉光问题) | 当前示例：蕾姆 v20 |
| 收腰、拉腿和球拍补全怎样保持坐姿可信 | [狩司司：整体比例、握持与球拍透视一起复核](natural-shaping/references/personal-cases.md#ns10狩司司三张已保存示例与球拍返修) | 110 v4 已返修保存；未记录用户最终认可 |
| 手、衣带与衣缘补完仍不自然 | [宫本樱：多视角定位，再锁定结构做材质收尾](natural-shaping/references/personal-cases.md#ns09宫本樱-v8-结构认可--v9-材质收尾与指定目录交付2026-10-06) | v8 整体与位置获认可，v9 获保存指示 |
| 鼻旁阴影显硬，是否需要直接瘦鼻 | [鼻旁局部：先柔化光影，再判断鼻形](natural-shaping/references/personal-cases.md#ns03鼻旁先柔光不默认改变鼻形) | 柔光效果获局部认可；该次未新增鼻形几何修改 |
| 群像补鞋不可靠，人物气色又不一致 | [群像：撤回补鞋、保留稳定取景，逐人检查肤色与唇色](natural-shaping/references/personal-cases.md#ns12群像111补鞋撤回气色漏检与派生层2026-10-07) | 补鞋／下扩已撤回；当前示例：群像 111 v4 |

## 安装与使用

下载或克隆本仓库，将整个 [`natural-shaping/`](natural-shaping/) 文件夹放入目标应用支持的技能目录，保持内部目录结构；不要只复制 `SKILL.md`。不需要另外安装原作者的其他修图 skill。首次使用先阅读[移植说明](natural-shaping/references/portability.md)，确认应用已识别技能，再用合成小图测试实际要用的执行路线。

也可以通过 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 安装。以下固定版本命令需要 Node.js 22.20.0 或更高版本；先列举仓库中的技能：

```sh
npx skills@1.7.1 add yeliannaa/natural-shaping --list
```

在目标项目目录中，为 Codex 复制安装该技能：

```sh
npx skills@1.7.1 add yeliannaa/natural-shaping --skill natural-shaping --agent codex --copy --yes
```

**安装验证（2026-10-07）**：独立 Windows 测试项目使用 Node.js 22.20.0、Skills CLI 1.7.1，识别出一个 `natural-shaping`，项目安装至 `.agents/skills/natural-shaping`；364 个文件的清单、哈希和本地引用通过包内校验。此项验证覆盖技能发现与复制安装，实际 Photoshop 连接和其他客户端执行能力仍按迁移说明检查。

仓库可直接安装与 skills.sh 目录收录是不同状态。本次 `skills find natural-shaping` 暂未返回条目；目录按真实安装遥测形成收录和排名，详见 [skills.sh 收录说明](https://skills.sh/docs/faq)。测试已关闭遥测，不把安装验证计作真实使用。

在支持 `$` 调用的 Codex 环境中，可提供照片或文件夹并这样请求：

```text
$natural-shaping 请先拆解这张 Cos 照的构图，展示基于原片的方案草图。
等我确认后，再精修肤质、五官、身形、背景和光线，并保存到我指定的目录。
```

每张新图或完整重修，应先展示草图并等待确认。同一方案内的局部返修沿用已有确认。源图保持只读，照片、PSD 和预览保存在本次任务目录，不写入技能安装目录。

**Quick start:** Copy the complete `natural-shaping/` folder into the skill location supported by your application. Provide a photo and output directory, invoke the skill, review the composition sketch, then confirm the editing scope. See [portability and dependencies](natural-shaping/references/portability.md) before using the scripts.

## 工具与能力边界

- 看图诊断与验收需要文件读取、图像查看能力。
- 原生精修需要 Photoshop 及能够执行 ExtendScript 的连接。包内 runtime 提供曲线、颜色层、蒙版、预览和导出；没有自动身体识别或液化接口。
- 局部生成需要当前应用提供的图像编辑能力；不附模型、账户、密钥或固定生图型号。
- 交互对照依赖应用的可视化能力；没有时使用等尺度静态对照。
- PNG 检查需要 PowerShell；无损压缩需要 Python 3.11+。自动主体蒙版是可选功能，其环境和模型按[蒙版说明](natural-shaping/references/mask-tools.md)另行准备。

## 示例、资料与校验

[成片示例目录](natural-shaping/assets/examples/README.md)包含蕾姆、dora、宫本樱、群像、神里、知更鸟、爱莉希雅和三张狩司司，共 10 张指定版本 JPG。逐张区分用户认可、保存交付与待完善状态；历史失败局部见[cases 索引](natural-shaping/references/cases/README.md)。

在仓库根目录运行：

```sh
python natural-shaping/scripts/validate_portable.py
```

校验脚本检查文件清单、SHA256 和显式本地引用，不联网、不修图、不写包内文件。检查通过不代表图像效果或外部工具已验收；当前包内容以 `natural-shaping/package-manifest.json` 为准。

资料按问题读取，外部链接保留出处，不会每次重新访问全部网页或视频。教程观察与向 PS 迁移的判断分别记录，详见[像素蛋糕方法参考](natural-shaping/references/pixcake-cos-workflow.md)。
