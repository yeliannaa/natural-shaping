# 私人偏好与训练配对共用档案

只整理一次事实：`cases-index.json` 保存图片版本和任务配对，`feedback.jsonl` 保存用户反馈；`preferences.md` 从这些证据整理有适用条件的偏好。修图检索与训练清单从同一档案读取，不另维护一套案例。

## 位置与隐私

公共 skill 默认不打包本机新增的私人照片、偏好、原始反馈或训练导出；已获公开授权的教学示例另见 `examples`。用户明确要求分享时，另建按字段白名单整理的公开副本，保留问题、可观察目标、适用条件和公开案例链接；省去个人原话、排序、身份线索、本机路径、私人图片指纹与训练资料，原私人库保持不变。当前包的[公开审美参考库](aesthetic-reference/README.md)是这种独立资料，不是可直接登记为私人案例／训练配对的原库副本。

可选的本机配置放在 `~/.codex/natural-shaping.local.json`：

```json
{"personal_store": "<PRIVATE_STORE>", "collection_enabled": false}
```

将占位符换成用户选择的私有目录的绝对路径；路径只存在本机配置里。用户授权持续收集后才开启 `collection_enabled`；命令行显式登记按本次授权执行。`init` 创建私有目录中的 `store-config.json`、`cases-index.json`、`feedback.jsonl`、`preferences.md`，已有文件不覆盖。初始化后设置私有 `store-config.json`：

```json
{"schema_version": 1, "media_roots": {"photos": "<LOCAL_PHOTO_ROOT>", "work": "<LOCAL_WORK_ROOT>"}}
```

各根目录填本机绝对路径；案例图片用根名加相对路径引用。原图继续留在原目录，通过 SHA-256 和尺寸确认身份，不复制、不覆盖。已登记图片要保留；新修订增加新资产和版本。图像资产目前只支持 PNG/JPEG，PSD 不作为训练图像资产。脚本拒绝把私有库或导出目录放进 skill 包内。

没有配置、没有私有库或没有 Python 时，继续普通 natural-shaping 流程；私人档案不是安装、修图或使用公共案例的前提。

## 日常调用

以下命令从 skill 根目录运行，Python 3.8+，无需额外 Python 包。占位符由调用者换成真实路径；配置后可省略 `--store`，也可用 `--config` 指定其他本机配置。

```powershell
$privateStore = '<PRIVATE_STORE>'
python scripts/personal_data.py --store "$privateStore" init
python scripts/personal_data.py --store "$privateStore" query --tags 袖口 手腕 --limit 3
python scripts/personal_data.py --store "$privateStore" query --summary --style highp --tags 脸部 妆面 --limit 3
python scripts/personal_data.py --store "$privateStore" query --summary --style natural --status any --tags 肤色 --limit 2
python scripts/personal_data.py --store "$privateStore" record-case --file '<CASE_RECORD.json>'
python scripts/personal_data.py --store "$privateStore" record-feedback --file '<FEEDBACK_RECORD.json>'
python scripts/personal_data.py --store "$privateStore" validate
python scripts/personal_data.py --store "$privateStore" export --output '<NEW_PRIVATE_EXPORT_DIR>'
```

修前读取偏好，按本次问题查 1–3 个相关案例，查看选中图片后再判断。`query` 返回短偏好档案、最近最多 8 条未绑定单图的通用反馈、命中案例及其反馈；通用反馈在无案例命中时仍返回。它是标签匹配，不是图像识别或向量检索；未命中也不虚构案例。记录与检索的图片路径均指向用户自己的库。私人库登记只设一个写入者，并行任务把记录串行汇总，避免同时改索引。

用户已授权收集后，日常修图应及时更新生成版本、返修反馈和真实认可记录，不要求每次记录重新审批。只有明确的用户反馈能改变认可状态；存图、导出、助手验收通过、模糊称赞不能自动代表全图终稿认可。任务偏好先留在案例中，反复出现且有证据的偏好再整理入 `preferences.md`。

### 按风格检索具体版本

不加新选项时，`query` 仍按案例级 `tags` 匹配，返回原有完整案例结构，`--limit` 保持1–10。`--summary` 则返回1–3个具体版本，默认只查有效认可的版本；`--style natural|highp` 和 `--status accepted|any` 仅用于摘要模式。`any` 用于查看相关待验收或待返修记录，不代表这些版本已获认可。

摘要仍需查询词与 `case.tags` 或 `variant.tags` 有交集，并且版本有明确风格证据：`variant.style` 为 `natural`／`highp`，或 `context.current_finals_by_style` 将该风格明确指向该版本。先按标签命中数量排相关性，同等相关性优先有效认可的该风格当前终稿；每个来源组／风格最多返回一个最相关版本，避免多个历史版本占满摘要。不搜索任意context文本，不从文件名、`display_name`、缺少标签或“不是高P”猜成自然档。没有证据或证据冲突时不纳入摘要，空命中就返回空列表。自然档和高P档各有适用条件，高P认可不覆盖自然档，也不使高P成为新照片默认。

可在既有案例中增补以下可选字段，无需新建数据库或提高schema版本：

```json
{
  "variants": {
    "natural-final": {"asset_id": "natural-final-image", "style": "natural", "tags": ["脸部", "肤色"], "acceptance": {"status": "accepted", "scope": {"kind": "full"}, "feedback_ids": ["actual-natural-acceptance"]}},
    "highp-final": {"asset_id": "highp-final-image", "style": "highp", "tags": ["脸部", "妆面"], "acceptance": {"status": "accepted", "scope": {"kind": "full"}, "feedback_ids": ["actual-highp-acceptance"]}}
  },
  "context": {
    "subject_group_id": "user-confirmed-person-group",
    "current_finals_by_style": {"natural": {"variant": "natural-final"}, "highp": {"variant": "highp-final"}},
    "preference_comparisons": [{"id": "comparison-001", "preferred_variant": "highp-final", "other_variant": "earlier-trial", "statement_type": "user_statement", "status": "tentative", "tags": ["妆面"], "note": "保留原话中的可能等限定", "scope": {"kind": "local", "region_id": "makeup"}, "feedback_ids": ["actual-comparison-feedback"], "summary": "仅概括该条真实反馈，不扩大为全局偏好"}],
    "revision_examples": [{"variant": "earlier-trial", "feedback_ids": ["actual-revision-feedback"], "tags": ["妆面"]}]
  }
}
```

这是字段示意，不是可登记的认可证据。`context.preference_comparisons` 可为上述列表，也可用 `{"records": [...]}` 包装；另一版本键兼容 `compared_variant`。返回与当前版本相关的最近最多3条比较及对应反馈，保留status／tentative／note／tags等限定。另从 `context.revision_examples` 按当前版本或查询标签关联最多2条返修例子，附原反馈的actor、decision和quote；不能把例子统一改称拒绝。比较记录不改变版本认可状态，“更喜欢A”不自动把B标为拒绝，pending也不是负例。未明确选胜者时不要编造 `preferred_variant`。

### 比较结果与适用条件

已有比较可补 `compared_variants`（实际比较过的版本列表）、`outcome` 与 `conditions`。`outcome` 可记 `preferred`／`tie`／`neither`／`undecided`，分别表示有明确偏好、平手、都不满意、无法判断；只按真实反馈登记。有胜者才填 `preferred_variant`；无胜者用 `compared_variants` 关联两侧，摘要仍能检索该比较，不制造负样本，也不改变版本认可或训练资格。

`conditions` 记录比较适用的光线、机位、姿态、材质、景别和修改范围，指出参考能借鉴什么；另用 `scope` 说明具体区域。必要联动按组合记录，不假称只有一个变量。用户原话与助手解释继续分开，已有历史反馈不为填齐字段而重写。

选中1–3条摘要后，先核当前问题与这些条件是否相容，再实际看对应图。对照测试检索价值时，保持输入、目标和候选预算，比较“既有流程”与“加入相近认可／明确返修经验”；记录命中的版本、偏好结果、遗漏、返修及总耗时，错配先修标签或条件，再决定是否改排序。当前摘要仍是标签排序，新增字段不代表已实现视觉检索或已证明更懂用户。已试训LoRA保留作同条件对照，是否继续训练由数据和实际收益决定。

用户原话保留在反馈的 `quote`，连同 `actor`、`source`、版本/hash/范围和时间；助手分析另放比较的 `interpretation`，并用 `statement_type: assistant_interpretation` 标明。偏好摘要应引用证据ID、说明本图／风格／角色等适用条件；不能因用户整图验收通过，就把助手对全部审美动机的推测变成用户原话或全局规则。

摘要的有效认可需要 `variant.acceptance.status=accepted`，以及 `feedback_ids` 指向用户对该版本、hash和同一范围的真实accept事件。按反馈追加顺序，最新有效accept之后若有用户同版本/hash且范围重叠的revision、reject或withdraw，该范围不再作为accepted命中；重新明确认可并绑定新事件后才恢复。局部认可照实返回local范围，不升级为整图；不重叠局部反馈、普通请求、保存指令和比较都不自动撤销认可。

摘要给出原图与目标资产的根名、相对路径、已登记hash/尺寸、范围、有效认可／阻断反馈和比较摘要；只读取metadata，不打开图片或核验媒体hash，也不替代实看。训练资格标为未评估，已有配对状态照实展示，不会创建配对或把pending改成ready。`context.subject_group_id` 只记录有用户依据的同人物分组，不靠人脸识别推断，不替换表示同一原照片的 `source_group_id`。当前export仍按下文既有来源组和配对门槛执行，不因人物组字段新增就宣称已完成跨人物分组核验。

## 最小案例模板

下面是结构模板，不是可直接登记的样本；文件、哈希、尺寸和证据必须来自真实资产。局部袖口任务保留实际阶段输入与候选整图，另准备两张对齐裁片；认可范围坐标属于候选父画布。

```json
{
  "id": "case-001", "source_group_id": "source-001", "split": "unassigned",
  "source_asset": "original", "tags": ["袖口", "手腕"],
  "assets": {
    "original": {"root": "photos", "path": "case-001/original.jpg", "sha256": "<ACTUAL_SHA256>", "size": [3072, 4080]},
    "stage-input": {"root": "work", "path": "case-001/stage-input.png", "sha256": "<ACTUAL_SHA256>", "size": [3072, 4080]},
    "candidate-full": {"root": "work", "path": "case-001/candidate-full.png", "sha256": "<ACTUAL_SHA256>", "size": [3072, 4080]},
    "input-crop": {"root": "work", "path": "case-001/input-crop.png", "sha256": "<ACTUAL_SHA256>", "size": [960, 960],
      "derived_from": {"asset_id": "stage-input", "operations": ["crop"], "mapping": {"crop_xyxy": [900, 1800, 1860, 2760], "output_size": [960, 960]}, "verified": true, "evidence": "<ACTUAL_PREPARATION_REVIEW>"}},
    "target-crop": {"root": "work", "path": "case-001/target-crop.png", "sha256": "<ACTUAL_SHA256>", "size": [960, 960],
      "derived_from": {"asset_id": "candidate-full", "operations": ["crop"], "mapping": {"crop_xyxy": [900, 1800, 1860, 2760], "output_size": [960, 960]}, "verified": true, "evidence": "<ACTUAL_PREPARATION_REVIEW>"}}
  },
  "variants": {
    "v1": {"asset_id": "candidate-full", "acceptance": {"status": "pending", "scope": {"kind": "local", "region_id": "cuff", "bbox_xyxy": [900, 1800, 1860, 2760]}, "feedback_ids": []}}
  },
  "training_pairs": [{
    "id": "pair-001", "status": "pending", "task": "cuff-repair",
    "input_parent_asset": "stage-input", "input_asset": "input-crop", "target_asset": "target-crop", "accepted_variant": "v1",
    "scope": {"kind": "local", "region_id": "cuff", "bbox_xyxy": [900, 1800, 1860, 2760]},
    "instruction": "修复手背与袖口过渡，保留握相机姿态和花边结构。",
    "preserve": ["相机", "握持姿态", "花边"],
    "alignment": {"status": "pending", "method": "prepared_pair", "mapping": {"input_crop_xyxy": [900, 1800, 1860, 2760], "target_crop_xyxy": [900, 1800, 1860, 2760], "output_size": [960, 960]}},
    "color_review": {"status": "pending"}, "review_evidence": ""
  }]
}
```

`record-case` 接收单个案例对象，核验所有资产后写入索引；更新时保留既有资产 ID、哈希、`source_asset`、`source_group_id` 和历史版本到资产的绑定。不要修改旧文件后沿用旧哈希。`split` 未分配的案例可检索，但不能导出训练配对。

反馈单独登记，真实认可必须绑定版本、图片哈希、范围、用户原话和来源：

```json
{
  "id": "feedback-001", "case_id": "case-001", "variant_id": "v1",
  "actor": "user", "decision": "accept", "asset_sha256": "<ACTUAL_CANDIDATE_FULL_SHA256>",
  "scope": {"kind": "local", "region_id": "cuff", "bbox_xyxy": [900, 1800, 1860, 2760]},
  "quote": "<USER_ACTUAL_ACCEPTANCE>", "source": "<THREAD_OR_MESSAGE_REFERENCE>",
  "recorded_at": "<ISO_TIMESTAMP>"
}
```

接受事件登记后，通过 `record-case` 更新该版本的 `acceptance.status` 为 `accepted`，并填写 `feedback_ids`。局部接受仍是局部接受，不升级为全图；重新编辑后的图片需要新的版本和对应反馈。被否定的候选保留为检索与评估记录，不直接作为普通监督 LoRA 的目标图。

否定、撤回、明确待返修分别记录 `reject`、`withdraw`、`revision`，同样绑定实际版本、哈希和范围；晚于认可且影响配对范围的事件会阻止导出。普通“再试一版”记 `request`，不自动撤销先前认可；新的认可需要新的真实证据。

## 从认可案例到合格训练配对

认可与可训练是两个状态：版本必须有真实 `accepted` 证据；配对经过以下核验后才可标为 `ready`，并记录 `review_evidence`。

- `same_canvas`：输入、目标本来就在同一画布；仍需实际核对对齐，不能只看尺寸。
- `prepared_pair`：先准备好对应输入与目标，再登记 `alignment.mapping` 和 `alignment.evidence`。mapping 只含 `input_crop_xyxy`、`target_crop_xyxy`、`output_size`：输入裁框属于 `input_parent_asset` 的画布，目标裁框属于 `accepted_variant.asset_id` 的画布，输出尺寸对应两张实际准备文件。两侧裁框可不同，脚本分别与各自的 `derived_from.mapping`、父资产和实际文件尺寸对账，不强制输入父图为最初原图。脚本不裁图、不缩放、不编辑图片。
- `prepared_pair` 必须有两张实际独立裁片和 `input_parent_asset`。局部任务不得整图标成 `local`；`scope.bbox_xyxy` 是目标认可父画布中的整数边界，与目标裁片映射一致，局部认可也使用这套范围坐标。裁框以各自父画布左上角为像素原点，右、下边界不包含在裁片内。
- 两张裁片的 `derived_from` 分别直接指向实际阶段输入父图和认可目标父图。必填 `operations`、`mapping.crop_xyxy`、`mapping.output_size`、`verified: true`、`evidence`；mapping 只含这两个字段，尺寸为两个正整数，裁框为四个整数且非空、不越界；布尔值不作整数接受。操作可组合 `crop`、`resize`、`color_convert`，但必须含 `crop`。当前格式不支持补边、旋转或额外映射字段，不将它们登记成普通 resize。任何新增修图都应成为另一个待认可版本。
- 未声明 `resize` 时，输出尺寸须等于裁框尺寸。声明后须存在同一个正缩放比例 `s`，使两边分别满足 `output = floor(crop_length * s + 0.5)`（四舍五入，恰好半像素向上）；脚本以精确分数核对共同缩放区间，不设百分比容差。因此 21×20→10×10 的合理整数舍入可通过，20×20→10×20 的非等比拉伸会被拒绝。该检查核对尺寸关系，重采样质量仍看实际裁片。
- `color_review` 填 `status: verified` 和 `evidence`，人工核对方向、EXIF 旋转、ICC／颜色转换及画质，避免把色彩管理差异误当美型偏好。哈希与尺寸检查不能替代这一步。
- `source_group_id` 将同一原图的全图、局部、重采样和多版结果归入同组；整组只分配到 `train` 或 `validation` 一侧，防止同源泄露。独立验收照片不参与训练。

`validate` 核验文件身份、实际尺寸、上述映射一致性和已登记的配对资格，报告待处理／排除项；它不自动判断审美、画面结构或用户是否认可。可检索案例不必马上具备训练配对。

## 导出与后续训练

`export` 写入新的或空的私有目录：`train-pairs.jsonl`、`validation-pairs.jsonl`、`export-report.json`。只导出通过检查的 `ready` 配对，保存实际图片路径、哈希、修改指令、范围、保留项和认可证据；不复制图片，不调用模型，不训练。

这是模型中性的编辑配对清单，还不是经过验证的 Qwen-Image-2.1／DiffSynth-Studio 数据适配。确定可训练底座、框架版本和 LoRA 兼容性后，可从这份清单自动生成具体框架所需的元数据，无需重新整理案例。训练与 ncnn 加载验证另行执行，不能将导出成功称为训练完成或兼容性通过。

导出清单包含本机路径与私人证据，继续放私有目录；发布公共 skill 时排除本机配置、私有库及训练导出。
