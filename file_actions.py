"""File operations use a short-lived preview token and never overwrite existing files."""
import contextlib
import datetime as dt
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
import zipfile
from native_ops import recycle_file, choose_folder


def identity(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def reserve_file(folder, name):
    p = Path(name)
    for i in range(10001):
        target = folder / (p.name if not i else f'{p.stem} ({i}){p.suffix}')
        try:
            return target, target.open('xb')
        except FileExistsError:
            continue
    raise ValueError('同名文件过多，请选择其他文件夹。')


class FileActions:
    def __init__(self, gallery):
        self.g = gallery
        self.prepared = {}
        self.lock = threading.Lock()
        self.job = {'running': False, 'id': None}
        self.output = None

    def prepare(self, ids):
        ids = list(dict.fromkeys(int(n) for n in ids))
        if not ids or len(ids) > 10000:
            raise ValueError('请选择 1–10000 张照片。')
        rows = []
        for id_ in ids:
            row, path = self.g.get_photo(id_)
            rows.append({'id': id_, 'path': str(path), 'name': row['name'], 'identity': identity(path)})
        key = secrets.token_urlsafe(24)
        with self.lock:
            self.prepared = {k:v for k,v in self.prepared.items() if time.monotonic()-v[0] < 600}
            if len(self.prepared) > 20:
                self.prepared.clear()
            self.prepared[key] = (time.monotonic(), rows)
        return {'token': key, 'count': len(rows), 'bytes': sum(r['identity'][2] for r in rows),
                'names': [r['name'] for r in rows[:20]], 'default_destination': str(getattr(self.g,'export_dir',self.g.data.parent/'分享导出'))}

    def start(self, body):
        mode = body.get('mode')
        if mode not in ('copy', 'share', 'recycle'):
            raise ValueError('未知文件操作。')
        if mode == 'recycle' and body.get('confirm_recycle') is not True:
            raise ValueError('请先确认把原照片放入回收站。')
        destination = None
        if mode != 'recycle':
            raw = str(body.get('destination', '')).strip().strip('"')
            destination = Path(raw)
            if not destination.is_absolute() or len(destination.drive) != 2 or destination.drive[1] != ':':
                raise ValueError('请选择本机磁盘上的绝对文件夹路径，例如 E:\\照片副本。')
            destination = destination.resolve()
            default = Path(getattr(self.g,'export_dir',self.g.data.parent/'分享导出')).resolve()
            if destination == default:
                destination.mkdir(parents=True,exist_ok=True)
            if not destination.is_dir():
                raise ValueError('目标文件夹不存在，请先创建或用“浏览”选择。')
            if destination.is_relative_to(self.g.data):
                raise ValueError('请选择程序 data 数据目录以外的文件夹。')
        with self.g.lock, self.lock:
            if self.g.status['running'] or self.job['running']:
                raise ValueError('正在扫描或处理照片，请稍后重试。')
            prepared = self.prepared.get(body.get('token'))
            if not prepared or time.monotonic()-prepared[0] >= 600:
                raise ValueError('照片选择已过期，请关闭窗口重新选择。')
            rows = prepared[1]
            for row in rows:
                self.checked_source(row)
            self.prepared.pop(body['token'])
            self.output = None
            self.job = {'id': secrets.token_hex(8), 'mode': mode, 'running': True,
                        'total': len(rows), 'processed': 0, 'succeeded': 0, 'errors': [], 'output': None}
            result = dict(self.job)
            threading.Thread(target=self.run, args=(mode, rows, destination), daemon=True).start()
            return result

    def checked_source(self, row):
        _, path = self.g.get_photo(row['id'])
        if str(path) != row['path'] or identity(path) != row['identity']:
            raise ValueError('所选照片位置或内容已变化，请刷新后重新选择。')
        return path

    def snapshot(self):
        with self.lock:
            return {**self.job, 'errors': list(self.job.get('errors', []))}

    def run(self, mode, rows, destination):
        output = None
        try:
            if mode == 'share':
                name = '照片分享_'+dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')+'.zip'
                output, stream = reserve_file(destination, name)
                try:
                    used = set()
                    with stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
                        for row in rows:
                            source = self.checked_source(row)
                            base = Path(row['name']); name = base.name; n = 1
                            while name.casefold() in used:
                                name = f'{base.stem} ({n}){base.suffix}'; n += 1
                            used.add(name.casefold())
                            z.write(source, name)
                            with self.lock:
                                self.job['processed'] += 1
                    with self.lock:
                        self.job['succeeded'] = len(rows)
                except Exception:
                    # This path was exclusively created by this job; never a user's pre-existing ZIP.
                    with contextlib.suppress(OSError):
                        output.unlink()
                    raise
            else:
                for row in rows:
                    try:
                        source = self.checked_source(row)
                        if mode == 'copy':
                            target, stream = reserve_file(destination, source.name)
                            try:
                                with stream, source.open('rb') as original:
                                    shutil.copyfileobj(original, stream, 1024*1024)
                                shutil.copystat(source, target)
                            except Exception:
                                with contextlib.suppress(OSError):
                                    target.unlink()
                                raise
                        else:
                            recycle_file(source)
                            with self.g.connect() as c:
                                c.execute('UPDATE photos SET active=0 WHERE id=?', (row['id'],))
                        with self.lock:
                            self.job['succeeded'] += 1
                    except Exception as exc:
                        with self.lock:
                            self.job['errors'].append({'name': row['name'], 'error': str(exc)})
                        if mode == 'recycle':
                            break
                    finally:
                        with self.lock:
                            self.job['processed'] += 1
                if mode == 'copy':
                    output = destination
            with self.lock:
                if output:
                    self.output = output
                    self.job['output'] = str(output)
        except Exception as exc:
            with self.lock:
                self.job['errors'].append({'name': '操作未完成', 'error': str(exc)})
        finally:
            with self.lock:
                self.job['running'] = False

    def reveal(self):
        import subprocess
        if self.output and self.output.exists():
            args = ['explorer.exe', '/select,', str(self.output)] if self.output.is_file() else ['explorer.exe', str(self.output)]
            subprocess.Popen(args)
        else:
            raise ValueError('没有可打开的导出结果。')
