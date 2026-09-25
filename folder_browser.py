"""Read-only, one-level browsing of local folders for export destinations."""
import ctypes
import os
from pathlib import Path


def local_drives():
    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    return [f'{chr(65+n)}:\\' for n in range(26)
            if mask & (1 << n) and kernel.GetDriveTypeW(f'{chr(65+n)}:\\') == 3]


def list_folders(value='', initial=False):
    roots = local_drives()
    raw = str(value or '').strip().strip('"')
    if not raw:
        return {'path': '', 'parent': None, 'roots': roots,
                'folders': [{'name': p, 'path': p} for p in roots], 'notice': ''}
    path = Path(raw)
    if not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ':':
        raise ValueError('请输入本机文件夹的完整路径，例如 E:\\资料库。')
    path = path.resolve()
    if path.anchor.upper() not in [r.upper() for r in roots]:
        raise ValueError('请选择本机固定磁盘上的文件夹。')
    notice = ''
    if initial:
        while not path.exists() and path.parent != path:
            path = path.parent
            notice = '原路径尚不存在，已显示最近的上级文件夹。'
    if not path.is_dir():
        raise ValueError('文件夹不存在，请检查路径。')
    try:
        folders = []
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    # Avoid system/private folders and directory reparse-point redirects.
                    stat = entry.stat(follow_symlinks=False)
                    if stat.st_file_attributes & (0x2 | 0x4 | 0x400):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        folders.append({'name': entry.name, 'path': str(path/entry.name)})
                except OSError:
                    continue
    except PermissionError:
        raise ValueError('没有权限读取这个文件夹，请选择其他位置。') from None
    folders.sort(key=lambda r: r['name'].casefold())
    return {'path': str(path), 'parent': str(path.parent) if path.parent != path else '',
            'roots': roots, 'folders': folders, 'notice': notice}
