"""Read-only package integrity and local-reference check; Python standard library only.

Run from any working directory. This checks packaged files, not photograph quality,
Photoshop compatibility, external URLs, or whether models/connections are installed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

TEXT = {'.md', '.json', '.yaml', '.yml', '.txt', '.py', '.ps1', '.jsx'}
DRIVE = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]')
MACHINE = re.compile(r'(?:/Users/[^/\s]+/|/home/[^/\s]+/|codex://threads/)')
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^\n]+?)\)')
SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def within(path, root):
    # pathlib.is_relative_to was added after Python 3.8.
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

def slug(text):
    return re.sub(r'[^\w\- ]', '', text.lower()).replace(' ', '-')

def headings(path):
    found, counts = set(), {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if re.match(r'^#{1,6} ', line):
            base = slug(line.lstrip('#').strip())
            count = counts.get(base, 0)
            found.add(base if not count else base + '-' + str(count))
            counts[base] = count + 1
    return found

def validate(root):
    errors, links, json_paths = [], 0, 0
    files = sorted(p for p in root.rglob('*') if p.is_file())
    manifest_file = root / 'package-manifest.json'

    def check_target(owner, value, base, anchor=False):
        target_name, _, fragment = unquote(value).partition('#')
        target = (base / target_name).resolve() if target_name else owner
        if not within(target, root):
            errors.append({'file':str(owner.relative_to(root)), 'outside_package':value})
        elif not target.exists():
            errors.append({'file':str(owner.relative_to(root)), 'missing':value})
        elif anchor and fragment and target.suffix == '.md' and fragment not in headings(target):
            errors.append({'file':str(owner.relative_to(root)), 'missing_anchor':value})

    def walk_json(owner, obj, base):
        nonlocal json_paths
        if isinstance(obj, dict):
            for v in obj.values(): walk_json(owner, v, base)
        elif isinstance(obj, list):
            for v in obj: walk_json(owner, v, base)
        elif isinstance(obj, str) and not SCHEME.match(obj):
            # Explicit resource paths, excluding prose and template placeholders.
            if re.match(r'^(?:assets/|references/|scripts/|(?:\.\./)+|\./)',obj) and '\n' not in obj and '<' not in obj:
                json_paths += 1
                check_target(owner,obj,base)

    for path in files:
        if path.is_symlink(): errors.append({'symlink':str(path.relative_to(root))})
        if path.suffix.lower() not in TEXT: continue
        try: text = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            errors.append({'encoding':str(path.relative_to(root))}); continue
        for match in list(DRIVE.finditer(text)) + list(MACHINE.finditer(text)):
            # This validator's own pattern constants describe what to reject.
            if path.resolve() == Path(__file__).resolve(): continue
            errors.append({'fixed_machine_path':str(path.relative_to(root)), 'line':text[:match.start()].count('\n')+1})
        if path.suffix == '.md':
            no_code = re.sub(r'```[\s\S]*?```','',text)
            for match in LINK.finditer(no_code):
                value = match.group(1).strip().strip('<>')
                if SCHEME.match(value): continue
                links += 1
                check_target(path,value,path.parent,anchor=True)
        if path.suffix == '.json':
            try: obj = json.loads(text)
            except ValueError as exc:
                errors.append({'json':str(path.relative_to(root)), 'error':str(exc)}); continue
            if path == manifest_file: continue
            portable = obj.get('_portability',{}) if isinstance(obj,dict) else {}
            base = root if portable.get('path_base') == 'skill-root' else path.parent
            walk_json(path,obj,base)
    if not manifest_file.exists():
        errors.append({'missing':'package-manifest.json'})
    else:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8-sig'))
        expected=set()
        for entry in manifest['files']:
            rel=entry['file']; expected.add(rel); path=(root/rel).resolve()
            if not within(path, root) or not path.is_file():
                errors.append({'manifest_missing_or_unsafe':rel}); continue
            if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
                errors.append({'manifest_mismatch':rel})
        actual={p.relative_to(root).as_posix() for p in files if p != manifest_file}
        for rel in sorted(actual-expected): errors.append({'unlisted_file':rel})
        for rel in sorted(expected-actual): errors.append({'absent_file':rel})
    return {'passed':not errors,'files':len(files),'local_markdown_links':links,
            'explicit_json_paths':json_paths,'errors':errors,
            'scope':'Package integrity and explicit local references only; not visual acceptance or runtime compatibility.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    result=validate(args.root.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
