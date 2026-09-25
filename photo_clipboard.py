"""Place decoded image pixels on the Windows clipboard, for chat paste."""
import io
import threading
import time

from PIL import Image, ImageOps
import win32clipboard
import win32con
import win32gui

_copy_lock = threading.Lock()


def image_payload(path):
    # Encode everything before clearing the clipboard; a decode failure keeps it intact.
    with Image.open(path) as source:
        oriented = ImageOps.exif_transpose(source)
        transparent = oriented.mode in ('RGBA', 'LA') or 'transparency' in oriented.info
        im = oriented.convert('RGBA' if transparent else 'RGB')
    im.info.clear()
    png = io.BytesIO()
    im.save(png, 'PNG')
    if transparent:
        bitmap = Image.new('RGB', im.size, 'white')
        bitmap.paste(im, mask=im.getchannel('A'))
    else:
        bitmap = im
    bmp = io.BytesIO()
    bitmap.save(bmp, 'BMP')
    # CF_DIB starts with BITMAPINFOHEADER, not the 14-byte BMP file header.
    return png.getvalue(), bmp.getvalue()[14:], im.size


def write_image(png, dib):
    png_format = win32clipboard.RegisterClipboardFormat('PNG')
    # A real owner window avoids OpenClipboard(NULL)/EmptyClipboard ownership issues.
    owner = win32gui.CreateWindowEx(0, 'STATIC', '拾光图库剪贴板', 0,
                                   0, 0, 0, 0, 0, 0, 0, None)
    opened = False
    try:
        for attempt in range(10):
            try:
                win32clipboard.OpenClipboard(owner)
                opened = True
                break
            except Exception:
                if attempt == 9:
                    raise ValueError('剪贴板正被其他程序占用，请稍后再点一次复制。') from None
                time.sleep(0.05)
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(png_format, png)
        win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
    finally:
        if opened:
            win32clipboard.CloseClipboard()
        win32gui.DestroyWindow(owner)


def copy_photo(gallery, photo_id):
    if not _copy_lock.acquire(blocking=False):
        raise ValueError('正在复制图片，请稍候。')
    try:
        row, path = gallery.get_photo(photo_id)
        preview = row['kind'] == 'RAW'
        if preview:
            path = gallery.preview(photo_id, large=True)
        png, dib, size = image_payload(path)
        write_image(png, dib)
        return {'ok': True, 'name': row['name'], 'width': size[0], 'height': size[1],
                'preview': preview}
    finally:
        _copy_lock.release()
