# PS2020 retouch runtime

Read this reference when repeated Photoshop operations should use the bundled
[ps_retouch_runtime.jsx](../scripts/ps_retouch_runtime.jsx) instead of writing another one-off script.
It targets ExtendScript ES3 / Photoshop 2020, not UXP. It supplies execution
mechanics; visual diagnosis, shape decisions and final aesthetic review remain
the caller's responsibility. It does not automatically reshape bodies or infer
occluded pixels.

## Load and execute

Load the JSX through the established Photoshop script tool, then pass a plain
object to `RetouchRuntime.run(plan)`. Do not feed arbitrary user strings to
`eval`. A supported load is Photoshop's `$.evalFile(new File(runtimePath))`;
the file is the vetted bundled runtime, not an arbitrary downloaded script.
Resolve the current skill root and authorized job root as described in
[portability.md](portability.md). The callable example below accepts those
resolved paths as arguments; it contains no machine-specific defaults. The
executor calls it with the exact unique name of the currently intended open
document. Its illustrative curve and ROI are not a universal retouch preset.

```javascript
function runPortraitExample(skillRootPath, authorizedJobPath, documentName) {
var skillRoot = new Folder(skillRootPath);
var jobRoot = new Folder(authorizedJobPath);
var runtimeFile = new File(skillRoot.fsName + "/scripts/ps_retouch_runtime.jsx");
if (!runtimeFile.exists || !jobRoot.exists) throw new Error("Resolve existing skill and job roots first");
$.evalFile(runtimeFile);
return RetouchRuntime.run({
    jobId: "portrait_light_01",
    mode: "edit",
    documentName: documentName,
    outputDir: jobRoot.fsName,
    allowlistedOutputDirs: [jobRoot.fsName],
    workingDocumentName: "Portrait_Working",
    operations: [
        { type: "group", name: "Light_01" },
        { type: "curve", name: "Elbow_Light_01", parent: {name: "Light_01"},
          points: [[0,0],[64,70],[128,140],[192,200],[255,255]],
          roi: [500,700,900,1150], feather: 45, opacity: 70 },
        { type: "checks", name: "CHECK_01" },
        { type: "preview", file: "overall.png", maxDimension: 1200 },
        { type: "preview", file: "elbow.png", roi: [450,650,950,1200], maxDimension: 1200 },
        { type: "checkPreview", target: {name: "CHECK_01"}, file: "gray-contrast.png" }
    ]
});
}
```

All coordinates above are illustrative. Diagnose the actual photo before
choosing the ROI or curve. ROI/crop units are source canvas pixels. New layer
names must be globally unique. Select existing layers by `{id: 123}` or a name
that matches exactly one layer; duplicate names fail rather than choosing one.

## Plan and continuation

- `jobId`: 1–64 ASCII letters/digits/underscore/hyphen, beginning with a letter
  or digit. A job creates `outputDir/jobId/manifest.json` and its own artifacts.
- `mode`: `probe` reads document/session information without photo edits;
  `edit` executes operations on a new layered duplicate by default.
- `documentName`: exact, unique name of an already open document. The runtime
  does not open original photos or choose the active document implicitly.
- `outputDir`, `allowlistedOutputDirs`: explicit absolute paths. Output root
  must match an allowlisted directory exactly. Parent traversal and root aliases
  are rejected. Paths must also be authorized by the enclosing tool/sandbox.
- `workingDocumentName`: optional name of the initial duplicate; default
  `RT_<jobId>`. The duplicate stays open on success unless
  `keepWorkingDocument: false`. Originals are never saved over.
- `reuseWorkingDocument: true`: explicitly continue a working document that
  already contains the runtime's `__RET_RUNTIME_WORK__` ownership marker. Use
  the working document's name and a **new** jobId. This avoids copying a large
  master for every small revision. The original photo is not a continuation
  target; additionally list its name in `protectedOriginalNames`.
- `operations`: ordered array. Preview early; perform expensive final exports
  only after the executor has completed visual QA for the candidate (this is not an additional user approval step). Do not repeatedly run full export for each tweak.

A continuation failure attempts to roll the working document's history back to
the job's starting state. A failed initial job closes its own working duplicate.
Version 1.0.7 records `rollback.attempted/succeeded/error` and `cleanupErrors`
separately from the original operation error. A failed rollback means the work
document may retain partial changes: stop continuation, inspect the actual
document and recover the saved stable source. Do not report a successful undo
from terminal `failed` alone.
Temporary preview/export/mask documents are closed in cleanup, and original
active document, ruler units and dialog mode are restored. User documents are
not closed. A process kill or Photoshop crash can prevent `finally` cleanup;
inspect the manifest/session rather than assuming completion.

## Operations

| type | Required fields | Optional fields / behavior |
|---|---|---|
| `group` | `name` | `parent`; `mask: white/black/roi`, ROI and feather for roi mask |
| `curve` | `name`, `points: [[x,y],...]` | `parent`, `roi`, `feather`, `opacity`, `channel`; default composite channel and luminosity blending; `blend: normal` explicitly enables color-changing channel corrections |
| `color` | `name`, `rgb: [r,g,b]` | `parent`, ROI/feather/opacity, `clipTo` selector; creates editable solid-color layer in COLOR blend mode, clipped directly above specified donor when supplied |
| `mask` | `target`, `kind: white/black/roi` | ROI/feather; target must not already have a user mask |
| `importMask` | `target`, `path` | Grayscale image matching canvas dimensions exactly; imported through an alpha channel and selection, preserving main RGB channels; refuses an already open input mask or pre-existing target mask |
| `liquifyFace` | `name`, `faceWidth` | Requires loaded native module; only the measured faceWidth control, not a complete face API |
| `liquifyMesh` | `name`, `meshPath` | Requires loaded native module; measured inline `LqMe` v4 format, matching current full-canvas geometry |
| `checks` | `name` | Creates hidden group with gray COLOR layer and contrast curve; caller must keep this group hidden for ordinary preview/final export |
| `preview` | `file` ending `.png` | ROI and `maxDimension` (64–4096; default 1200), never upscales; merged temporary duplicate is cropped/resized/converted to sRGB8 |
| `checkPreview` | `target` check group, `file` | Same preview options; group temporarily shown and restored |
| `export` | `variants` or `psd`/`png` | Native PSD and/or PNG, optional exact integer crop derived from full master |

Curve x coordinates must increase strictly and x/y must lie in 0–255, even on
RGB16 documents; supported channels are `Cmps`, `Rd  `, `Grn `, `Bl  `.
Feather is bounded by half the smaller ROI dimension. Operations support RGB8
and RGB16. Work canvas size, mode, bit depth and profile are checked after every
operation. Runtime intentionally supplies no arbitrary action playback,
flatten-master, whole-body transformation or mask replacement operation.

An imported automatic mask supplies visible subject separation. Check hair,
lace, contact edges and retained props before adopting it. It cannot recover
body or clothing hidden behind a box.

## Optional native Liquify in 1.0.7

Read this section only when the approved task benefits from native geometry.
Load `scripts/ps_liquify_runtime.jsx` **before** this runtime. Other operations
remain available without that optional module. A `probe` is read-only and
reports the loaded API; it never invokes Liquify and cannot prove that pixels
will move on this host or photo.

The measured routes are `executeAction("LqFy", ...)` with `faceMesh` controlling
only `faceWidth`, and inline binary `LqMe` mesh v4. Other face controls, multi-face
selection, `.msh` file playback through `LqMD`, arbitrary recorded actions and
other Photoshop versions are not established by these tests. Photoshop may
return success with no pixel effect. The value `faceWidth: -0.1` is an engine
parameter, **not** a measured 10% face-width reduction or a beauty preset.

```javascript
function runReviewedGeometry(skillRootPath, jobRootPath, meshFolderPath, documentName, meshPath) {
    $.evalFile(new File(skillRootPath + "/scripts/ps_liquify_runtime.jsx"));
    $.evalFile(new File(skillRootPath + "/scripts/ps_retouch_runtime.jsx"));
    return RetouchRuntime.run({
        jobId: "reviewed_geometry_01", mode: "edit", documentName: documentName,
        outputDir: jobRootPath, allowlistedOutputDirs: [jobRootPath],
        allowlistedInputDirs: [meshFolderPath],
        operations: [{type: "liquifyMesh", name: "Reviewed_Local_Shape", meshPath: meshPath}]
    });
}
```

Pass fresh coordinates and a mesh made for the actual current source. This
example does not choose a shape or create a mesh. For `liquifyFace`, replace the
operation with `{type: "liquifyFace", name: "Reviewed_Face", faceWidth: amount}`;
choose `amount` from a justified local trial and verify the actual image.

Both operations accept `source: "mergedVisible"` (default) or `"target"`:

- **mergedVisible** snapshots the current visible composition onto a new top
  level pixel layer above all existing content. It requires a visible document
  root Photoshop **Background** layer at normal 100% opacity/fill without masks
  or effects, which supplies a truly opaque base. Full-canvas bounds alone do
  not prove opaque pixels. `parent` and `target` are refused on this route.
  Subsequent snapshots bake visible earlier changes; record this dependency
  rather than treating all geometry layers as independent edits of the source.
- **target** requires a named or identified normal 100% full-canvas ordinary
  pixel layer, without masks, effects or clipping. It duplicates at the donor's
  original stack position, then hides the donor as a reversible replacement.
  The original group stays in place unless an explicit `parent` is supplied.
  Only no mask or `mask: "white"`, 100% opacity and visible output are supported;
  local effects belong in the mesh. This also avoids double compositing alpha.
  Compare by hiding the result **and restoring donor visibility**; hiding only
  the replacement is not a valid before view. Moving to a different parent can
  change group compositing and must pass separate visual/pixel QA.

Merged output may use `opacity`, `visible`, and `mask: "white"/"black"/"roi"`;
ROI requires `roi: [left,top,right,bottom]` and optional bounded `feather`.
The filter receives the whole canvas with no active selection; the mask is
created afterwards. Feather is a selection setting, **not** a guarantee that
all changed pixels lie inside the rectangle. Inspect the actual support and
protection regions after the final effective opacity and mask are applied.

Mesh input must be a literal absolute local `.msh` file in the job directory or
an explicit existing `allowlistedInputDirs` root. Parent traversal, aliases,
UNC/URI paths, unknown headers, canvas mismatch, malformed row runs, non-finite
floats, trailers and files above 128 MiB are refused. Geometry in this measured
v4 path requires current width and height divisible by four. Other geometry
uses another actually verified method; do not resize the mother file to satisfy
this format. A sidecar source hash is a caller binding, not automatically
verified by the JSX parser.

`scripts/build_liquify_mesh.py` uses only Python standard library. Its `--spec`
JSON contains `width`, `height`, manually reviewed `regions` with `center`,
`radius`, `sample_offset_pixels`, optional `protected_rois` and `source_sha256`.
`--output` names a new task `.msh`; a `.json` sidecar is written alongside it.
Do not write artifacts to the skill or feed pose keypoints directly as control
regions. The measured grid is four source pixels; displacements are inverse
sampling offsets, so visible movement has the opposite direction. All four cell
corner Jacobians are checked after float32 quantization. A positive result is
a numerical fold check, not anatomy, protection or aesthetic acceptance.

`manifest.nativeLiquify` records parameters/mesh metadata, source dependencies,
style/mask settings, command timing and outcome. `commandExecuted` and runtime
`complete` are execution statuses; `pixelEffectUnverified` stays explicit.
Check actual output for **effect, scope and aesthetic benefit**. First deployment
or code change also needs zero controls, nonzero effect, saved depth/profile,
layer preservation and failure/rollback checks. Each photo still needs visual
review of its affected areas and connected protection regions: as applicable,
face/neck, chest/waist/hips, joints, fingers, costume and straight props. A local
repair does not reopen unrelated full-body retouching.

The measured evidence is packaged in [native validation](../assets/evidence/native-liquify-validation.json).
Its environment and exact script hashes define the tested scope. Missing module,
unsupported host or a failed applicable test falls back to an existing verified
PS geometry method; use a generation candidate only when justified by the
approved problem. Neither native Liquify nor body landmarks fill hidden anatomy.

## Final export example

Continue the reviewed working master and export once. Load the same vetted
runtime as above before calling this function; pass the current working and
protected original document names. Choose crop coordinates for the actual
master rather than copying the example unchanged.

```javascript
function exportPortraitExample(authorizedJobPath, workingName, originalName) {
var jobRoot = new Folder(authorizedJobPath);
if (!jobRoot.exists) throw new Error("Resolve the existing authorized job root first");
return RetouchRuntime.run({
    jobId: "portrait_final_02", mode: "edit",
    documentName: workingName, reuseWorkingDocument: true,
    protectedOriginalNames: [originalName],
    outputDir: jobRoot.fsName,
    allowlistedOutputDirs: [jobRoot.fsName],
    operations: [{type: "export", variants: [
        {name: "full", psd: "full.psd", png: "full.png"},
        {name: "medium", crop: [200,100,2200,2600], psd: "medium.psd", png: "medium.png"}
    ]}]
});
}
```

PSD is layered and requests embedded ICC/alpha channels. PNG is saved through
native `PNGSaveOptions` from a merged duplicate without converting profile,
reducing bit depth, rescaling or flattening the source. Crop coordinates are
integer source pixels; crop PSD remains layered. PNG does not preserve edit
layers. Preview conversion is separate and must not be used for final delivery.
The runtime respects current layer visibility. It creates checking groups hidden
and `checkPreview` restores their prior visibility, but it cannot identify a
checking group that the caller manually renamed or showed. Before ordinary
preview or final export, explicitly confirm checking groups are hidden. A
manually visible gray/contrast checking group would otherwise enter the output.
Verify the exported PNG bit depth/ICC and crop pixels independently when first
deploying or changing the runtime; document metadata alone does not prove bytes
in the saved file are correct.

## Timing, completion and limits

The manifest records source metadata, each operation's start, completion and
elapsed milliseconds, assets, total elapsed time and terminal `complete` or
`failed` status. `complete` means execution and cleanup completed; it does not
mean aesthetic QA passed. On a tool timeout, Photoshop may still be executing:
inspect this manifest and any output progress before retrying. Existing job
directories and output files are refused, so a resubmission cannot silently
overwrite or repeat a completed job. Failed job assets may be partial; only
deliver after terminal success and appropriate visual verification.

The runtime does not compress PNG IDAT, remove metadata, install plugins or
perform external writes beyond the explicit job directory. Lossless compression
can follow final verification with [the bundled container compressor](native-file-checks.md).
This reference describes intended behavior; retain real
Photoshop smoke-test evidence before calling a newly modified version verified.

Historical deployment tests used Photoshop 21.2.9 and runtime 1.0.6.
The ROI curve, color correction, hidden gray/contrast check, native export,
exact crop, original-P3 mask import and continuation rollback were exercised.
Group white/black masks use full-canvas selection plus `revealSelection`;
black is then filled on the mask channel. Direct `hideAll` mask creation failed
in the original PS2020 test session and is not used by this runtime. Read the job manifest even if the MCP
tool says its script executed: a job's terminal status can still be `failed`.
Historical test artifacts and the author's machine are not included in this
package. Recheck required operations on a small synthetic document when moving
to a different environment. Tool-call batching measurements do not establish
total photo-retouching speed or aesthetic quality.
