# Native PNG checks and lossless recompression

These helpers verify file integrity and pixels, not anatomy, lighting or aesthetic quality. Use them for a new export route, a meaningful crop/protected-region check, or a claim of lossless compression. Do not repeat full-image comparisons for every minor revision after the route is verified.

Resolve paths using [the portability convention](portability.md). The examples below are task-local PowerShell scripts with explicit parameters; they do not assume a particular installation directory. If you modify the checker's embedded .NET code, start a fresh process so an older compiled class is not reused.

## Independent PNG checker

[verify_native_png.ps1](../scripts/verify_native_png.ps1) reads inputs without editing them. Pass a new report path. Default expected depth is 16; use `-ExpectedDepth 8` explicitly for sharing previews.

```powershell
param(
  [Parameter(Mandatory=$true)][string]$SkillRoot,
  [Parameter(Mandatory=$true)][string]$JobRoot,
  [Parameter(Mandatory=$true)][string]$AfterPng,
  [Parameter(Mandatory=$true)][string]$BeforePng
)
$retouchSkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$retouchJobRoot = (Resolve-Path -LiteralPath $JobRoot).Path
& (Join-Path $retouchSkillRoot 'scripts/verify_native_png.ps1') `
  -Png $AfterPng -Before $BeforePng -AllowedRoi @(500,700,900,1150) `
  -Report (Join-Path $retouchJobRoot 'roi-check.json')
```

Replace example ROI coordinates with the actual native canvas region. `-AllowedRoi` accepts one or more flattened rectangles and checks their entire outside complement. Omit it for exact whole-image comparison. For exact crops, use `-Png $CropPng -CropOf $FullPng -CropRect @(left,top,right,bottom)` with actual integer bounds excluding right/bottom.

`-AllowMissingIcc` is an explicit exception: the report still discloses absent ICC. It does not prove a profile that was never embedded. The checker validates CRC, zlib Adler32, decoded RGB/RGBA samples, bit depth, standard PNG color-definition chunks and stable input hashes. XMP naming sRGB is not an ICC payload. Native Photoshop PNG behavior can differ by profile/version, so verify the saved bytes rather than relying only on document metadata.

## Recompression

[recompress_png.py](../scripts/recompress_png.py) needs Python 3.11+ and only the standard library. It does not need the optional mask environment.

```powershell
param(
  [Parameter(Mandatory=$true)][string]$SkillRoot,
  [Parameter(Mandatory=$true)][string]$JobRoot,
  [Parameter(Mandatory=$true)][string]$InputPng
)
$retouchSkillRoot = (Resolve-Path -LiteralPath $SkillRoot).Path
$retouchJobRoot = (Resolve-Path -LiteralPath $JobRoot).Path
python (Join-Path $retouchSkillRoot 'scripts/recompress_png.py') `
  $InputPng (Join-Path $retouchJobRoot 'full-lossless.png') `
  --report (Join-Path $retouchJobRoot 'compression.json')
if ($LASTEXITCODE -ne 0) { throw 'PNG recompression failed' }
```

The compressor refuses an existing image output, supports noninterlaced RGB/RGBA PNG at 8 or 16 bits, and only recompresses IDAT. Non-IDAT chunks remain byte-identical. Source CRC, complete decompression, filtered scanline hashes and source-file hashes are checked. Use new report/output names; verify decoded pixels and profile with the independent checker before claiming a fully validated lossless result. Flat fixtures compress much more than photographs; no fixed reduction is promised.
