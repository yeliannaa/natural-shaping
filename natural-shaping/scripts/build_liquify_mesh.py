"""Build a Photoshop Liquify v4 mesh from manually reviewed source-pixel regions.

Python standard library only. This never edits an image, detects a body, or
decides an aesthetic amount. Model landmarks are not accepted as control input.
The verified encoding uses a four-pixel grid and dimensions divisible by four.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

MAX_MESH_BYTES = 134217728  # Same bound as ps_liquify_runtime.jsx.


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return float(value)


def pair(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f'{label} must have two numbers')
    return tuple(number(v, label) for v in value)


def build(spec):
    allowed = {'width', 'height', 'regions', 'protected_rois', 'source_sha256', 'coordinate_basis'}
    if set(spec) - allowed:
        raise ValueError('Unknown spec fields: ' + ', '.join(sorted(set(spec)-allowed)))
    width, height = spec.get('width'), spec.get('height')
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 4 or v > 16384 or v % 4 for v in [width, height]):
        raise ValueError('Verified v4 meshes require integer dimensions 4..16384 divisible by four; use another verified route for other dimensions')
    if spec.get('coordinate_basis', 'source_canvas_pixels') != 'source_canvas_pixels':
        raise ValueError('Regions must use the actual current source canvas pixels')
    regions = spec.get('regions')
    if not isinstance(regions, list) or len(regions) > 32:
        raise ValueError('regions must be a list of at most 32 manually reviewed regions; [] creates an identity mesh')
    parsed = []
    for region in regions:
        if not isinstance(region, dict) or set(region) != {'center', 'radius', 'sample_offset_pixels'}:
            raise ValueError('Each region requires only center, radius, sample_offset_pixels')
        center = pair(region['center'], 'center')
        radius = pair(region['radius'], 'radius')
        offset = pair(region['sample_offset_pixels'], 'sample_offset_pixels')
        if not (0 <= center[0] < width and 0 <= center[1] < height) or min(radius) < 4:
            raise ValueError('center must be on canvas and each radius at least four source pixels')
        if max(radius) > max(width, height)*2 or max(abs(v) for v in offset) > max(width, height):
            raise ValueError('Region radius or sampling offset exceeds canvas bounds')
        parsed.append((center, radius, offset))
    protected = spec.get('protected_rois', [])
    if not isinstance(protected, list):
        raise ValueError('protected_rois must be a list')
    for box in protected:
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('Protected ROI requires [left,top,right,bottom]')
        for v in box:
            number(v, 'protected_roi')
        if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            raise ValueError('Protected ROI must be nonempty and within the canvas')
    source_hash = spec.get('source_sha256')
    if source_hash is not None and (not isinstance(source_hash, str) or len(source_hash) != 64 or any(v not in '0123456789abcdefABCDEF' for v in source_hash)):
        raise ValueError('source_sha256 must be a 64-digit hex hash when supplied')
    mw, mh = width//4, height//4

    def field(x, y):
        dx = dy = 0.0
        for center, radius, offset in parsed:
            r2 = ((x-center[0])/radius[0])**2 + ((y-center[1])/radius[1])**2
            if r2 < 1:
                weight = (1-r2)**2
                dx += offset[0]*weight
                dy += offset[1]*weight
        # Soft neutral guard covers the supplied rectangle plus 4 px outside.
        # This assists interpolation protection; image-domain QA remains required.
        for l, t, r, b in protected:
            distance = max(l-x, x-r, t-y, y-b, 0)
            if distance < 8:
                z = max(0.0, min(1.0, (distance-4)/4))
                guard = z*z*(3-2*z)
                dx *= guard
                dy *= guard
        return dx/4, dy/4

    header = struct.pack('>I', 4)+b'yfqLhseM'+struct.pack('<13I', 2,mw,mh,0,1,0,0,height,width,0,0,height,width)
    body = bytearray()
    min_jacobian = 1.0
    max_sample_offset = 0.0
    nonzero_cells = 0
    support = None
    previous_row = None
    for gy in range(mh):
        # Check the float32 values that Photoshop actually receives.
        row = [struct.unpack('<ff', struct.pack('<ff', *field(gx*4, gy*4))) for gx in range(mw)]
        for gx, (dx, dy) in enumerate(row):
            max_sample_offset = max(max_sample_offset, math.hypot(dx*4, dy*4))
            if dx or dy:
                nonzero_cells += 1
                if support is None:
                    support = [gx*4,gy*4,gx*4,gy*4]
                else:
                    support = [min(support[0],gx*4),min(support[1],gy*4),max(support[2],gx*4),max(support[3],gy*4)]
        if previous_row is not None:
            # Cell corner orientation: sampled source coordinate Jacobian.
            # Discrete positivity detects sampled folds; not a visual guarantee.
            for gx in range(mw-1):
                a, b, c, d = previous_row[gx], previous_row[gx+1], row[gx], row[gx+1]
                horizontal = [(b[0]-a[0], b[1]-a[1]), (d[0]-c[0], d[1]-c[1])]
                vertical = [(c[0]-a[0], c[1]-a[1]), (d[0]-b[0], d[1]-b[1])]
                for hx, hy in horizontal:
                    for vx, vy in vertical:
                        jac = (1+hx)*(1+vy)-vx*hy
                        min_jacobian = min(min_jacobian, jac)
        previous_row = row
        pos = 0
        while pos < mw:
            start = pos
            while pos < mw and row[pos] == (0.0, 0.0):
                pos += 1
            body += struct.pack('<I', pos-start)
            if pos == mw:
                break
            start = pos
            while pos < mw and row[pos] != (0.0, 0.0):
                pos += 1
            body += struct.pack('<I', pos-start)
            for dx, dy in row[start:pos]:
                body += struct.pack('<ff', dx, dy)
        if len(header)+len(body) > MAX_MESH_BYTES:
            raise ValueError('Mesh exceeds the native runtime 128 MiB input limit; reduce the supported canvas or field')
    if min_jacobian <= 0:
        raise ValueError('Requested field contains a sampled fold; reduce or redesign the actual regions')
    data = header+body
    report = {
        'schema_version': 1, 'mesh_version': 4, 'encoding': '64_byte_header_row_RLE_float32_xy',
        'width': width, 'height': height, 'grid_width': mw, 'grid_height': mh, 'grid_step_pixels': 4,
        'coordinate_basis': 'source_canvas_pixels', 'field_semantics': 'inverse sampling offset; visible movement has opposite direction',
        'regions': regions, 'protected_rois': protected, 'source_sha256': source_hash,
        'source_hash_verification': 'caller must bind and check the source; this builder does not read the photo',
        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'nonzero_cells': nonzero_cells,
        'nonzero_grid_extent_inclusive': support, 'maximum_sampling_offset_pixels': max_sample_offset,
        'minimum_sampled_jacobian': min_jacobian,
        'jacobian_check': 'all four cell corners after float32 quantization',
        'review_status': 'needs_pixel_and_visual_review',
        'limits': ['Native validation originally used Photoshop 21.2.9.', 'Positive sampled Jacobian is not aesthetic acceptance.',
                   'Protected rectangles and interpolation need actual output QA.', 'Old image coordinates and amplitudes are not presets.']}
    return data, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path, help='JSON with width,height,manually reviewed regions and optional protected_rois')
    parser.add_argument('--output', required=True, type=Path, help='New .msh file; sidecar .json is written alongside it')
    args = parser.parse_args()
    try:
        spec_path = args.spec.resolve(strict=True)
        output = args.output.resolve()
        metadata = output.with_suffix('.json')
        if output.suffix.lower() != '.msh' or output.exists() or metadata.exists():
            raise ValueError('Use a new .msh output and sidecar name; existing files are never overwritten')
        skill_root = Path(__file__).resolve().parents[1]
        if skill_root == output or skill_root in output.parents:
            raise ValueError('Write mesh artifacts to the authorized job directory, not the installed skill')
        spec = json.loads(spec_path.read_text(encoding='utf-8-sig'))
        if not isinstance(spec, dict):
            raise ValueError('spec must be a JSON object')
        data, report = build(spec)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(data)
        report['mesh_file'] = output.name
        with metadata.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'status':'complete','mesh':str(output),'metadata':str(metadata),
                          'bytes':len(data),'review_status':report['review_status']}, ensure_ascii=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, struct.error) as exc:
        print(json.dumps({'status':'failed','error':str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
