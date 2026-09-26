"""Persistent photo sources, isolated catalogs, and serialized source changes."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from folder_browser import local_drives
from user_data_backup import restore_missing_source_settings, restore_pending_catalog

SKIP_DIRECTORIES = {'windows', 'program files', 'program files (x86)', 'programdata',
                    'appdata', '$recycle.bin', 'system volume information', 'recovery',
                    '$windows.~bt', '$windows.~ws', 'perflogs', 'node_modules', '.git',
                    '.venv', 'venv', '__pycache__', '.cache', 'site-packages',
                    'apps', 'applications', '应用', '软件'}


def source_key(mode, roots):
    normalized = sorted(str(Path(p).resolve()).casefold() for p in roots)
    value = normalized[0] if mode == 'folder' else 'computer\n' + '\n'.join(normalized)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]


def write_json(path, value):
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


class SourceManager:
    def __init__(self, factory, control, initial_root, export_dir, legacy_data=None, app_dir=None):
        self.factory = factory
        self.control = Path(control).resolve()
        self.control.mkdir(parents=True, exist_ok=True)
        self.path = self.control / 'source-settings.json'
        self.lock = threading.RLock()
        self.export_dir = Path(export_dir)
        self.app_dir = Path(app_dir or (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent)).resolve()
        # The updater writes a one-shot recovery snapshot before launching setup.
        # Only a missing settings file is restored; a user's current source choice
        # is never replaced by an older snapshot.
        restore_missing_source_settings(self.path)
        self.state = {'version': 1, 'mode': 'folder', 'roots': [str(Path(initial_root).resolve())], 'aliases': {}}
        if legacy_data:
            self.state['aliases'][source_key('folder', [initial_root])] = str(Path(legacy_data).resolve())
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('mode') not in ('folder', 'computer') or not saved.get('roots'):
                raise ValueError('照片来源设置损坏，请恢复 source-settings.json 备份。')
            self.state = saved
        if self.state.get('export_dir'):self.export_dir=Path(self.state['export_dir'])
        mode, roots = self.state['mode'], [Path(p).resolve() for p in self.state['roots']]
        key = source_key(mode, roots)
        data_path = Path(self.state.get('aliases', {}).get(key, self.control / 'catalogs' / key)).resolve()
        restore_pending_catalog(key, data_path / 'gallery.sqlite3')
        self.gallery = self.make_gallery(self.state)
        write_json(self.path, self.state)

    def make_gallery(self, state):
        mode, roots = state['mode'], [Path(p).resolve() for p in state['roots']]
        key = source_key(mode, roots)
        data = Path(state.get('aliases', {}).get(key, self.control / 'catalogs' / key))
        g = self.factory(roots[0], data, roots=roots, mode=mode,
                         exclusions=[self.control, self.app_dir])
        g.catalog_key = key
        g.export_dir = self.export_dir
        return g

    def describe(self):
        drives = local_drives()
        return {'mode': self.state['mode'], 'roots': self.state['roots'],
                'catalog': self.gallery.catalog_key,
                'drives': [{'path': p, 'default': p[:1].upper() != 'G'} for p in drives]}

    def validate(self, body):
        mode = body.get('mode')
        values = body.get('roots')
        if mode not in ('folder', 'computer') or not isinstance(values, list) or not values:
            raise ValueError('请重新选择照片文件夹或要浏览的磁盘。')
        if len(values) > 26 or (mode == 'folder' and len(values) != 1):
            raise ValueError('文件夹模式请选择一个目录；全盘模式请选择本机磁盘。')
        drives = {str(Path(p).resolve()).casefold() for p in local_drives()}
        roots = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError('照片路径不能为空。')
            raw = Path(value.strip().strip('"'))
            if not raw.is_absolute() or len(raw.drive) != 2 or raw.drive[1] != ':':
                raise ValueError('请选择本机磁盘上的完整路径。')
            path = raw.resolve()
            if str(Path(path.anchor)).casefold() not in drives:
                raise ValueError('请选择已连接的本机固定磁盘。')
            if mode == 'computer' and str(path).casefold() not in drives:
                raise ValueError('全盘模式请选择磁盘根目录。')
            if not path.is_dir():
                raise ValueError(f'路径不存在或磁盘未连接：{path}')
            if path.is_relative_to(self.control) or path.is_relative_to(self.app_dir):
                raise ValueError('请选择图库程序和缓存目录以外的照片位置。')
            try:
                with os.scandir(path) as entries:
                    next(entries, None)
            except OSError:
                raise ValueError(f'无法读取此目录：{path}') from None
            if path not in roots:
                roots.append(path)
        return mode, sorted(roots, key=lambda p: str(p).casefold())

    def apply(self, server, body):
        # The HTTP handler also holds this lock for every file/album mutation.
        with self.lock:
            mode, roots = self.validate(body)
            old = self.gallery
            if old.files.snapshot()['running']:
                raise ValueError('正在复制、分享或删除照片，请等当前操作结束再切换来源。')
            if not old.stop_scan():
                raise ValueError('正在停止扫描，请稍后再次应用。当前照片来源尚未改变。')
            state = {**self.state, 'mode': mode, 'roots': [str(p) for p in roots]}
            try:
                new = self.make_gallery(state)
                new.token = old.token
                write_json(self.path, state)
            except Exception:
                old.start_scan()
                raise
            self.state = state
            self.gallery = new
            server.gallery = new
            new.start_scan()
            return {'ok': True, 'catalog': new.catalog_key}
