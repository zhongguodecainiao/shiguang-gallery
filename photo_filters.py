"""Small, persistent facets for filtering a local photo catalog."""
import math
import json
import re
from pathlib import Path

import exifread
from PIL import Image


def origin_category(name, folder):
    value = (str(name) + ' ' + str(folder)).casefold()
    if re.search(r'截图|截屏|屏幕快照|screenshot|screen[ _-]?shot|screen[ _-]?capture', value):
        return 'screenshot'
    if re.search(r'微信|wechat|weixin|micromsg|mmexport|wx[_-]image', value):
        return 'wechat'
    if re.search(r'qq截图|qq图片|qqimage|qq[_-]image|tencent[\\/]qq|[\\/]qq[\\/]', value):
        return 'qq'
    if re.search(r'下载|downloads?|浏览器下载', str(folder), re.I):
        return 'download'
    return ''


def capture_facets(path):
    """Read just camera and exposure tags; broken metadata yields empty facets."""
    tags = {}
    try:
        with Image.open(path) as image:
            ex = image.getexif()
            detail = ex.get_ifd(34665) if ex else {}
            tags = {'make': ex.get(271), 'model': ex.get(272),
                    'focal': detail.get(37386), 'aperture': detail.get(33437)}
    except Exception:
        pass
    if not any(tags.values()):
        try:
            with Path(path).open('rb') as stream:
                ex = exifread.process_file(stream, details=False, extract_thumbnail=False)
            tags = {'make': ex.get('Image Make'), 'model': ex.get('Image Model'),
                    'focal': ex.get('EXIF FocalLength'), 'aperture': ex.get('EXIF FNumber')}
        except Exception:
            return '', None, None
    def value(key):
        item = tags.get(key)
        if item is None:return None
        item = getattr(item, 'values', item)
        if isinstance(item, (list, tuple)):item = item[0] if item else None
        return item
    def number(key):
        try:
            n = float(value(key))
            return round(n, 3) if math.isfinite(n) and n > 0 else None
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):return None
    make = str(value('make') or '').strip('\x00 ')
    model = str(value('model') or '').strip('\x00 ')
    if make == 'NIKON CORPORATION':make = 'Nikon'
    camera = (make + ' ' + model if make and model and make.casefold() not in model.casefold() else model or make)[:120]
    return camera, number('focal'), number('aperture')


FOCAL_BUCKETS = {'wide': (0, 24), 'normal': (24, 70), 'tele': (70, 200), 'long': (200, None)}
APERTURE_BUCKETS = {'fast': (0, 2.9), 'medium': (2.9, 5.7), 'narrow': (5.7, None)}


def append_filter_clauses(query, where, args, extensions):
    """AND facets together; OR choices inside one facet, with optional negation."""
    fields = {'origin': ('origin_category', {'screenshot','wechat','qq','download'}),
              'camera': ('camera', None), 'extension': ('extension', extensions),
              'focal': ('focal', FOCAL_BUCKETS), 'aperture': ('aperture', APERTURE_BUCKETS)}
    for key,(column,allowed) in fields.items():
        raw = query.get('filter_' + key)
        if raw is None:
            choices = [query[key]] if query.get(key) else []  # old single-choice links
        else:
            try:choices = json.loads(raw)
            except (ValueError, TypeError):raise ValueError('筛选条件格式错误')
            if not isinstance(choices,list) or len(choices)>100:raise ValueError('筛选选项过多')
        choices = list(dict.fromkeys(value for value in choices if isinstance(value,str) and 0<len(value)<=120 and (allowed is None or value in allowed)))
        if not choices:continue
        exclude = query.get('mode_' + key) == 'exclude'
        if key in ('focal','aperture'):
            ranges=[]
            for value in choices:
                low,high=allowed[value]
                ranges.append(f'(p.{column}>=?' + (f' AND p.{column}<?' if high is not None else '') + ')')
                args.append(low)
                if high is not None:args.append(high)
            expression=' OR '.join(ranges)
            where.append(f'(p.{column} IS NULL OR NOT ({expression}))' if exclude else f'({expression})')
        else:
            marks=','.join('?' for _ in choices)
            expression=f"COALESCE(p.{column},'') {'NOT IN' if exclude else 'IN'} ({marks})"
            where.append(expression)
            args.extend(choices)
