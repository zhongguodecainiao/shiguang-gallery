"""Local, one-shot recovery snapshots for user data before app upgrades."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3


def backup_root():
    local = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    return local / 'ShiguangGallery' / 'update-backups'


def _db_backup(source_path, target_path):
    source = sqlite3.connect(Path(source_path).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(target_path, timeout=30)
    try:
        source.backup(target)
        result = target.execute('PRAGMA integrity_check').fetchone()
        if not result or result[0] != 'ok':
            raise sqlite3.DatabaseError('更新前的图库数据库快照未通过完整性检查')
    finally:
        target.close()
        source.close()


def create_pending_snapshot(control, active_db, catalog_key, source_settings):
    """Snapshot SQLite catalogs and small local settings before handing off setup."""
    root = backup_root()
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    folder = root / stamp
    folder.mkdir()
    control = Path(control).resolve()
    source_settings = Path(source_settings).resolve()
    manifest = {
        'created_at': dt.datetime.now().isoformat(timespec='seconds'),
        'source_settings_path': str(source_settings),
        'catalogs': [],
    }
    try:
        if source_settings.is_file():
            settings_copy = folder / 'source-settings.json'
            shutil.copy2(source_settings, settings_copy)
            manifest['source_settings_backup'] = settings_copy.name
        for setting_name in ('ui-preferences.json', 'release-notes-seen.json'):
            source = control / setting_name
            if source.is_file():
                shutil.copy2(source, folder / setting_name)

        candidates = set((control / 'catalogs').rglob('gallery.sqlite3'))
        active_db = Path(active_db).resolve()
        if active_db.is_file():
            candidates.add(active_db)
        for index, source in enumerate(sorted(candidates, key=lambda p: str(p).casefold())):
            if not source.is_file():
                continue
            if source == active_db:
                key = str(catalog_key)
            else:
                key = source.parent.name
            name = f'catalog-{index:03d}.sqlite3'
            _db_backup(source, folder / name)
            manifest['catalogs'].append({
                'catalog_key': key,
                'db_path': str(source.resolve()),
                'backup_file': name,
            })

        manifest_path = folder / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        pending = root / 'pending.json'
        temp = pending.with_name(pending.name + '.' + secrets.token_hex(4) + '.tmp')
        temp.write_text(json.dumps({'manifest': str(manifest_path)}, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, pending)
        return str(pending)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def cancel_pending_snapshot():
    try:
        (backup_root() / 'pending.json').unlink(missing_ok=True)
    except OSError:
        pass


def _read_pending():
    pending = backup_root() / 'pending.json'
    try:
        payload = json.loads(pending.read_text(encoding='utf-8'))
        manifest_path = Path(payload['manifest']).resolve()
        if not manifest_path.is_relative_to(backup_root().resolve()):
            return pending, None
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['_folder'] = manifest_path.parent
        return pending, manifest
    except (OSError, ValueError, KeyError, TypeError):
        return pending, None


def restore_missing_source_settings(path):
    """Restore only if the settings file vanished; never replace current choices."""
    path = Path(path).resolve()
    if path.exists():
        return False
    _, manifest = _read_pending()
    if not manifest or Path(manifest.get('source_settings_path', '')).resolve() != path:
        return False
    backup_name = manifest.get('source_settings_backup')
    if not backup_name:
        return False
    source = (manifest['_folder'] / backup_name).resolve()
    if not source.is_relative_to(manifest['_folder']) or not source.is_file():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, path)
    return True


def _curation_counts(connection):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'photos', 'albums', 'album_photos'} <= tables:
        raise sqlite3.DatabaseError('图库数据库缺少相册或照片表')
    favorites = connection.execute('SELECT count(*) FROM photos WHERE favorite=1').fetchone()[0]
    albums = connection.execute('SELECT count(*) FROM albums').fetchone()[0]
    memberships = connection.execute('SELECT count(*) FROM album_photos').fetchone()[0]
    return favorites, albums, memberships


def _merge_curation(source_path, target_path):
    source = sqlite3.connect(Path(source_path).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(target_path, timeout=30)
    target.row_factory = sqlite3.Row
    try:
        old_counts = _curation_counts(source)
        check = target.execute('PRAGMA quick_check').fetchone()
        if not check or check[0] != 'ok':
            raise sqlite3.DatabaseError('database disk image malformed: quick_check failed')
        new_counts = _curation_counts(target)
        if not any(old_counts) or any(new_counts):
            return False
        with target:
            by_path = {str(row['path']).casefold(): row['id']
                       for row in target.execute('SELECT id,path FROM photos')}
            for row in source.execute('SELECT path FROM photos WHERE favorite=1'):
                photo_id = by_path.get(str(row['path']).casefold())
                if photo_id is not None:
                    target.execute('UPDATE photos SET favorite=1 WHERE id=?', (photo_id,))

            album_ids = {}
            for album in source.execute('SELECT id,name,created FROM albums'):
                target.execute('INSERT OR IGNORE INTO albums(name,created) VALUES(?,?)',
                               (album['name'], album['created']))
                current = target.execute('SELECT id FROM albums WHERE name=?', (album['name'],)).fetchone()
                if current:
                    album_ids[album['id']] = current['id']
            for membership in source.execute(
                    'SELECT a.id album_id,p.path FROM album_photos ap '
                    'JOIN albums a ON a.id=ap.album_id JOIN photos p ON p.id=ap.photo_id'):
                photo_id = by_path.get(str(membership['path']).casefold())
                album_id = album_ids.get(membership['album_id'])
                if photo_id is not None and album_id is not None:
                    target.execute('INSERT OR IGNORE INTO album_photos(album_id,photo_id) VALUES(?,?)',
                                   (album_id, photo_id))
        return True
    finally:
        target.close()
        source.close()


def _restore_corrupt_catalog(source_path, target_path, archive_dir):
    """Replace a proven-unreadable catalog only after preserving it and sidecars."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / ('damaged-current-' + secrets.token_hex(4))
    archive.mkdir()
    staged = target_path.with_name(target_path.name + '.restore-' + secrets.token_hex(4))
    _db_backup(source_path, staged)
    originals = [target_path, *(Path(str(target_path) + suffix)
                                for suffix in ('-wal', '-shm', '-journal'))]
    copied = []
    try:
        for original in originals:
            if original.is_file():
                saved = archive / original.name
                shutil.copy2(original, saved)
                copied.append((original, saved))
        for original, saved in copied:
            if original.name != target_path.name:
                original.unlink(missing_ok=True)
        os.replace(staged, target_path)
        return True
    except Exception:
        for original, saved in copied:
            if not original.exists() and saved.exists():
                shutil.copy2(saved, original)
        raise
    finally:
        staged.unlink(missing_ok=True)


def restore_pending_catalog(catalog_key, db_path):
    """Recover only the same source catalog, and consume this one-shot marker."""
    pending, manifest = _read_pending()
    if not manifest:
        pending.unlink(missing_ok=True)
        return False
    db_path = Path(db_path).resolve()
    try:
        for entry in manifest.get('catalogs', []):
            if (str(entry.get('catalog_key', '')).casefold() != str(catalog_key).casefold()
                    or Path(entry.get('db_path', '')).resolve() != db_path):
                continue
            source = (manifest['_folder'] / entry.get('backup_file', '')).resolve()
            if not source.is_relative_to(manifest['_folder']) or not source.is_file():
                continue
            if not db_path.exists():
                _db_backup(source, db_path)
                return True
            try:
                return _merge_curation(source, db_path)
            except sqlite3.DatabaseError as exc:
                if not any(text in str(exc).casefold()
                           for text in ('malformed', 'not a database', 'no such table', 'no such column')):
                    return False
                return _restore_corrupt_catalog(source, db_path, manifest['_folder'])
        return False
    finally:
        pending.unlink(missing_ok=True)
