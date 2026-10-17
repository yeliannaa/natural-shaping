"""Generate current public example labels from the bundled catalogue; no private data."""
import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = 'natural-shaping/assets/examples/index.json'
MARKER = re.compile(r'<!-- example-status:([a-z0-9-]+) -->.*?<!-- /example-status -->', re.S)


def generated(root):
    package = root / 'natural-shaping'
    catalogue = json.loads((root / CATALOGUE).read_text(encoding='utf-8-sig'))
    rows = catalogue['examples']
    by_id = {row['id']: row for row in rows}
    if len(rows) != len(by_id):
        raise ValueError('Duplicate example ID')
    for row in rows:
        for key in ('label', 'version', 'reference_version', 'file', 'status', 'use'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Missing example field: '+key)
        image = (package / row['file']).resolve()
        if package.resolve() not in image.parents or not image.is_file():
            raise ValueError('Missing or unsafe example image: '+row['id'])

    def label(match):
        row = by_id[match.group(1)]
        return '<!-- example-status:'+row['id']+' -->'+html.escape(row['label']+'；'+row['status'])+'<!-- /example-status -->'

    outputs = {}
    readme = package/'assets/examples/README.md'
    text = readme.read_text(encoding='utf-8-sig')
    table = '\n'.join([
        '| 人物／文件 | 版本状态 | 适合参考的内容 |',
        '|---|---|---|',
        *['| ['+row['label']+']('+Path(row['file']).name+') | '+row['status']+' | '+row['use']+' |' for row in rows],
    ])
    start, end = '<!-- example-catalogue:start -->', '<!-- example-catalogue:end -->'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Example table markers missing or duplicated')
    outputs[readme] = text[:text.index(start)+len(start)]+'\n'+table+'\n'+text[text.index(end):]

    for path in sorted((root/'docs').glob('*')):
        if path.suffix not in ('.html','.md'):
            continue
        text = path.read_text(encoding='utf-8-sig')
        if '<!-- example-status:' in text:
            outputs[path] = MARKER.sub(label,text)

    aesthetic = package/'references/aesthetic-reference/index.json'
    data = json.loads(aesthetic.read_text(encoding='utf-8-sig'))
    versions = {Path(row['file']).name: row['reference_version'] for row in rows}
    def walk(obj):
        if isinstance(obj, dict):
            if 'path' in obj and 'version' in obj:
                name = Path(obj['path']).name
                if name in versions:
                    obj['version'] = versions[name]
            for value in obj.values(): walk(value)
        elif isinstance(obj,list):
            for value in obj: walk(value)
    walk(data)
    outputs[aesthetic] = json.dumps(data,ensure_ascii=False,indent=2)+'\n'

    showcase = root/'docs/assets/highp-showcase.json'
    data = json.loads(showcase.read_text(encoding='utf-8-sig'))
    highp_ids = {'yao-highp-portrait':'yao135', 'yao-highp-wide':'yao140'}
    for case in data['cases']:
        if case['id'] in highp_ids:
            case['result_version'] = by_id[highp_ids[case['id']]]['version']
    outputs[showcase] = json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--write',action='store_true',help='Update generated labels; otherwise check only.')
    args = parser.parse_args()
    stale = []
    for path,expected in generated(args.root.resolve()).items():
        raw = path.read_bytes()
        if raw.decode('utf-8-sig').replace('\r\n','\n') == expected.replace('\r\n','\n'):
            continue
        stale.append(path.relative_to(args.root.resolve()).as_posix())
        if args.write:
            newline = '\r\n' if b'\r\n' in raw else '\n'
            path.write_bytes(expected.replace('\r\n','\n').replace('\n',newline).encode('utf-8'))
    print(json.dumps({'passed':not stale or args.write,'updated' if args.write else 'stale':stale},ensure_ascii=False,indent=2))
    return 0 if not stale or args.write else 1


if __name__ == '__main__':
    raise SystemExit(main())
