"""Check local site links and image dimensions without a browser or network."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.images, self.ids = [], [], set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        for key in ('src','href'):
            if attrs.get(key): self.refs.append(attrs[key])
        if tag == 'img': self.images.append(attrs)


def check(root):
    pages, errors, links = {}, [], 0
    for path in sorted((root/'docs').glob('*.html')):
        page = Page()
        page.feed(path.read_text(encoding='utf-8-sig'))
        pages[path.resolve()] = page
    for path,page in pages.items():
        for value in page.refs:
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc: continue
            target = (path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            links += 1
            if root not in target.parents and target != root:
                errors.append({'page':path.name,'unsafe':value})
            elif not target.exists():
                errors.append({'page':path.name,'missing':value})
            elif parsed.fragment and target in pages and unquote(parsed.fragment) not in pages[target].ids:
                errors.append({'page':path.name,'missing_anchor':value})
        for attrs in page.images:
            parsed = urlsplit(attrs.get('src',''))
            if parsed.scheme or parsed.netloc: continue
            image = (path.parent/unquote(parsed.path)).resolve()
            if root not in image.parents or not image.is_file(): continue
            try:
                with Image.open(image) as im:
                    im.load()
                    if attrs.get('width') and attrs.get('height') and im.size != (int(attrs['width']),int(attrs['height'])):
                        errors.append({'page':path.name,'image_size':image.name,'actual':list(im.size)})
            except (OSError,ValueError) as exc:
                errors.append({'page':path.name,'image':image.name,'error':str(exc)})
    return {'passed':not errors,'pages':len(pages),'local_links':links,'errors':errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = check(args.root.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
