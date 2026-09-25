"""Rename a catalog folder in place while retaining photo IDs and memberships."""
import os
from pathlib import Path
import re
from photo_sources import SKIP_DIRECTORIES


def rename_folder(gallery, folder, name):
    if (not isinstance(name, str) or not 1 <= len(name) <= 120
            or name != name.strip() or name.endswith('.')
            or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
            or name in ('.', '..')
            or re.match(r'^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)', name, re.I)):
        raise ValueError('请输入有效的文件夹名称（1–120 个字符，不含路径或特殊符号）。')
    if (name.lower().endswith(('.lrdata', '.lrcat-data')) or name == '照片处理program'
            or (gallery.mode == 'computer' and (name.startswith('.') or name.casefold() in SKIP_DIRECTORIES))):
        raise ValueError('此名称会被图库扫描排除，请换一个名称。')
    if not isinstance(folder, str) or not folder:
        raise ValueError('请选择要重命名的照片文件夹。')
    raw = gallery.root / folder
    source = raw.resolve()
    # A rename must remain under the current source and must not move catalog/program data.
    if (source != Path(os.path.abspath(raw)) or not gallery.allowed_path(source)
            or source in gallery.roots or source == Path(source.anchor)
            or any(p.is_relative_to(source) for p in gallery.exclusions)):
        raise ValueError('照片来源根目录、磁盘和程序目录不能在这里重命名。')
    if not source.is_dir() or source.is_symlink() or getattr(source.lstat(), 'st_file_attributes', 0) & 0x400:
        raise ValueError('文件夹不存在或位置已变化，请刷新后重试。')
    target = source.with_name(name)
    if target.parent != source.parent or not gallery.allowed_path(target.resolve()):
        raise ValueError('请选择要重命名的照片文件夹。')
    with gallery.lock, gallery.files.lock:
        if gallery.status['running'] or gallery.files.job['running']:
            raise ValueError('正在扫描或处理照片，请稍后重试。')
        if target.exists() and target != source:
            raise ValueError('此位置已有同名文件夹，请换一个名称。')
        moved = False
        try:
            with gallery.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                updates = []
                for row in db.execute('SELECT id,path,file_key,active FROM photos'):
                    old = gallery.root / row['path']
                    if old.is_relative_to(source):
                        new = target / old.relative_to(source)
                        path = str(new if gallery.mode == 'computer' else new.relative_to(gallery.root))
                        parent = str(new.parent if gallery.mode == 'computer' else new.parent.relative_to(gallery.root))
                        key = str(new) if row['file_key'] == str(old) else row['file_key']
                        updates.append((path, parent, key, row['id'], row['active']))
                if not any(r[4] for r in updates):
                    raise ValueError('请选择要重命名的照片文件夹。')
                if source.name != name:
                    # Windows rename fails on an existing destination; never merge directories.
                    os.rename(source, target)
                    moved = True
                db.executemany('UPDATE photos SET path=?,folder=?,file_key=? WHERE id=?', [r[:4] for r in updates])
        except Exception as exc:
            if moved:
                os.rename(target, source)
            if isinstance(exc, OSError):
                raise ValueError('无法重命名文件夹，请检查权限或关闭占用它的程序。') from exc
            raise
        gallery.files.prepared.clear()
    return {'ok': True, 'folder': str(target if gallery.mode == 'computer' else target.relative_to(gallery.root)), 'name': name}
