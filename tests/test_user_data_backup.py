import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from user_data_backup import (
    create_pending_snapshot,
    restore_missing_source_settings,
    restore_pending_catalog,
)


SCHEMA = '''
CREATE TABLE photos(id INTEGER PRIMARY KEY, path TEXT NOT NULL, favorite INTEGER DEFAULT 0);
CREATE TABLE albums(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created TEXT NOT NULL);
CREATE TABLE album_photos(album_id INTEGER, photo_id INTEGER, PRIMARY KEY(album_id,photo_id));
'''


class UserDataBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_local = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = str(Path(self.temp.name) / 'local')
        self.control = Path(self.temp.name) / 'control'
        self.settings = self.control / 'source-settings.json'
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({'mode': 'folder', 'roots': ['C:/Photos']}), encoding='utf-8')
        self.db = self.control / 'catalogs' / 'catalog-test' / 'gallery.sqlite3'
        self.db.parent.mkdir(parents=True)
        conn = sqlite3.connect(self.db)
        try:
            conn.executescript(SCHEMA)
            conn.execute('INSERT INTO photos VALUES(1, ?, 1)', ('C:/Photos/favorite.jpg',))
            conn.execute('INSERT INTO photos VALUES(2, ?, 0)', ('C:/Photos/album.jpg',))
            conn.execute('INSERT INTO albums VALUES(7, ?, ?)', ('Trip', '2026-09-26'))
            conn.execute('INSERT INTO album_photos VALUES(7, 2)')
            conn.commit()
        finally:
            conn.close()
        self.pending = create_pending_snapshot(self.control, self.db, 'catalog-test', self.settings)

    def tearDown(self):
        if self.old_local is None:
            os.environ.pop('LOCALAPPDATA', None)
        else:
            os.environ['LOCALAPPDATA'] = self.old_local
        self.temp.cleanup()

    def test_merges_missing_curation_for_the_same_catalog_only(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute('UPDATE photos SET favorite=0')
            conn.execute('DELETE FROM album_photos')
            conn.execute('DELETE FROM albums')
            conn.commit()
        finally:
            conn.close()
        self.assertTrue(restore_pending_catalog('catalog-test', self.db))
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute('SELECT favorite FROM photos WHERE id=1').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT name FROM albums').fetchone()[0], 'Trip')
            self.assertEqual(conn.execute('SELECT count(*) FROM album_photos').fetchone()[0], 1)
        finally:
            conn.close()

    def test_never_replaces_a_present_settings_file(self):
        changed = {'mode': 'folder', 'roots': ['D:/NewPhotos']}
        self.settings.write_text(json.dumps(changed), encoding='utf-8')
        self.assertFalse(restore_missing_source_settings(self.settings))
        self.assertEqual(json.loads(self.settings.read_text(encoding='utf-8')), changed)

    def test_does_not_overwrite_any_existing_favorites_or_albums(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute('UPDATE photos SET favorite=1 WHERE id=2')
            conn.commit()
        finally:
            conn.close()
        self.assertFalse(restore_pending_catalog('catalog-test', self.db))
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute('SELECT favorite FROM photos WHERE id=2').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT count(*) FROM albums').fetchone()[0], 1)
        finally:
            conn.close()

    def test_restores_a_missing_database_without_overwriting_settings(self):
        self.db.unlink()
        self.assertTrue(restore_pending_catalog('catalog-test', self.db))
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute('SELECT count(*) FROM albums').fetchone()[0], 1)
        finally:
            conn.close()

    def test_recovers_a_corrupt_database_but_keeps_a_copy_of_the_damaged_file(self):
        self.db.write_bytes(b'not a SQLite database')
        self.assertTrue(restore_pending_catalog('catalog-test', self.db))
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute('SELECT count(*) FROM albums').fetchone()[0], 1)
        finally:
            conn.close()
        archives = list((Path(os.environ['LOCALAPPDATA']) / 'ShiguangGallery' /
                         'update-backups').glob('*/damaged-current-*'))
        self.assertEqual(len(archives), 1)
        self.assertTrue(any(path.read_bytes() == b'not a SQLite database' for path in archives[0].iterdir()))


if __name__ == '__main__':
    unittest.main()
