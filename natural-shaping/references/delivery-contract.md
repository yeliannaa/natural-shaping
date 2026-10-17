# 将验收绑定到实际交付文件

用于最终导出、较复杂局部融合，或曾出现画幅／版本错位的任务。沿用任务旁的单一 JSON：可把对象放入既有 runtime/task manifest 的 `delivery` 字段，也可用一个 `delivery.json`。它承接已有三道验收，不新增用户确认步骤。

## 记录什么

| 字段 | 含义 |
|---|---|
| `files.source` | 本轮锁定的稳定母稿，记录实际文件 SHA256 和真实宽高 |
| `files.composite` | 已对位、已完成尺寸和颜色处理的工作画布合成，区别于原始生成供体 |
| `files.candidate` | 可选；实际选中的生成供体或候选。不生成的小修省略 |
| `files.export` | 实际交付文件；视觉验收打开的就是这份文件 |
| `mapping` | 工作画布尺寸、母稿放置原点、交付裁框及像素核对方式 |
| `responsibilities` | 允许修改的矩形集合，坐标统一来自工作画布 |
| `protections` | 像素精确、几何或语义保护；按任务选择，可为空 |
| `visual_review` | 对实际导出完成的三视图、三道结论与保护项观察，并绑定文件版本 |

路径相对于记录文件解析，使用本地相对路径，可含 `../`。裁框与区域均用整数半开坐标 `[left, top, right, bottom]`；母稿按 `source_origin` 原尺寸放入画布。交付宽高等于裁框宽高，工具不猜测位移或缩放。需要缩放时先完成尺寸处理、生成对齐合成，再记录本次原生裁框；更复杂变换继续留在既有 runtime 记录，不能强填成平移映射。

## 最小记录示意

以下路径、尺寸、区域和 SHA 均为示意，按真实文件填写。生成候选不是必填项。

```json
{
  "schema_version": 1,
  "files": {
    "source": {"path": "source.png", "sha256": "<actual-source-sha256>", "size": [1000, 1400]},
    "composite": {"path": "work/composite.png", "sha256": "<actual-composite-sha256>", "size": [1200, 1500]},
    "export": {"path": "final.png", "sha256": "<actual-export-sha256>", "size": [1100, 1400]}
  },
  "mapping": {
    "canvas_size": [1200, 1500],
    "source_origin": [0, 100],
    "delivery_crop": [0, 100, 1100, 1500],
    "export_crop_check": "exact_png"
  },
  "responsibilities": [{"id": "prop", "rect": [800, 100, 1200, 600]}],
  "protections": [
    {"id": "outside", "type": "exact_pixels", "scope": "outside_responsibilities"},
    {"id": "face", "type": "semantic", "rect": [300, 250, 600, 650]}
  ],
  "visual_review": {
    "kind": "manual_visual",
    "export_sha256": "<same-actual-export-sha256>",
    "binding_sha256": "<fingerprint-after-files-and-regions-are-fixed>",
    "views": ["fit", "native", "context"],
    "gates": {"goal": "pass", "structure": "pass", "finish": "pass"},
    "protection_results": {"face": {"status": "pass", "note": "记录本次实际看到的脸部、妆色与连接关系。"}}
  }
}
```

`fit` 是全图观看尺寸；`native` 是原尺寸细节；`context` 联看完整受影响轮廓、两端连接和邻接结构。`goal` 对应目标及审美收益，`structure` 对应身份／妆造／结构，`finish` 对应实际导出的融合与接缝。助手实际看图和用户认可分别记录；这里的 `pass` 是已完成的看图结论，不是脚本代填。

## 检查与记录顺序

1. 固定母稿、工作画布、选中候选、责任范围和实际导出，填写真实 SHA 与宽高。
2. 运行只读检查取得本次绑定指纹：

   ```text
   python scripts/verify_retouch_delivery.py path/to/task.json --print-binding
   ```

   输出 `binding_ready` 只说明可记录此次复核；不会写入记录或宣告已看图。
3. 打开实际导出，完成三视图与三道验收，填写 `visual_review`，再运行：

   ```text
   python scripts/verify_retouch_delivery.py path/to/task.json
   ```

成功输出 `mechanical_checks_passed`，失败退出码为 1。文件内容、真实尺寸、映射、责任范围或保护定义改变后，旧复核绑定失效；修改后重新看相应视图并更新结论。记录和图一起移动、只改变相对路径时，内容绑定保持有效。

## 保护项怎样选择

- `exact_pixels / outside_responsibilities`：在母稿与交付裁框的**有效重叠区**内，检查责任矩形并集以外的全部像素。新增扩边无原始像素可比。该范围为空时拒绝把它算作保护通过。
- `exact_pixels / roi`：再加更严格的矩形 `rect`，例如允许改道具附近但仍严格保留某处细节。ROI 必须完整落在源与交付的重叠区。这些集合是矩形范围，不表示任意形状蒙版。
- `geometry`、`semantic`：填写工作画布内、实际交付可见的 `rect`，并在 `protection_results` 按 id 写入本次具体观察。脚本校验这份结论的版本绑定，不自动识别人脸、骨骼、服装连接或审美。

整体补光、调色或已授权美型可以只采用几何／语义保护，不必强加整图零差异。精确保护仅用于同坐标、同颜色表示的原生 **8-bit PNG**；支持匹配的 L、LA、RGB、RGBA，核对 ICC、透明声明、原生方向和全部通道。工具读取实际 PNG IHDR 位深；16-bit RGB／RGBA 即使被 Pillow 解码成 RGB／RGBA，也不进入精确像素比较。

高位深交付使用 `binding_only`，保护项选择几何／语义，保留原文件哈希、尺寸与实际看图绑定。需要高位深像素核对时，另用 [原生 PNG 检查器](../scripts/verify_native_png.ps1) 执行对应检查。这里不会把原图降成8-bit后宣称原生像素相同。

`mapping.export_crop_check` 选择：

| 值 | 实际证明 |
|---|---|
| `exact_png` | 工作合成裁框与实际导出逐像素相同；要求原生8-bit及匹配的 PNG 颜色表示 |
| `binding_only` | 文件内容哈希、尺寸和所声明映射已绑定；不声称证明了裁剪像素来源 |

JPEG 用 `binding_only`，不登记 `exact_pixels`。压缩与颜色转换不能用无损差异判作越界修图。

## 验证范围

工具只读本地文件，不调用 Photoshop、模型或网络。它不会替代实际看图，也不会生成用户认可、终稿身份或训练资格。`manual_visual` 是助手或人工看图记录；回归测试中的结论均为 **synthetic**，只证明机械检查行为。

运行合成回归：

```text
python -B -m unittest discover -s tests -p test_retouch_delivery.py -v
```
