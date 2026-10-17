# 公开教程与案例展示

[打开教程站](https://yeliannaa.github.io/natural-shaping/) · [第一次修一张](https://yeliannaa.github.io/natural-shaping/first-photo.html)

本目录是供使用者阅读的静态教程站，由 GitHub Pages 从 `main` 分支的 `/docs` 发布。安装技能时仍复制完整的 `natural-shaping/` 目录；展示站不是技能执行依赖。

进阶方法与可选参考另见[高P精修](../natural-shaping/references/highp-retouch.md)、[公开审美参考库](../natural-shaping/references/aesthetic-reference/README.md)和[发丝清理](../natural-shaping/references/tone-and-edges.md#杂毛与飞丝清理)。这些资料随技能包提供，不要求新使用者配置原作者的私人库或本地模型。

| 页面 | 内容 |
|---|---|
| `index.html` | 蕾姆、群像、宫本樱代表效果，瑶高P双例，以及狩司司双草图入口 |
| `first-photo.html` | 安装、提供原片、草图确认、修图与实际文件交付 |
| `rem.html` / [rem.md](rem.md) | 遮挡、坐姿、彩光、发缘、手腕袖口与相机连接 |
| `group.html` / [group.md](group.md) | 三人构图、逐人气色、眼妆与脸颈、道具及画边补全 |
| `sakura.html` / [sakura.md](sakura.md) | 腰腹、双侧双带、手指、衣缘与贴肤材质 |
| `highp.html` / [highp.md](highp.md) | 瑶高P双图的编号标注复盘、全局光线与脸妆细节、Image＋PS实际尺寸链及详细控制入口 |
| `shousisi.html` | 110 与 114 既有构图草图及更细的保护、取舍与验收说明 |

三个代表案例各有八项观察与判断、四组局部对照和四项验收重点。图片是公开教学预览；完整成片与其状态见[示例目录](../natural-shaping/assets/examples/README.md)。整图看构图与光色，点击局部放大观察妆面、材质和连接。

## 素材与后续维护

- `assets/*-source.jpg` 与 `*-final.jpg` 是长边 1600px 的网页预览，已移除私人文件路径和拍摄元数据；原始文件未覆盖。
- `assets/*-detail-*.jpg` 从对应原尺寸素材裁取，再缩小到长边最多 900px；只作展示，不另行锐化或精修。
- `assets/yao-highp-*.jpg` 为既有认可高P母版的公开展示，整图长边最多1600px；单侧细节最长边1040px，对照板含排版边框。竖幅整图裁去底部账号区，修后采用相同高度裁幅。`assets/highp-showcase.json` 记录图片尺寸与图例说明。下述编号分析图另以1920px宽输出，便于放大阅读文字。
- `assets/*-analysis-map.png` 用编号、辅助线与区域展示照片分析。瑶的两张图复盘构图、美型与光色；狩司司两张图展示修前方案。两张高P图在技能包 `assets/evidence/highp/` 保留同字节副本，便于离线参考。
- `assets/shousisi-110-plan.png` 和 `shousisi-114-plan.png` 与技能包里的既有 v2 草图保持相同内容，补充教学说明写在网页中。
- 当前展示版本与认可范围以技能包的 `assets/examples/index.json` 为准。在仓库根运行 `python -B tools/sync_example_status.py --write` 同步示例表、页面状态、审美参考版本及高P素材版本；不加 `--write` 时只检查是否过期。
- 更新代表成片时，一起核对网页整图、局部特写与分析。局部坐标随新取景更新；生成状态标签不会替换图片，也不自动升级认可范围。随后更新包清单，并运行 `tools/check_site.py`、包校验及合成回归。
- 页面文字可直接阅读，不依赖脚本才能显示。`site.js` 只负责图片放大和复制按钮；`sitemap.xml` 列出七个公开页面，新增页面时同步索引。
