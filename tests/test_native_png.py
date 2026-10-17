"""Synthetic native PNG verifier regressions; standard library + PowerShell.

Run with ``python -m unittest discover -s tests -p test_native_png.py -v``.
Set NATURAL_SHAPING_PNG_TEST_ROOT to place temporary fixtures and run logs in
a chosen directory. No Photoshop, Pillow, model, or real photograph is used.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib


# Generic LittleCMS-generated sRGB profile, with no image or personal metadata.
ICC = base64.b64decode(
    'AAACTGxjbXMEQAAAbW50clJHQiBYWVogB+oACgARAAgADAAOYWNzcE1TRlQAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1sY21zAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALZGVzYwAAAQgAAAA2Y3BydAAAAUAAAABMd3Rw'
    'dAAAAYwAAAAUY2hhZAAAAaAAAAAsclhZWgAAAcwAAAAUYlhZWgAAAeAAAAAUZ1hZWgAA'
    'AfQAAAAUclRSQwAAAggAAAAgZ1RSQwAAAggAAAAgYlRSQwAAAggAAAAgY2hybQAAAigA'
    'AAAkbWx1YwAAAAAAAAABAAAADGVuVVMAAAAaAAAAHABzAFIARwBCACAAYgB1AGkAbAB0'
    'AC0AaQBuAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAADAAAAAcAE4AbwAgAGMAbwBwAHkA'
    'cgBpAGcAaAB0ACwAIAB1AHMAZQAgAGYAcgBlAGUAbAB5WFlaIAAAAAAAAPbWAAEAAA'
    'AA0y1zZjMyAAAAAAABDEIAAAXe///zJQAAB5MAAP2Q///7of///aIAAAPcAADAblhZ'
    'WiAAAAAAAABvoAAAOPUAAAOQWFlaIAAAAAAAACSfAAAPhAAAtsNYWVogAAAAAAAAYpcA'
    'ALeHAAAY2XBhcmEAAAAAAAMAAAACZmYAAPKnAAANWQAAE9AAAApbY2hybQAAAAAAAwAA'
    'AACj1wAAVHsAAEzNAACZmgAAJmYAAA9c'
)


def chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload
            + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def png_bytes(depth=16, rgba=False, transparent=False, pixels=None, icc=ICC,
              color_type=None, interlace=0):
    maximum = (1 << depth) - 1
    channels = 4 if rgba else 3
    if pixels is None:
        pixels = [(maximum, 0, 0), (0, 0, maximum)]
        if rgba:
            pixels = [p + (maximum,) for p in pixels]
    samples = [value for pixel in pixels for value in pixel]
    assert all(len(pixel) == channels for pixel in pixels)
    encoded = bytes(samples) if depth == 8 else struct.pack('>' + 'H' * len(samples), *samples)
    header = struct.pack('>IIBBBBB', len(pixels), 1, depth,
                         color_type if color_type is not None else (6 if rgba else 2),
                         0, 0, interlace)
    parts = [b'\x89PNG\r\n\x1a\n', chunk(b'IHDR', header)]
    if icc is not None:
        parts.append(chunk(b'iCCP', b'sRGB\0\0' + zlib.compress(icc)))
    if transparent:
        parts.append(chunk(b'tRNS', struct.pack('>HHH', maximum, 0, 0)))
    parts.extend([chunk(b'IDAT', zlib.compress(b'\0' + encoded)), chunk(b'IEND', b'')])
    return b''.join(parts)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class NativePngTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = shutil.which('pwsh') or shutil.which('powershell.exe') or shutil.which('powershell')
        if not cls.shell:
            raise unittest.SkipTest('PowerShell is required for the native verifier')
        cls.script = Path(__file__).resolve().parents[1] / 'natural-shaping' / 'scripts' / 'verify_native_png.ps1'
        location = os.environ.get('NATURAL_SHAPING_PNG_TEST_ROOT')
        cls.log_root = Path(location).resolve() if location else None
        if cls.log_root:
            cls.log_root.mkdir(parents=True, exist_ok=True)
        cls.run_number = 0

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='native-png-', dir=self.log_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.wrapper = self.root / 'invoke.ps1'
        self.wrapper.write_text('''param([string]$Script,[string]$Png,[string]$Before,[string]$CropOf,
[string]$AllowedCsv,[string]$CropCsv,[string]$Report,[int]$ExpectedDepth=16,
[switch]$AllowMissingIcc,[switch]$PreloadLegacyParser)
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
if($PreloadLegacyParser){Add-Type 'public static class RetouchNativePngQA {}'}
$a=@{Png=$Png;ExpectedDepth=$ExpectedDepth}
if($Before){$a.Before=$Before};if($CropOf){$a.CropOf=$CropOf}
if($AllowedCsv){$a.AllowedRoi=[int[]]($AllowedCsv.Split(',') | ForEach-Object {[int]$_})}
if($CropCsv){$a.CropRect=[int[]]($CropCsv.Split(',') | ForEach-Object {[int]$_})}
if($Report){$a.Report=$Report};if($AllowMissingIcc){$a.AllowMissingIcc=$true}
& $Script @a
exit $LASTEXITCODE
''', encoding='utf-8')

    def image(self, name, **kwargs):
        path = self.root / name
        path.write_bytes(png_bytes(**kwargs))
        return path

    def invoke(self, target, depth=16, before=None, crop_of=None,
               allowed=None, crop=None, report=None, allow_missing=False, preload_legacy=False):
        inputs = [Path(p) for p in (target, before, crop_of) if p is not None]
        original = {p: digest(p) for p in inputs}
        cmd = [self.shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.wrapper),
               '-Script', str(self.script), '-Png', str(target), '-ExpectedDepth', str(depth)]
        for option, value in (('-Before', before), ('-CropOf', crop_of), ('-Report', report)):
            if value is not None:
                cmd.extend([option, str(value)])
        if allowed:
            cmd.extend(['-AllowedCsv', ','.join(map(str, allowed))])
        if crop:
            cmd.extend(['-CropCsv', ','.join(map(str, crop))])
        if allow_missing:
            cmd.append('-AllowMissingIcc')
        if preload_legacy:
            cmd.append('-PreloadLegacyParser')
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
        self.assertTrue(process.stdout.strip(), process.stderr)
        data = json.loads(process.stdout.lstrip('\ufeff'))
        for path, old_hash in original.items():
            self.assertEqual(digest(path), old_hash, 'Verifier changed input: ' + str(path))
        type(self).run_number += 1
        if self.log_root:
            (self.log_root / ('run-%03d.json' % self.run_number)).write_text(
                json.dumps({'test': self.id(), 'exit_code': process.returncode, 'result': data,
                            'stderr': process.stderr}, ensure_ascii=False, indent=2), encoding='utf-8')
        return process.returncode, data

    def assert_error(self, result, text=None):
        code, data = result
        self.assertEqual(code, 2, data)
        self.assertEqual(data['status'], 'error', data)
        if text:
            self.assertIn(text.lower(), (data.get('error', '') + data.get('reportError', '')).lower())

    def test_rgb_and_rgba_positive_at_both_depths(self):
        for depth in (8, 16):
            for rgba in (False, True):
                with self.subTest(depth=depth, rgba=rgba):
                    name = '%d-%s' % (depth, rgba)
                    image = self.image(name + '.png', depth=depth, rgba=rgba)
                    report = self.root / (name + '-report.json')
                    code, data = self.invoke(image, depth=depth, before=image, report=report)
                    self.assertEqual((code, data['status']), (0, 'passed'), data)
                    self.assertEqual(data['checks']['before']['alphaIncluded'], rgba)
                    self.assertEqual(data['metadata']['png']['iccBytes'], len(ICC))
                    self.assertTrue(data['checks']['before']['allPixelsIdentical'])
                    self.assertTrue(data['allInputsStable'])
                    self.assertTrue(data['inputStabilityCheckedAfterReportWrite'])
                    self.assertEqual(data['sha256AfterReportWrite']['png'], digest(image))
                    self.assertEqual(json.loads(report.read_text(encoding='utf-8')), data)

    def test_existing_report_is_not_overwritten(self):
        image = self.image('image.png')
        report = self.root / 'report.json'
        report.write_bytes(b'preserve previous report')
        self.assert_error(self.invoke(image, report=report))
        self.assertEqual(report.read_bytes(), b'preserve previous report')

    def test_report_direct_input_path_is_rejected(self):
        image = self.image('image.png')
        self.assert_error(self.invoke(image, report=image), 'Report path equals an input')

    def test_report_hardlink_cannot_overwrite_input(self):
        image = self.image('image.png')
        alias = self.root / 'report.json'
        os.link(image, alias)
        original = digest(alias)
        self.assert_error(self.invoke(image, report=alias))
        self.assertEqual(digest(alias), original)

    def test_error_report_hardlink_cannot_overwrite_other_input(self):
        before = self.image('before.png')
        invalid = self.image('invalid.png', transparent=True)
        alias = self.root / 'error-report.json'
        os.link(before, alias)
        self.assert_error(self.invoke(invalid, before=before, report=alias), 'tRNS')
        self.assertEqual(digest(alias), digest(before))

    def test_error_can_be_saved_to_new_report(self):
        image = self.image('unsupported.png', transparent=True)
        report = self.root / 'new-error-report.json'
        result = self.invoke(image, report=report)
        self.assert_error(result, 'tRNS')
        self.assertEqual(json.loads(report.read_text(encoding='utf-8')), result[1])

    def test_report_parent_failure_never_outputs_passed(self):
        image = self.image('image.png')
        blocked = self.root / 'blocked'
        blocked.write_bytes(b'not a directory')
        self.assert_error(self.invoke(image, report=blocked / 'report.json'))
        self.assertEqual(blocked.read_bytes(), b'not a directory')

    def test_report_symlink_cannot_overwrite_input(self):
        image = self.image('image.png')
        alias = self.root / 'report-link.json'
        try:
            os.symlink(image, alias)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('Creating symlinks is unavailable: ' + str(exc))
        self.assert_error(self.invoke(image, report=alias))
        self.assertTrue(alias.is_symlink())

    def test_trns_rejected_in_all_comparison_routes(self):
        for depth in (8, 16):
            opaque = self.image('opaque%d.png' % depth, depth=depth)
            transparent = self.image('key%d.png' % depth, depth=depth, transparent=True)
            calls = (
                ('single', transparent, {}),
                ('before-target', transparent, {'before': opaque}),
                ('before-reference', opaque, {'before': transparent}),
                ('roi-target', transparent, {'before': opaque, 'allowed': [0, 0, 1, 1]}),
                ('roi-reference', opaque, {'before': transparent, 'allowed': [0, 0, 1, 1]}),
                ('crop-target', transparent, {'crop_of': opaque, 'crop': [0, 0, 2, 1]}),
                ('crop-parent', opaque, {'crop_of': transparent, 'crop': [0, 0, 2, 1]}),
            )
            for route, target, options in calls:
                with self.subTest(depth=depth, route=route):
                    self.assert_error(self.invoke(target, depth=depth, **options), 'tRNS')

    def test_rgba_alpha_changes_still_detected(self):
        for depth in (8, 16):
            with self.subTest(depth=depth):
                maximum = (1 << depth) - 1
                before = self.image('rgba-before%d.png' % depth, depth=depth, rgba=True)
                after = self.image('rgba-after%d.png' % depth, depth=depth, rgba=True,
                                   pixels=[(maximum, 0, 0, 0), (0, 0, maximum, maximum)])
                code, data = self.invoke(after, depth=depth, before=before)
                self.assertEqual((code, data['status']), (1, 'failed'))
                self.assertEqual(data['metadata']['png']['nonopaquePixelCount'], 1)
                self.assertEqual(data['metadata']['png']['minimumAlpha'], 0)
                self.assertTrue(data['checks']['before']['alphaIncluded'])
                self.assertEqual(data['checks']['before']['changedPixels'], 1)

    def test_legacy_cached_parser_is_not_reused(self):
        image = self.image('key.png', transparent=True)
        self.assert_error(self.invoke(image, preload_legacy=True), 'tRNS')

    def test_allowed_roi_and_exact_crop_still_work(self):
        before = self.image('before.png')
        after = self.image('after.png', pixels=[(0, 65535, 0), (0, 0, 65535)])
        code, data = self.invoke(after, before=before, allowed=[0, 0, 1, 1])
        self.assertEqual((code, data['status']), (0, 'passed'))
        code, data = self.invoke(after, before=before, allowed=[1, 0, 2, 1])
        self.assertEqual((code, data['status']), (1, 'failed'))
        crop = self.image('blue-crop.png', pixels=[(0, 0, 65535)])
        code, data = self.invoke(crop, crop_of=before, crop=[1, 0, 2, 1])
        self.assertEqual((code, data['status']), (0, 'passed'))
        self.assertTrue(data['checks']['crop']['allPixelsIdentical'])

    def test_icc_requirements_preserved(self):
        missing = self.image('missing.png', icc=None)
        self.assert_error(self.invoke(missing), 'ICC missing')
        code, data = self.invoke(missing, allow_missing=True)
        self.assertEqual((code, data['status']), (0, 'passed'))
        invalid_icc = bytearray(ICC)
        invalid_icc[16:20] = b'GRAY'
        invalid = self.image('invalid-icc.png', icc=bytes(invalid_icc))
        self.assert_error(self.invoke(invalid), 'Invalid embedded RGB ICC')

    def test_format_and_integrity_rejections_preserved(self):
        wrong_depth = self.image('eight.png', depth=8)
        self.assert_error(self.invoke(wrong_depth), 'Expected noninterlaced')
        grayscale = self.image('unsupported-color.png', color_type=0)
        self.assert_error(self.invoke(grayscale), 'Expected noninterlaced')
        interlaced = self.image('interlaced.png', interlace=1)
        self.assert_error(self.invoke(interlaced), 'Expected noninterlaced')
        damaged = self.image('crc.png')
        body = bytearray(damaged.read_bytes())
        body[-1] ^= 1
        damaged.write_bytes(body)
        self.assert_error(self.invoke(damaged), 'CRC mismatch')
        signature = self.image('signature.png')
        body = bytearray(signature.read_bytes())
        body[0] = 0
        signature.write_bytes(body)
        self.assert_error(self.invoke(signature), 'Bad PNG signature')


if __name__ == '__main__':
    unittest.main()
