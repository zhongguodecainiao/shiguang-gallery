import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from types import SimpleNamespace
from PIL import Image
from app import Gallery, Server
from photo_sources import SourceManager, source_key


class SourceTests(unittest.TestCase):
    def setUp(self):
        # Keep metadata indexing deterministic; background SQLite writers can outlive cleanup.
        indexing = patch.object(Gallery, 'start_filter_index', Gallery.index_filter_metadata)
        indexing.start(); self.addCleanup(indexing.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(self.base/'local-app-data')})
        environment.start(); self.addCleanup(environment.stop)
        self.a, self.b = self.base/'photos-a', self.base/'photos-b'
        for root, color in [(self.a, 'red'), (self.b, 'blue')]:
            root.mkdir(); Image.new('RGB', (32, 24), color).save(root/'photo.jpg')
        self.manager = SourceManager(Gallery, self.base/'host', self.a, self.base/'exports',
                                     legacy_data=self.base/'host', app_dir=self.base/'program')
        self.g = self.manager.gallery
        self.g.scan()
        self.server = SimpleNamespace(gallery=self.g)

    def tearDown(self):
        self.manager.gallery.stop_scan()
        self.temp.cleanup()

    def switch(self, root):
        result = self.manager.apply(self.server, {'mode': 'folder', 'roots': [str(root)]})
        thread = self.manager.gallery.scan_thread
        if thread: thread.join(timeout=10)
        return result

    def test_roundtrip_keeps_albums_and_originals_and_survives_restart(self):
        hashes = [hashlib.sha256((p/'photo.jpg').read_bytes()).hexdigest() for p in [self.a,self.b]]
        aid = self.g.mutate('/api/albums/create', {'name':'原相册'})['id']
        self.g.mutate('/api/albums/add', {'album':aid, 'ids':[1]})
        self.g.mutate('/api/favorite', {'ids':[1], 'value':True})
        self.switch(self.b)
        self.assertEqual(self.manager.gallery.overview()['albums'], [])
        reopened = SourceManager(Gallery, self.base/'host', self.a, self.base/'exports', app_dir=self.base/'program')
        self.assertEqual(reopened.gallery.root, self.b)
        self.switch(self.a)
        self.assertEqual(self.manager.gallery.overview()['albums'][0]['count'], 1)
        self.assertEqual(self.manager.gallery.overview()['favorites'], 1)
        self.assertEqual(self.manager.gallery.data, self.base/'host')
        self.assertEqual(hashes, [hashlib.sha256((p/'photo.jpg').read_bytes()).hexdigest() for p in [self.a,self.b]])

    def test_invalid_or_missing_selection_does_not_change_current_source(self):
        for body in [{'mode':'computer','roots':[]}, {'mode':'folder','roots':[]},
                     {'mode':'computer','roots':[str(self.a)]},
                     {'mode':'folder','roots':[str(self.base/'absent')]},
                     {'mode':'folder','roots':[str(self.manager.control)]}]:
            with self.assertRaises(ValueError): self.manager.apply(self.server, body)
            self.assertIs(self.server.gallery, self.g)

    def test_running_file_job_blocks_switch(self):
        self.g.files.job['running'] = True
        try:
            with self.assertRaises(ValueError): self.switch(self.b)
            self.assertIs(self.manager.gallery, self.g)
        finally:self.g.files.job['running'] = False

    def test_multi_root_scan_excludes_system_and_data_and_keeps_offline_records(self):
        for root in [self.a, self.b]:
            for name in ['Windows', 'AppData', '$Recycle.Bin', 'node_modules', 'test.lrdata']:
                folder=root/name;folder.mkdir();Image.new('RGB',(5,5)).save(folder/'junk.png')
        cache=self.a/'cache-data';cache.mkdir();Image.new('RGB',(5,5)).save(cache/'ignore.png')
        g=Gallery(self.a,self.base/'multi',roots=[self.a,self.b],mode='computer',exclusions=[cache])
        g.scan();rows=g.list_photos({})['items']
        self.assertEqual(len(rows),2)
        self.assertEqual({g.get_photo(r['id'])[1] for r in rows},{self.a/'photo.jpg',self.b/'photo.jpg'})
        self.assertEqual(g.list_photos({'folder':str(self.a)})['total'],1)
        self.assertEqual(g.list_photos({'folder':self.a.anchor})['total'],2)
        g.roots=[self.a,self.base/'offline'];g.scan()
        self.assertEqual(g.overview()['count'],2);self.assertIsNotNone(g.status['error'])
        g.cancel_scan.set();g.scan();self.assertEqual(g.overview()['count'],2)

    def test_computer_selection_order_has_stable_isolated_catalog(self):
        self.assertEqual(source_key('computer',[self.a,self.b]),source_key('computer',[self.b,self.a]))
        self.assertNotEqual(source_key('computer',[self.a]),source_key('folder',[self.a]))
        with patch('photo_sources.storage_drives',return_value=[{'path': p, 'default': p[0] != 'G'} for p in ['C:\\','D:\\','G:\\']]):
            defaults={d['path']:d['default'] for d in self.manager.describe()['drives']}
        self.assertTrue(defaults['C:\\']);self.assertFalse(defaults['G:\\'])

    def test_removable_source_can_be_browsed_and_disconnection_is_atomic(self):
        with patch('folder_browser._drive_roots', return_value=[(self.b.anchor, 2)]):
            self.switch(self.b)
        current = self.manager.gallery
        with patch('folder_browser._drive_roots', return_value=[]):
            with self.assertRaisesRegex(ValueError, '已连接'):
                self.switch(self.a)
        self.assertIs(self.manager.gallery, current)
        self.assertEqual(current.overview()['count'], 1)

    def test_computer_mode_persists_without_starting_unrequested_scans(self):
        with patch.object(Gallery,'start_scan',return_value=True) as start:
            self.manager.apply(self.server,{'mode':'computer','roots':[self.a.anchor]})
            self.assertEqual(start.call_count,1)
            reopened=SourceManager(Gallery,self.base/'host',self.a,self.base/'exports',app_dir=self.base/'program')
            self.assertEqual(reopened.gallery.mode,'computer')
            self.assertEqual(reopened.state['roots'],[self.a.anchor])
            self.assertEqual(start.call_count,1)
        self.switch(self.a)
        self.assertEqual(self.manager.gallery.data,self.base/'host')

    def test_stale_window_cannot_operate_on_same_id_in_new_source(self):
        server=Server(('127.0.0.1',0),self.g);server.sources=self.manager
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{server.server_port}';token=self.g.token
        def request(route, catalog, body=None):
            headers={'Cookie':f'sg_{server.server_port}='+token,'X-Gallery-Catalog':catalog,
                     'Origin':origin,'X-Gallery-Request':'1','Content-Type':'application/json'}
            req=urllib.request.Request(origin+route,headers=headers,data=None if body is None else json.dumps(body).encode())
            with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
        oldkey=self.g.catalog_key
        try:
            prepared=request('/api/files/prepare',oldkey,{'ids':[1]})
            switched=request('/api/source/apply',oldkey,{'mode':'folder','roots':[str(self.b)]})
            self.manager.gallery.scan_thread.join(timeout=5)
            self.assertEqual(self.manager.gallery.list_photos({})['items'][0]['id'],1)
            for route,body in [('/api/favorite',{'ids':[1],'value':True}),
                               ('/api/files/start',{'token':prepared['token'],'mode':'recycle','confirm_recycle':True}),
                               ('/api/photos',None),('/image/'+oldkey+'/1',None)]:
                with self.assertRaises(urllib.error.HTTPError) as caught:request(route,oldkey,body)
                self.assertEqual(caught.exception.code,409)
            self.assertEqual(request('/api/photos',switched['catalog'])['total'],1)
            self.assertEqual(self.manager.gallery.overview()['favorites'],0)
            self.assertTrue((self.a/'photo.jpg').exists());self.assertTrue((self.b/'photo.jpg').exists())
        finally:server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':unittest.main()
