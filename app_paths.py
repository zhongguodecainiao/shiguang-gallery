"""Per-user installation settings and separate catalogs for each photo directory."""
import hashlib
import os
from pathlib import Path
import winreg

PREFERENCE_KEY = r'Software\ShiguangGallery'


def registry_value(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as handle:
            value,_=winreg.QueryValueEx(handle,name)
            return os.path.expandvars(value) if isinstance(value,str) else None
    except OSError:return None


def known_folder(name, fallback):
    value=registry_value(r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders',name)
    return Path(value) if value else Path.home()/fallback


def launch_paths(root=None, data=None):
    root=Path(root or registry_value(PREFERENCE_KEY,'PhotoRoot') or known_folder('My Pictures','Pictures')).resolve()
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'ShiguangGallery'
    key=hashlib.sha256(str(root).casefold().encode('utf-8')).hexdigest()[:24]
    data=Path(data).resolve() if data else base/'catalogs'/key
    export=known_folder('Personal','Documents')/'拾光图库分享'
    if root.is_relative_to(data) or data.is_relative_to(root):
        raise ValueError('照片目录不能与图库缓存目录相互包含，请选择单独的照片文件夹。')
    return root,data,export
