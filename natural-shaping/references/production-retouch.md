# Photoshop production: natural shaping, compositing, and efficient review

Read this reference only for native Photoshop production or a Photoshop-finished hybrid edit. It supplements [the main skill](../SKILL.md); its identity protections, requested scope, and applicable limits still apply. This is a working method, not an automatic body-slimming preset.

## Route and authorization

- Continue a route and adjustment scope already selected in the conversation. An explicit Photoshop/editable-PSD request authorizes that route; do not repeat a menu or connection question for its ordinary operations.
- An approved request for autonomous, noticeable natural shaping permits image-specific local decisions within that scope. It does not authorize new subjects, destructive overwrites, unrelated feature changes, or compulsory reshaping of every later photo.
- Preserve the original file and an untouched source layer. Keep identity anchors, costume design, props, and the intent of the photographed pose. Keep subjective shaping distinguishable from corrections to capture or light.
- With a verified Photoshop MCP/ExtendScript connection, use that existing route. A UXP panel, Developer Tool, and new plugin installation are not prerequisites for JSX execution. Load a UXP-specific reference only when actually using that panel route.

## Classify before editing

When the user asks to improve composition, start with [composition and capture guidance](composition-and-capture.md) before choosing pixel moves or reconstruction.

Use a short change map containing the observation, likely cause, operation, local scope, protected anchors, and uncertainty. Classify each problem before choosing a tool:

| Class | Typical evidence | First useful operation |
|---|---|---|
| Tone | Dark elbow, hard nose-side shadow, uneven face/neck light | Local curves or dodge-and-burn with structural shadow preserved |
| Color | Magenta skin spill, different arm hues, gray hair after correction | Material-specific color correction with luminance/texture retained |
| Geometry | Supported contour issue or explicitly requested proportion change | Verified native liquify or displacement on a separate, inspectable layer |
| Mask/edge | Straight hair cut, halo, detached arc, clipped collar | Identify the layer/mask responsible and repair its actual boundary |
| Occlusion/reconstruction | Box hides hair, clothing, or body | Choose composition first; use source texture or narrowly masked synthesis where needed |

Distinguish perspective, head tilt, expression, optical distortion, light, and occlusion from permanent anatomy. A tilted pose is not automatically a defect. A color correction cannot fix a polygon-shaped hair outline; broad blur cannot fix a broken joint or mask.

## Build the production master

1. Inspect the whole image and identity-critical details. For every new photo or full rework, show the source-based composition sketch and obtain the main skill’s required confirmation before editing. A same-plan local repair inherits its existing confirmed scope.
2. Establish the main light, background competition, and overall skin/costume color. Anticipate reconstruction boundaries and light falloff now, rather than after finishing individual patches.
3. Keep tone/color, geometry, reconstructed pixels, and environmental light/contact shadows in independently editable layers or groups. Use an untouched anchor and rollback points for meaningful stages; every temporary preview need not become a full PSD checkpoint.
4. Run an authorized natural-shaping pass where it helps this image. Recheck light and contour together after geometry changes.
5. Resolve local seams and edges, then complete visual and file verification appropriate to the task size.
6. Finish one master before deriving approved crops. Store crop rectangles/placement so a later master repair propagates consistently. If a crop needs independent treatment, record the intentional difference.

Merged pixel layers are snapshots, not live dependencies. Track their source state when making background blur, tone-combined layers or geometry composites. After changing an upstream donor, mask, geometry or light layer, rebuild any affected snapshot from the reliable current state; simply hiding an old source layer cannot remove pixels already baked into a later layer. Preserve the accepted master and anchors while updating only the necessary dependent layers.

## Natural shaping and skin continuity

- Match the requested visible improvement while preserving identity and believable anatomy. Do not use a universal face ratio, fixed displacement percentage, app-slider value, or a single beauty template as proof that a result looks good. Respect applicable parent-skill bounds; choose actual movement relative to this image and inspect its consequence.
- Assess a complete contour, including its adjacent joints and clothing: shoulder → upper arm → elbow → forearm/sleeve, and jaw → neck → clavicle/shoulder. Avoid narrowing only an arm's middle and leaving its ends unchanged; this can create a dent. A continuous coordinated adjustment need not move every part by an identical amount.
- Keep joint position, crease direction, muscle transitions, hand structure, and costume seams coherent. Preserve pose intent. Small pose presentation corrections may use the approved native route when pixels remain available; a new action or hidden anatomy requires a separately scoped reconstruction.
- For face/neck transitions and a pronounced line beside the nose, test tone/color softening before inventing new geometry. Preserve nostril, lip, eye, and other locked feature edges.
- Compare an elbow or shadowed limb to adjacent exposed skin. Coordinate hue, brightness, and transition width; retain useful form shadow without an isolated dark or gray patch. Stronger brightening is allowed within an explicit request, but a flat white joint is not a substitute for continuity.
- Do not compensate for one contour problem by silently moving another protected feature or repainting a broad region. If the correction conflicts with identity or anatomy, reduce or revise it.

### Native geometry and optional body reference

Within the same confirmed plan, prefer controlled, small geometry changes on the original pixels when they can support the intended result. Complex missing content or hidden structure follows the existing generated/hybrid route. Use independent geometry layers, preserve the stable source, and rebuild affected downstream snapshots after replacing upstream geometry.

- RetouchRuntime **1.0.7** uses [ps_liquify_runtime.jsx](../scripts/ps_liquify_runtime.jsx) for `liquifyFace` and `liquifyMesh`; load that module before the main runtime. Read the [runtime API](ps-runtime.md) for calls, source-layer requirements, masks and path validation. The current verified environment is Photoshop **21.2.9**; production validation scope is recorded in [native-liquify evidence](../assets/evidence/native-liquify-validation.json).
- `liquifyFace` supports only the verified `faceWidth` parameter. `liquifyMesh` accepts embedded v4 `LqMe` meshes, not `LqMD` or v3; the current mesh/canvas dimensions must satisfy the API. This is a limited interface, not proof of all facial controls, automatic body shaping, multiple-person behavior or batch/version compatibility.
- The default `source: "mergedVisible"` forbids `parent` and creates a document-root, topmost snapshot. It requires a visible root-level Photoshop Background at 100% opacity/fill, Normal blending, without user/vector masks or layer effects, to establish opaque alpha. Full-canvas layer bounds do not prove opacity. The snapshot includes the current visible preceding edits, including earlier liquify layers; hiding those older layers cannot remove their baked effect from this snapshot.
- `source: "target"` creates a replacement copy and hides the donor. It accepts only omitted/`white` mask, omitted/100 opacity, and omitted/`true` visibility; ROI/black masks, reduced opacity and hidden replacement are rejected before copying. With no `parent`, it stays adjacent above the donor in the original stack/group; an explicit parent is the caller's decision to change that context. For comparison, hide the new layer and restore the donor's original visibility, then restore the edited state. Do not compare a simultaneous donor/copy composite as if it were the source. The manifest records snapshot dependencies or donor visibility, not a verified pixel-source hash; the caller binds actual source versions/hashes when provenance is needed.
- For a custom contour, use [build_liquify_mesh.py](../scripts/build_liquify_mesh.py) with image-specific, manually chosen geometry and protected regions. Historical sliders, offsets and meshes are evidence, not presets. A valid mesh or nonfolding numeric field does not establish the correct skin/hair boundary or natural proportions.
- When locating body joints would help, optionally use [build_body_reference.py](../scripts/build_body_reference.py) with an explicit local `--model-path`; read [the body-reference limits](shape-and-pose.md#可选身体参考只辅助定位) only for this route. It does not download models. Missing dependencies/model or failed detection means continue manually. Sitting and occlusion can produce confidently wrong landmarks; inspect the source before defining contours, anchors and protected regions. Neither landmarks nor a segmentation output is automatic approval of a liquify field or a finished protection mask.

The filter runs on the full canvas; a `mergedVisible` ROI mask controls presentation afterward. Feather softens that edge and does not establish a strict rectangular pixel-support boundary. Inspect the actual changed range. For a new environment or changed code, verify the intended native operation on a reversible synthetic document, including the observed pixel behavior of zero values, and cache the environment/code result. Each actual photo still needs observed displacement in the intended direction, protected-region checks, and complete contour/connection/texture review under the [three gates](quality-review.md#三道采用与交付门槛). A verified zero-parameter result or repeatable replay proves a technical property; `complete` or a new layer does not certify visual effect or aesthetic success. Local iterations inspect their affected region and context without repeating the full synthetic test suite or adding user approvals.

## Occlusion and compositing

- Treat a box or foreground object as a possible framing element. Decide whether to retain, deemphasize, crop, or partially remove it based on the pose and requested composition. Compare shoe-preserving and tighter framing only when useful or requested.
- Removing an occluder does not reveal recorded detail. Newly visible anatomy, hair, or costume is inferred. Say what was reconstructed; do not describe synthesis or borrowed texture as recovery of the hidden original.
- Protect visible source anchors such as face, hand, camera, costume marks, stockings, and shoes. Prefer narrow source-texture repair when sufficient; test generated donors for missing content or difficult local repairs while retaining the original identity anchor. Lighting or beauty candidates may also serve as references; do not replace source pixels broadly just because one generated area improved. Follow the backend-neutral adoption criteria in [engine routing](cos-retouch-engines.md#候选如何采用).
- Place the donor using the recorded source crop, resize and padding mapping; do not guess placement from layer bounds. Check separated visible anchors before masking. Use an inspectable mask covering the occluder's blurred/partly transparent footprint while protecting real fingers, clothing and prop edges. Then match material-specific color, luminance, texture scale and depth. Follow the [crop mapping guidance](cos-retouch-engines.md#局部输入与原生映射).
- For floors, grids and architectural lines, constrain each visible seam's endpoints, direction, spacing and perspective across the join. A heavily anisotropically stretched narrow strip is not a solved multi-line perspective repair. Use sufficiently contextual source/donor material and repair actual line connections; keep source detail outside the accepted coverage.
- Check the raw donor before adopting it, then reopen the actual integrated export for seam and whole-image review. An internally continuous raw floor or zero differences outside a mask does not establish that the join to the source is natural. Use the [three adoption gates](quality-review.md#三道采用与交付门槛).
- Reconcile primary light, real colored spill, rim light, background fixtures, reflections, contact shadows, and feet/floor contact as one system. Do not remove every magenta pixel when some of the scene's hand/knee spill is real.
- For edge defects, toggle suspected layers/groups to find the actual origin before patching. Distinguish source occlusion, layer alpha, group mask, adjustment spill, and shadow placement. Repair the responsible component rather than stacking a compensating smear.

## Stage reviews and proportional verification

Visual review and pixel/file checks answer different questions. A valid file or unchanged protected pixels do not establish natural appearance. A local color review does not certify contour geometry.

| Task size | Working review | Final verification |
|---|---|---|
| Small local tone/color fix | Target at native detail plus neighboring skin/materials and a fit-to-screen context view | Reopen actual output; dimensions/profile and targeted before/after or difference check where materially useful |
| Local shaping/edge repair | Complete adjacent contour/joints; inspect seam and receiving material, then full-image context | Verify affected anchors and unintended spill; inspect exported result at native detail |
| Major composition/reconstruction | Early composition/light gate, anatomy/pose gate, then entire subject outline/material/light gate | Whole-image visual review plus source/crop/profile checks and targeted protected-region verification |

- At an early stage, inspect reduced previews for hierarchy, composition, pose, perspective, light direction, and proportion. Stop detailed polishing when this structure is not yet convincing.
- At native detail, inspect affected contours and transitions: hair, jaw/neck, shoulder/joints, collar/lace, sleeves, hands, knees, shoes, and floor contact as applicable. For major reconstruction, scan the entire subject perimeter, not only the latest complained-about area.
- Optional temporary grayscale or contrast-check layers can expose uneven luminance transitions. Toggle them off for the final color assessment; preserve real skin/material variation.
- Review realistic midtone transitions as well as high-contrast edges. Reject hard hair facets, detached wisps, broad gray spill, duplicated texture, waxy skin, false joints, and conflicting shadows/reflections.
- Use targeted region checks during local iterations; run broad checks once on the stable final unless new changes or unresolved risks justify repetition. Do not repeatedly export both full-resolution crops for a one-region trial.
- If a technical report checks only selected rectangles, state that scope. Claim zero change outside the whole approved region only when that full complement was actually compared.
- Prefer the last stable native master when a repair fails. Avoid repeatedly regenerating a degraded intermediate. Follow parent-skill retry limits and report unresolved reconstruction uncertainty honestly.

## Reusable helpers and execution speed

- Use [ps_retouch_runtime.jsx](../scripts/ps_retouch_runtime.jsx) for its implemented common PS operations rather than rewriting wrappers each time. Read [its API](ps-runtime.md) when preparing a call; batch dependent layer steps into a coherent script where safe.
- Use one writer for the shared Photoshop instance, including preview export and saves. Independent read-only diagnosis, numeric mask preparation and review of a fixed candidate can run in parallel. Give scripts short recoverable stages with unique layer names and completion records; after a connector timeout, inspect actual layers and outputs before replaying a mutation. Record rollback attempts, success and errors from the manifest; if rollback fails, stop further edits from that uncertain working state and inspect it read-only or return to a verified stable source. An attempted rollback is not proof that edits were undone.
- Use [build_subject_mask.py](../scripts/build_subject_mask.py) only when an automatic visible-subject mask is likely to save work. Read [its optional environment and measured limits](mask-tools.md) and CLI help before invoking it. Do not promise its speed or hair quality without measurement.
- An automatic matte is an initial mask, not final edge QA and not reconstruction of hidden pixels. Keep its coordinate/size alignment and use it in PS without replacing the original RGB data.
- Measure diagnosis/planning, execution, mask generation/model loading, preview/review, final export, and copying separately. Identify actual repeated costs before changing tools. Persistent/reused model sessions and cached masks can help only when supported by the helper/backend.
- During adjustment, use targeted native crops plus lightweight full-image previews. Save the editable master at meaningful stable points; perform final full-resolution exports and approved crop derivation together.
- Plan the needed full-image and native crops together and avoid regenerating unchanged views. This runtime merges each preview separately; it has no `previewBatch` operation. Adopt optimizations only after a same-format representative benchmark shows a useful benefit. Pixel edits, visibility changes and color adjustments invalidate prior previews; saving preview work does not authorize reducing final quality or required inspection.
- Export an editable PSD and requested raster formats with verified dimensions/profile/bit depth. Preserve the native master; create an sRGB sharing preview when needed. A 16-bit export does not restore detail absent from an 8-bit source.
- Lossless PNG recompression can reduce storage without changing decoded pixels; verify pixel/profile preservation if claiming that result. File size is not a clarity score. Do not flatten the working master solely to shrink a delivered PNG.
- For independent native PNG comparison and recompression, read [helper usage](native-file-checks.md) only when the task needs these checks. Report an absent embedded ICC explicitly; a Photoshop profile name alone does not prove that the saved PNG embeds those bytes.
- Keep the final log short: meaningful changes, reconstruction/uncertainty, validation actually performed, timings, and output paths. Do not let repeated exhaustive reports become the main cost of a small edit.
- For route comparisons, hold the source, requested outcome and acceptance criteria constant. Count alignment/compositing, failed attempts, review repairs and saving in total time; list user waiting separately. Record actual omissions and revision counts alongside quality. A small tool benchmark or a faster model response alone does not establish an end-to-end retouching speedup.
