"""On-demand full-resolution decoding. Never edits the photo source."""
import hashlib
import io
import os
from pathlib import Path
import re
import secrets
import threading

from PIL import Image, ImageOps, ImageCms
import rawpy
import png


class FullResolution:
    CACHE_BYTES = 256 * 1024 * 1024
    VERSION = 'full-raw-v2-ahd-camera-wb-srgb16'

    def __init__(self, gallery):
        self.gallery = gallery
        self.cache = gallery.data/'full-resolution'
        self.lock = threading.Lock()

    def read(self, photo_id):
        row, path = self.gallery.get_photo(photo_id)
        # Browser-native formats can be read byte-for-byte, with no re-encoding.
        native = {'.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.png':'image/png',
                  '.webp':'image/webp', '.gif':'image/gif', '.avif':'image/avif', '.bmp':'image/bmp'}
        if row['kind'] != 'RAW' and path.suffix.lower() in native:
            return path.read_bytes(), native[path.suffix.lower()]
        # Serialize heavyweight RAW processing to bound peak memory across windows.
        with self.lock:
            row, path = self.gallery.get_photo(photo_id)
            before = path.stat()
            key = hashlib.sha256(f'{self.VERSION}:{row["file_key"]}:{before.st_mtime_ns}:{before.st_size}'.encode()).hexdigest()
            self.cache.mkdir(exist_ok=True)
            dest = self.cache/(key+'.png')
            if dest.exists():
                data = dest.read_bytes()
                dest.touch()
                return data, 'image/png'
            image = None
            rgb = None
            if row['kind'] == 'RAW':
                with rawpy.imread(str(path)) as raw:
                    # This path intentionally never calls extract_thumb or half-size processing.
                    rgb = raw.postprocess(half_size=False, use_camera_wb=True,
                                          demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                                          fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
                                          noise_thr=None, median_filter_passes=0,
                                          output_color=rawpy.ColorSpace.sRGB, output_bps=16,
                                          gamma=(2.4,12.92), no_auto_bright=True)
                profile = None
            else:
                with Image.open(path) as src:
                    image = ImageOps.exif_transpose(src)
                    profile = image.info.get('icc_profile')
                    if image.mode == 'CMYK' and profile:
                        image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                                          ImageCms.createProfile('sRGB'), outputMode='RGB')
                        profile = None
                    image = image.convert('RGBA' if image.mode in ('RGBA','LA') or 'transparency' in image.info else 'RGB')
            if image is not None:image.info.clear()
            temp = self.cache/(key+'.'+secrets.token_hex(4)+'.tmp')
            try:
                if rgb is not None:
                    if rgb.dtype.name != 'uint16':raise ValueError('RAW 解码未返回 16 bit 数据')
                    height,width,_ = rgb.shape
                    # Pillow RGB conversion would discard the lower eight bits.
                    with temp.open('wb') as stream:
                        png.Writer(width,height,greyscale=False,bitdepth=16,compression=2).write(stream,rgb.reshape(height,width*3))
                    del rgb
                else:
                    image.save(temp, 'PNG', compress_level=2, icc_profile=profile)
                after = path.stat()
                if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                    raise ValueError('原照片刚刚发生变化，请重新打开。')
                data = temp.read_bytes()
                # Oversized individual images are served without retaining a disk cache.
                if len(data) <= self.CACHE_BYTES:
                    os.replace(temp, dest)
                    self.trim(dest)
                return data, 'image/png'
            finally:
                if image is not None:image.close()
                if temp.exists():temp.unlink()

    def trim(self, keep):
        files = []
        for p in self.cache.iterdir():
            if re.fullmatch(r'[0-9a-f]{64}\.png', p.name) and p.is_file():
                stat = p.stat(); files.append((stat.st_mtime_ns, stat.st_size, p))
        total = sum(size for _, size, _ in files)
        for _, size, p in sorted(files):
            if total <= self.CACHE_BYTES:break
            if p != keep:
                p.unlink(); total -= size
