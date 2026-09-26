"""拾光：本机照片与虚拟相册；确认后可复制、导出或回收原照片。"""
from __future__ import annotations
import argparse, contextlib, datetime as dt, hashlib, io, json, logging, mimetypes, os
import secrets, sqlite3, struct, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image, ImageOps
import pillow_heif
import rawpy
from file_actions import FileActions, choose_folder
from photo_info import capture_info
from photo_clipboard import copy_photo
from folder_browser import list_folders
from full_resolution import FullResolution
from app_paths import launch_paths
from photo_sources import SourceManager, source_key, SKIP_DIRECTORIES
from release_notes import ReleaseNotes
from update_channel import UpdateChannel
from ui_preferences import UIPreferences
from folder_actions import rename_folder
from photo_filters import origin_category, capture_facets, append_filter_clauses

pillow_heif.register_heif_opener(decode_threads=1)
RAW = {'.rw2','.dng','.cr2','.cr3','.nef','.arw','.orf','.raf','.pef','.srw'}
EXTENSIONS = RAW | {'.jpg','.jpeg','.png','.heic','.heif','.tif','.tiff','.bmp','.webp','.gif','.avif'}
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'web'

def normalized_date(value):
    if not isinstance(value, str): return None
    value = value.strip('\x00 ')
    try:
        stamp = dt.datetime.strptime(value[:19], '%Y:%m:%d %H:%M:%S')
    except ValueError:
        try: stamp = dt.datetime.fromisoformat(value)
        except ValueError: return None
    return stamp.isoformat()[:19] if 1900 <= stamp.year <= dt.datetime.now().year else None

def raw_date(path):
    with path.open('rb') as f:
        h = f.read(8)
        if len(h) != 8 or h[:2] not in (b'II', b'MM'): return None
        order = '<' if h[:2] == b'II' else '>'
        if struct.unpack(order+'H', h[2:4])[0] not in (42,85): return None
        todo, seen, size = [struct.unpack(order+'I',h[4:])[0]],set(),path.stat().st_size
        while todo and len(seen)<12:
            pos=todo.pop()
            if pos in seen or pos<8 or pos+2>size: continue
            seen.add(pos); f.seek(pos); n=struct.unpack(order+'H',f.read(2))[0]
            if n>2048 or pos+2+n*12>size: continue
            block=f.read(n*12)
            for k in range(n):
                e=block[k*12:k*12+12];tag,kind,count,value=struct.unpack(order+'HHII',e)
                if tag==34665 and kind==4 and count==1: todo.append(value)
                if tag==36867 and kind==2 and 0<count<=128 and value+count<=size:
                    f.seek(value); stamp=normalized_date(f.read(count).decode('ascii','ignore'))
                    if stamp:return stamp
    return None

def metadata(path, stat):
    stamp=None; width=height=0
    try:
        if path.suffix.lower() in RAW: stamp=raw_date(path)
        else:
            with Image.open(path) as im:
                width,height=im.size; ex=im.getexif()
                detail=ex.get_ifd(34665) if 34665 in ex else {}
                stamp=normalized_date(detail.get(36867) or ex.get(36867))
    except Exception: pass
    return stamp or dt.datetime.fromtimestamp(stat.st_mtime).isoformat()[:19], '拍摄日期' if stamp else '修改日期', width,height

class Gallery:
    def __init__(self, root, data, roots=None, mode='folder', exclusions=None):
        self.root=Path(root).resolve();self.data=Path(data).resolve()
        self.roots=[Path(p).resolve() for p in (roots or [root])];self.mode=mode
        self.exclusions=[Path(p).resolve() for p in (exclusions or [])]+[self.data]
        self.catalog_key=source_key(mode,self.roots);self.cancel_scan=threading.Event();self.scan_thread=None
        self.data.mkdir(parents=True,exist_ok=True);self.cache=self.data/'thumbnails';self.cache.mkdir(exist_ok=True)
        self.db=self.data/'gallery.sqlite3';self.lock=threading.Lock();self.thumbs=threading.Semaphore(3)
        self.status={'running':False,'processed':0,'error':None,'last_scan':None,'skipped':0}
        self.filter_status={'running':False,'processed':0,'total':0,'error':None}
        self.last_seen=time.monotonic();self.token=secrets.token_urlsafe(32)
        self.files=FileActions(self)
        self.full_resolution=FullResolution(self)
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY,file_key TEXT UNIQUE,path TEXT NOT NULL,name TEXT NOT NULL,folder TEXT NOT NULL,extension TEXT NOT NULL,kind TEXT NOT NULL,size INTEGER,mtime INTEGER,taken TEXT,date_source TEXT,width INTEGER,height INTEGER,favorite INTEGER DEFAULT 0,active INTEGER DEFAULT 1,scan TEXT);
            CREATE INDEX IF NOT EXISTS photos_sort ON photos(active,taken,id);
            CREATE INDEX IF NOT EXISTS photos_folder ON photos(folder);
            CREATE TABLE IF NOT EXISTS albums(id INTEGER PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS album_photos(album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,photo_id INTEGER REFERENCES photos(id) ON DELETE CASCADE,PRIMARY KEY(album_id,photo_id));
            ''')
            columns={r['name'] for r in c.execute('PRAGMA table_info(photos)')}
            for name,kind in (('origin_category','TEXT'),('camera','TEXT'),('focal','REAL'),('aperture','REAL'),('filter_indexed','INTEGER DEFAULT 0')):
                if name not in columns:c.execute(f'ALTER TABLE photos ADD COLUMN {name} {kind}')
            c.execute("UPDATE photos SET origin_category='' WHERE origin_category IS NULL")
            for row in c.execute("SELECT id,name,folder FROM photos WHERE origin_category='' AND coalesce(filter_indexed,0)=0").fetchall():
                category=origin_category(row['name'],row['folder'])
                if category:c.execute('UPDATE photos SET origin_category=? WHERE id=?',(category,row['id']))
            c.execute('CREATE INDEX IF NOT EXISTS photos_camera ON photos(camera)')
            c.execute('CREATE INDEX IF NOT EXISTS photos_origin ON photos(origin_category)')
    @contextlib.contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:yield c
        finally:c.close()
    def start_scan(self):
        with self.lock:
            if self.status['running'] or self.files.snapshot()['running']:return False
            self.cancel_scan.clear();self.status.update(running=True,processed=0,error=None,skipped=0)
        self.scan_thread=threading.Thread(target=self.scan,daemon=True);self.scan_thread.start();return True
    def stop_scan(self):
        self.cancel_scan.set()
        if self.scan_thread and self.scan_thread.is_alive():self.scan_thread.join(timeout=5)
        return not self.status['running']
    def allowed_path(self,path):
        roots=[self.root] if self.mode=='folder' else self.roots
        return any(path.is_relative_to(root) for root in roots) and not any(path.is_relative_to(p) for p in self.exclusions)
    def walk_sources(self,errors):
        roots=[self.root] if self.mode=='folder' else self.roots
        for root in roots:
            if self.cancel_scan.is_set():return
            if not root.is_dir():
                errors.append(f'磁盘或目录未连接：{root}');continue
            for directory,dirs,files in os.walk(root,followlinks=False,onerror=lambda e:errors.append(str(e))):
                if self.cancel_scan.is_set():return
                keep=[]
                for name in dirs:
                    try:
                        path=Path(directory)/name;attrs=path.lstat().st_file_attributes
                        if attrs&0x400 or name.lower().endswith(('.lrdata','.lrcat-data')) or name=='照片处理program':continue
                        if any(path.resolve().is_relative_to(p) for p in self.exclusions):continue
                        if self.mode=='computer' and (attrs&(0x2|0x4) or name.startswith('.') or name.casefold() in SKIP_DIRECTORIES):continue
                        keep.append(name)
                    except OSError as exc:errors.append(str(exc))
                dirs[:]=keep
                yield root,directory,dirs,files
    def scan(self):
        try:
            scan_id=secrets.token_hex(8);errors=[]
            with self.connect() as c:
                known={r['file_key']:dict(r) for r in c.execute('SELECT * FROM photos')}
                for root,directory,dirs,files in self.walk_sources(errors):
                    for name in files:
                        if self.cancel_scan.is_set():return
                        path=Path(directory)/name
                        if name.startswith('._') or path.suffix.lower() not in EXTENSIONS:continue
                        try:
                            stat=path.lstat()
                            if stat.st_file_attributes&0x400 or not self.allowed_path(path.resolve()):continue
                            if self.mode=='computer' and stat.st_file_attributes&(0x2|0x4):continue
                            key=f'{stat.st_dev}:{stat.st_ino}' if stat.st_ino else str(path)
                            rel=str(path if self.mode=='computer' else path.relative_to(root));old=known.get(key)
                            if old and old['mtime']==stat.st_mtime_ns and old['size']==stat.st_size:
                                stamp,source,w,h=old['taken'],old['date_source'],old['width'],old['height']
                            else:stamp,source,w,h=metadata(path,stat)
                            folder=str(path.parent if self.mode=='computer' else path.parent.relative_to(root));ext=path.suffix.lower()
                            category=origin_category(name,folder)
                            c.execute('''INSERT INTO photos(file_key,path,name,folder,extension,kind,size,mtime,taken,date_source,width,height,active,scan,origin_category,filter_indexed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,0)
                              ON CONFLICT(file_key) DO UPDATE SET path=excluded.path,name=excluded.name,folder=excluded.folder,extension=excluded.extension,kind=excluded.kind,size=excluded.size,mtime=excluded.mtime,taken=excluded.taken,date_source=excluded.date_source,width=excluded.width,height=excluded.height,active=1,scan=excluded.scan,origin_category=excluded.origin_category,filter_indexed=CASE WHEN photos.mtime=excluded.mtime AND photos.size=excluded.size THEN photos.filter_indexed ELSE 0 END''',
                              (key,rel,name,folder,ext,'RAW' if ext in RAW else '图片',stat.st_size,stat.st_mtime_ns,stamp,source,w,h,scan_id,category))
                            self.status['processed']+=1
                            if self.status['processed']%50==0:c.commit()
                        except Exception as exc:
                            self.status['skipped']+=1;errors.append(str(exc));logging.exception('scan file %s',path)
                if self.cancel_scan.is_set():return
                if not errors:c.execute('UPDATE photos SET active=0 WHERE scan IS NULL OR scan<>?',(scan_id,))
                c.commit()
                self.status['error']='有部分文件暂时无法读取，已保留之前的记录。' if errors else None
                self.status['last_scan']=dt.datetime.now().isoformat()[:19]
        except Exception as exc:self.status['error']=str(exc);logging.exception('scan')
        finally:
            self.status['running']=False
            self.start_filter_index()
    def start_filter_index(self):
        with self.lock:
            if self.filter_status['running']:return
            self.filter_status.update(running=True,processed=0,error=None)
        threading.Thread(target=self.index_filter_metadata,daemon=True).start()
    def index_filter_metadata(self):
        try:
            with self.connect() as c:
                rows=c.execute('SELECT id,path,name,folder,mtime FROM photos WHERE active=1 AND coalesce(filter_indexed,0)=0').fetchall()
            self.filter_status['total']=len(rows)
            for row in rows:
                if self.cancel_scan.is_set():break
                try:
                    path=(self.root/row['path']).resolve()
                    if not self.allowed_path(path) or not path.is_file():continue
                    camera,focal,aperture=capture_facets(path)
                    with self.connect() as c:
                        c.execute('UPDATE photos SET camera=?,focal=?,aperture=?,origin_category=?,filter_indexed=1 WHERE id=? AND mtime=?',
                                  (camera,focal,aperture,origin_category(row['name'],row['folder']),row['id'],row['mtime']))
                except Exception as exc:
                    logging.warning('filter metadata %s: %s',row['id'],exc)
                self.filter_status['processed']+=1
        except Exception as exc:
            self.filter_status['error']=str(exc);logging.exception('filter metadata')
        finally:self.filter_status['running']=False
    def filter_options(self):
        with self.connect() as c:
            cameras=[dict(r) for r in c.execute("SELECT camera,count(*) count FROM photos WHERE active=1 AND camera IS NOT NULL AND camera<>'' GROUP BY camera ORDER BY count DESC,camera LIMIT 100")]
            extensions=[dict(r) for r in c.execute('SELECT extension,count(*) count FROM photos WHERE active=1 GROUP BY extension ORDER BY count DESC,extension')]
        return {'cameras':cameras,'extensions':extensions,'index':dict(self.filter_status)}
    def get_photo(self,id_):
        with self.connect() as c:r=c.execute('SELECT * FROM photos WHERE id=? AND active=1',(int(id_),)).fetchone()
        if r is None:raise FileNotFoundError('照片不在当前图库中')
        path=(self.root/r['path']).resolve()
        if not self.allowed_path(path) or path.suffix.lower() not in EXTENSIONS or not path.is_file():raise FileNotFoundError('原照片位置已变化，请刷新图库')
        return dict(r),path
    def preview(self,id_,large=False):
        r,path=self.get_photo(id_);stat=path.stat()
        key=hashlib.sha256(f'{r["file_key"]}:{stat.st_mtime_ns}:{stat.st_size}:{large}'.encode()).hexdigest()
        dest=self.cache/(key+'.jpg')
        if dest.exists():return dest
        with self.thumbs:
            if dest.exists():return dest
            limit=2560 if large else 480
            if path.suffix.lower() in RAW:
                with rawpy.imread(str(path)) as raw:
                    try:
                        thumb=raw.extract_thumb()
                        if thumb.format==rawpy.ThumbFormat.JPEG:im=Image.open(io.BytesIO(thumb.data));im.load();im=ImageOps.exif_transpose(im)
                        else:im=Image.fromarray(thumb.data)
                    except (rawpy.LibRawNoThumbnailError,rawpy.LibRawUnsupportedThumbnailError):
                        im=Image.fromarray(raw.postprocess(half_size=True,use_camera_wb=True,output_bps=8))
            else:
                with Image.open(path) as src:
                    src.draft('RGB',(limit,limit));im=ImageOps.exif_transpose(src);im.thumbnail((limit,limit));im=im.copy()
            im.thumbnail((limit,limit),Image.Resampling.LANCZOS)
            if im.mode in ('RGBA','LA') or 'transparency' in im.info:
                rgba=im.convert('RGBA');bg=Image.new('RGB',rgba.size,'#f4f4f4');bg.paste(rgba,mask=rgba.getchannel('A'));im=bg
            else:im=im.convert('RGB')
            temp=dest.with_name(dest.stem+'.'+secrets.token_hex(4)+'.tmp')
            im.save(temp,'JPEG',quality=90 if large else 80,optimize=True);os.replace(temp,dest)
            return dest
    def overview(self):
        with self.connect() as c:
            count=c.execute('SELECT count(*) FROM photos WHERE active=1').fetchone()[0]
            favorite=c.execute('SELECT count(*) FROM photos WHERE active=1 AND favorite=1').fetchone()[0]
            raw=c.execute("SELECT count(*) FROM photos WHERE active=1 AND kind='RAW'").fetchone()[0]
            albums=[dict(r) for r in c.execute('''SELECT a.*,count(p.id) count,min(p.id) cover FROM albums a LEFT JOIN album_photos ap ON ap.album_id=a.id LEFT JOIN photos p ON p.id=ap.photo_id AND p.active=1 GROUP BY a.id ORDER BY a.created DESC,a.id DESC''')]
            direct=c.execute('SELECT folder,count(*) count,min(id) cover FROM photos WHERE active=1 GROUP BY folder').fetchall()
        groups={}
        for r in direct:
            parts=Path(r['folder']).parts
            name=parts[0] if parts else '.'
            if name not in groups:groups[name]={'name':name,'count':0,'cover':r['cover']}
            groups[name]['count']+=r['count']
        return {'root':str(self.root) if self.mode=='folder' else '本机照片 · '+'、'.join(str(p) for p in self.roots),'mode':self.mode,'roots':[str(p) for p in self.roots],'catalog':self.catalog_key,'count':count,'favorites':favorite,'raw':raw,'albums':albums,'folders':sorted(groups.values(),key=lambda r:r['name'],reverse=True),'status':dict(self.status)}
    def list_photos(self,q):
        where=['p.active=1'];args=[]
        if q.get('favorite')=='1':where.append('p.favorite=1')
        if q.get('kind') in ('RAW','图片'):where.append('p.kind=?');args.append(q['kind'])
        append_filter_clauses(q,where,args,EXTENSIONS)
        if q.get('album'):
            where.append('EXISTS(SELECT 1 FROM album_photos ap WHERE ap.photo_id=p.id AND ap.album_id=?)');args.append(int(q['album']))
        if q.get('folder'):
            folder=q['folder'];prefix=folder.rstrip('\\')+'\\';where.append("(p.folder=? OR substr(p.folder,1,?)=?)");args.extend([folder,len(prefix),prefix])
        if q.get('search'):
            term=q['search']
            where.append('(instr(lower(p.name),lower(?))>0 OR instr(lower(p.folder),lower(?))>0 OR instr(p.taken,?)>0)');args.extend([term]*3)
        order='ASC' if q.get('sort')=='oldest' else 'DESC'
        offset=max(0,int(q.get('offset','0')));limit=min(240,max(1,int(q.get('limit','120'))))
        with self.connect() as c:
            clause=' AND '.join(where)
            total=c.execute('SELECT count(*) FROM photos p WHERE '+clause,args).fetchone()[0]
            rows=[dict(r) for r in c.execute('SELECT p.* FROM photos p WHERE '+clause+f' ORDER BY p.taken {order},p.id {order} LIMIT ? OFFSET ?',args+[limit,offset])]
        for r in rows:r.pop('file_key',None);r.pop('scan',None)
        return {'items':rows,'total':total}
    def mutate(self,route,body):
        if route=='/api/folders/rename':return rename_folder(self,body.get('folder'),body.get('name'))
        if route=='/api/folders/list':return list_folders(body.get('path',''),body.get('initial') is True)
        if route=='/api/clipboard/image':return copy_photo(self,body['id'])
        if route=='/api/files/prepare':return self.files.prepare(body.get('ids',[]))
        if route=='/api/files/start':return self.files.start(body)
        if route=='/api/files/choose-folder':raise ValueError('文件夹浏览已升级，请关闭旧窗口，重新打开桌面的拾光图库。')
        if route=='/api/files/reveal':self.files.reveal();return {'ok':True}
        ids=list(dict.fromkeys(int(x) for x in body.get('ids',[])))
        if len(ids)>10000:raise ValueError('一次最多选择 10000 张照片')
        with self.connect() as c:
            if route=='/api/albums/create':
                name=str(body.get('name','')).strip()
                if not name or len(name)>80:raise ValueError('相册名称需为 1–80 个字符')
                try:id_=c.execute('INSERT INTO albums(name,created) VALUES(?,?)',(name,dt.datetime.now().isoformat())).lastrowid
                except sqlite3.IntegrityError:raise ValueError('已有同名相册')
                return {'id':id_}
            if route=='/api/albums/rename':
                name=str(body.get('name','')).strip()
                if not name or len(name)>80:raise ValueError('相册名称需为 1–80 个字符')
                try:c.execute('UPDATE albums SET name=? WHERE id=?',(name,int(body['album'])))
                except sqlite3.IntegrityError:raise ValueError('已有同名相册')
            elif route=='/api/albums/delete':c.execute('DELETE FROM albums WHERE id=?',(int(body['album']),))
            elif route in ('/api/albums/add','/api/albums/remove'):
                aid=int(body['album'])
                if c.execute('SELECT id FROM albums WHERE id=?',(aid,)).fetchone() is None:raise ValueError('相册不存在')
                for id_ in ids:
                    if route.endswith('/add'):c.execute('INSERT OR IGNORE INTO album_photos SELECT ?,id FROM photos WHERE id=? AND active=1',(aid,id_))
                    else:c.execute('DELETE FROM album_photos WHERE album_id=? AND photo_id=?',(aid,id_))
            elif route=='/api/favorite':
                for id_ in ids:c.execute('UPDATE photos SET favorite=? WHERE id=?',(1 if body.get('value') else 0,id_))
            elif route=='/api/scan':self.start_scan()
            elif route=='/api/reveal':
                _,path=self.get_photo(body['id']);subprocess.Popen(['explorer.exe','/select,',str(path)])
            else:raise ValueError('未知操作')
        return {'ok':True}

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,gallery):self.gallery=gallery;self.updates=ReleaseNotes(gallery.data);self.update_channel=UpdateChannel(gallery.data.parent.parent);self.preferences=UIPreferences(gallery.data);self.native_window=None;super().__init__(address,Handler)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):logging.debug(fmt,*args)
    def reply(self,status,data,ctype='application/json; charset=utf-8',cookie=None,cache=False):
        if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode()
        if isinstance(data,str):data=data.encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','private, max-age=86400' if cache else 'no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def auth(self):
        host=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=host:return False
        names=(f'sg_{self.server.server_port}=', 'sg=')
        return any(secrets.compare_digest(x.strip(),name+self.server.gallery.token) for x in self.headers.get('Cookie','').split(';') for name in names)
    def do_GET(self):
        url=urllib.parse.urlsplit(self.path);q=dict(urllib.parse.parse_qsl(url.query));g=self.server.gallery
        if url.path=='/' and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and secrets.compare_digest(q.get('token',''),g.token):
            return self.reply(200,(ASSETS/'index.html').read_bytes(),'text/html; charset=utf-8',cookie=f'sg_{self.server.server_port}={g.token}; HttpOnly; SameSite=Strict; Path=/')
        if not self.auth():return self.reply(403,{'error':'请通过拾光图库启动程序打开。'})
        try:
            if url.path=='/':return self.reply(200,(ASSETS/'index.html').read_bytes(),'text/html; charset=utf-8')
            if url.path in ('/brand-icon.png','/favicon.ico','/cursor-left.png','/cursor-right.png'):
                return self.reply(200,(ASSETS/url.path[1:]).read_bytes(),'image/png' if url.path.endswith('.png') else 'image/x-icon')
            if url.path=='/material-symbols-outlined.woff2':
                return self.reply(200,(ASSETS/url.path[1:]).read_bytes(),'font/woff2',cache=True)
            if url.path in ('/style.css','/stitch-theme.css','/beta8.css','/beta9.css','/app.js','/histogram.js','/interactions.js','/release-notes.js','/viewer-navigation.js','/i18n.js','/locales.js','/viewer-layout.js','/folder-rename.js','/photo-grid-actions.js'):
                return self.reply(200,(ASSETS/url.path[1:]).read_bytes(),'text/css; charset=utf-8' if url.path.endswith('.css') else 'text/javascript; charset=utf-8')
            if url.path=='/api/overview':g.last_seen=time.monotonic();return self.reply(200,g.overview())
            if url.path=='/api/source':return self.reply(200,self.server.sources.describe())
            if url.path=='/api/preferences':return self.reply(200,self.server.preferences.read())
            if url.path=='/api/updates':return self.reply(200,self.server.updates.describe())
            if url.path=='/api/update-check':return self.reply(200,self.server.update_channel.check())
            if url.path=='/api/update-status':return self.reply(200,self.server.update_channel.install_status())
            if url.path=='/api/window/activate':
                window=self.server.native_window
                if window is None:raise RuntimeError('窗口尚未准备完成')
                window.show();window.restore()
                return self.reply(200,{'ok':True})
            if hasattr(self.server,'sources') and url.path.startswith('/api/') and url.path!='/api/ping' and self.headers.get('X-Gallery-Catalog')!=g.catalog_key:
                return self.reply(409,{'error':'照片来源已改变，请刷新窗口后重试。'})
            if url.path=='/api/photos':return self.reply(200,g.list_photos(q))
            if url.path=='/api/filters':return self.reply(200,g.filter_options())
            if url.path=='/api/photo-info':
                _,photo=g.get_photo(q['id']);return self.reply(200,capture_info(photo))
            if url.path=='/api/files/job':g.last_seen=time.monotonic();return self.reply(200,g.files.snapshot())
            if url.path=='/api/ping':g.last_seen=time.monotonic();return self.reply(200,{'ok':True})
            if url.path.startswith('/image/'):
                if hasattr(self.server,'sources') and (len(url.path.split('/'))!=4 or url.path.split('/')[2]!=g.catalog_key):
                    return self.reply(409,{'error':'照片来源已改变，请刷新窗口。'})
                try:
                    id_=int(url.path.rsplit('/',1)[1])
                    if q.get('size')=='full':
                        data,ctype=g.full_resolution.read(id_)
                        return self.reply(200,data,ctype,cache=True)
                    preview=g.preview(id_,q.get('size')=='large')
                    return self.reply(200,preview.read_bytes(),'image/jpeg',cache=True)
                except Exception as exc:
                    logging.info('preview %s: %s',url.path,exc)
                    return self.reply(422,{'error':'此照片暂时无法生成预览，原文件未改动。'})
            return self.reply(404,{'error':'不存在'})
        except Exception as exc:logging.exception('GET');return self.reply(400,{'error':str(exc)})
    def do_POST(self):
        origin=f'http://127.0.0.1:{self.server.server_port}'
        if not self.auth() or self.headers.get('Origin')!=origin or self.headers.get('X-Gallery-Request')!='1':return self.reply(403,{'error':'请求来源无效'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>262144:raise ValueError('请求过大')
            body=json.loads(self.rfile.read(size))
            if self.path=='/api/preferences':return self.reply(200,self.server.preferences.save(body.get('language')))
            if self.path=='/api/updates/seen':return self.reply(200,self.server.updates.acknowledge(body.get('version')))
            if self.path=='/api/update-install':
                window=self.server.native_window
                if window is None:raise RuntimeError('自动更新需要在桌面应用窗口中运行。')
                def close_application():
                    try:window.destroy()
                    except Exception:os._exit(0)
                return self.reply(202,self.server.update_channel.start_install(
                    os.getpid(),sys.executable,close_application))
            manager=getattr(self.server,'sources',None)
            with manager.lock if manager else contextlib.nullcontext():
                if manager and self.headers.get('X-Gallery-Catalog')!=self.server.gallery.catalog_key:
                    return self.reply(409,{'error':'照片来源已改变，请刷新窗口后重新选择照片。'})
                if self.path=='/api/source/apply' and manager:
                    return self.reply(200,manager.apply(self.server,body))
                self.reply(200,self.server.gallery.mutate(self.path,body))
        except Exception as exc:logging.exception('POST');self.reply(400,{'error':str(exc)})

def dark_native_titlebar(window):
    """Keep the Win32 frame aligned with the gallery palette on light desktops."""
    try:
        import ctypes
        handle=window.native.Handle.ToInt64()
        dwm=ctypes.WinDLL('dwmapi')
        for attribute,value in ((20,1),(35,0x00100e0e),(36,0x00dee7ee),(34,0x00333130)):
            setting=ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(handle,attribute,ctypes.byref(setting),ctypes.sizeof(setting))
    except Exception:logging.exception('native title bar')

class NativeWindowAPI:
    def __init__(self):self._window=None;self._fullscreen=False
    def enter_fullscreen(self):
        if self._window is not None and not self._fullscreen:
            self._window.toggle_fullscreen();self._fullscreen=True
        return True
    def exit_fullscreen(self):
        if self._window is not None and self._fullscreen:
            self._window.toggle_fullscreen();self._fullscreen=False
        return True

def open_window(url, control, server=None):
    """Run the gallery in its own WebView2 window instead of an Edge app window."""
    import webview
    debug_port=os.environ.get('SHIGUANG_WEBVIEW2_DEBUG_PORT')
    if debug_port: webview.settings['REMOTE_DEBUGGING_PORT']=int(debug_port)
    storage=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'ShiguangGallery'/'webview2'
    storage.mkdir(parents=True,exist_ok=True)
    native_api=NativeWindowAPI()
    window=webview.create_window('拾光图库 · v 1.0.2',url,width=1440,height=940,
                                 min_size=(760,600),background_color='#0e0e10',
                                 text_select=True,zoomable=False,js_api=native_api)
    native_api._window=window
    if server is not None:server.native_window=window
    window.events.shown += lambda: dark_native_titlebar(window)
    icon_path=(Path(sys.executable).parent/'shiguang-brand-v1.ico' if getattr(sys,'frozen',False)
               else Path(__file__).parent/'shiguang.ico')
    webview.start(gui='edgechromium',private_mode=False,storage_path=str(storage),
                  icon=str(icon_path))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--data-dir');parser.add_argument('--root');args=parser.parse_args()
    legacy=Path(sys.executable).parent/'data' if getattr(sys,'frozen',False) else None
    if not args.data_dir and legacy and (legacy/'source-settings.json').is_file():args.data_dir=str(legacy)
    root,data,export=launch_paths(args.root,args.data_dir)
    control=Path(args.data_dir).resolve() if args.data_dir else data.parent.parent
    control.mkdir(parents=True,exist_ok=True)
    data.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=data/'gallery.log',level=logging.INFO,format='%(asctime)s %(message)s')
    info=control/'running.json'
    saved={}
    if info.exists():
        try:
            saved=json.loads(info.read_text());address=urllib.parse.urlsplit(saved['origin'])
            if address.scheme!='http' or address.hostname!='127.0.0.1' or not address.port:raise ValueError('无效的本机服务地址')
            req=urllib.request.Request(saved['origin']+'/api/ping',headers={'Cookie':f'sg_{address.port}='+saved['token']})
            with urllib.request.urlopen(req,timeout=1) as response:
                if response.status==200:
                    if not args.no_browser:
                        activate=urllib.request.Request(saved['origin']+'/api/window/activate',headers={'Cookie':f'sg_{address.port}='+saved['token']})
                        try:
                            with urllib.request.urlopen(activate,timeout=2):pass
                        except (urllib.error.HTTPError, urllib.error.URLError):open_window(saved['url'],control)
                    return
        except Exception:pass
    manager=SourceManager(Gallery,control,root,export,legacy_data=data if args.data_dir else None)
    gallery=manager.gallery;server=bind_local_server(gallery,saved);server.sources=manager
    server.updates=ReleaseNotes(control)
    server.preferences=UIPreferences(control)
    origin=f'http://127.0.0.1:{server.server_port}';url=origin+'/?token='+gallery.token
    info.write_text(json.dumps({'origin':origin,'token':gallery.token,'url':url,'pid':os.getpid()}),encoding='utf-8')
    gallery.start_scan()
    def idle():
        while True:
            time.sleep(30)
            active=server.gallery
            if not args.no_browser and time.monotonic()-active.last_seen>240 and not active.status['running'] and not active.files.snapshot()['running']:
                server.shutdown();break
    if args.no_browser:threading.Thread(target=idle,daemon=True).start()
    try:
        if args.no_browser:server.serve_forever(poll_interval=.5)
        else:
            server_thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.5},daemon=True)
            server_thread.start()
            open_window(url,control,server)
            server.shutdown()
            server_thread.join()
    finally:
        server.server_close()
        # Keep the local address for the next launch, so existing windows can reconnect.

def bind_local_server(gallery,saved):
    try:
        address=urllib.parse.urlsplit(saved.get('origin',''))
        token=saved.get('token','')
        if address.scheme=='http' and address.hostname=='127.0.0.1' and address.port and 32<=len(token)<=128 and all(c.isascii() and (c.isalnum() or c in '_-') for c in token):
            server=Server(('127.0.0.1',address.port),gallery)
            gallery.token=token
            return server
    except (ValueError,TypeError,OSError):pass
    return Server(('127.0.0.1',0),gallery)

if __name__=='__main__':main()
