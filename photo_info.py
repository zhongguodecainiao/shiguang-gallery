"""Read a whitelist of capture metadata without changing the original file."""
import math
import exifread
from PIL import Image, ExifTags
from photo_depth import bit_depth, RAW_EXTENSIONS
import rawpy


def capture_info(path):
    warning = None
    try:
        with path.open('rb') as stream:
            tags = exifread.process_file(stream, details=True, extract_thumbnail=False)
    except Exception:
        tags = {}
        warning = '部分拍摄参数暂时无法读取。'
    # Pillow fallback also covers images whose EXIF container is not understood by ExifRead.
    if not tags:
        try:
            with Image.open(path) as im:
                ex = im.getexif()
                tags = {'Image '+ExifTags.TAGS.get(k,str(k)): v for k,v in ex.items()}
                tags.update({'EXIF '+ExifTags.TAGS.get(k,str(k)):v for k,v in ex.get_ifd(34665).items()})
        except Exception:
            pass

    def value(*names):
        for name in names:
            if name not in tags:
                continue
            v = getattr(tags[name], 'values', tags[name])
            if isinstance(v, (list, tuple)):
                v = v[0] if v else None
            if v is not None:
                return v
        return None

    def text(*names):
        v = value(*names)
        if isinstance(v, bytes):
            v = v.decode('utf-8','replace')
        return str(v).strip('\x00 ')[:200] if v is not None else None

    def number(*names):
        try:
            n = float(value(*names))
            return n if math.isfinite(n) else None
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return None

    make, model = text('Image Make'), text('Image Model')
    if make=='NIKON CORPORATION':make='Nikon'
    camera = model
    if make and model and make.lower() not in model.lower():
        camera = make+' '+model
    if not camera:
        camera = make
    shutter = number('EXIF ExposureTime')
    aperture = number('EXIF FNumber')
    iso = number('EXIF ISOSpeedRatings','EXIF PhotographicSensitivity','EXIF RecommendedExposureIndex')
    focal = number('EXIF FocalLength')
    equivalent = number('EXIF FocalLengthIn35mmFilm')
    ev = number('EXIF ExposureBiasValue')
    wb_code = number('EXIF WhiteBalance')
    wb = {0:'自动',1:'手动'}.get(wb_code)
    if wb is None:
        maker_wb = str(tags.get('MakerNote WhiteBalance', '')).strip()
        wb = {'Auto':'自动','Manual':'手动','Daylight':'日光','Cloudy':'阴天','Shade':'阴影',
              'Tungsten':'钨丝灯','Fluorescent':'荧光灯','Flash':'闪光灯','Custom':'自定义'}.get(maker_wb)
    light = {1:'日光',2:'荧光灯',3:'钨丝灯',4:'闪光灯',9:'晴天',10:'阴天',11:'阴影',
             12:'日光色荧光灯',13:'日光白荧光灯',14:'冷白荧光灯',15:'白色荧光灯',
             17:'标准光源 A',18:'标准光源 B',19:'标准光源 C',20:'D55',21:'D65',22:'D75',23:'D50'}.get(number('EXIF LightSource'))
    temperature = number('MakerNote ColorTemperature','EXIF ColorTemperature')
    shutter_text='未记录'
    if shutter and shutter>0:
        reciprocal=1/shutter
        shutter_text=f'1/{round(reciprocal)} 秒' if shutter<1 and abs(reciprocal-round(reciprocal))<.005*reciprocal else f'{shutter:.4g} 秒'
    fields = [
        ['相机型号',camera or '未记录'],
        ['镜头',text('EXIF LensModel','MakerNote LensModel','Image LensModel') or '未记录'],
        ['快门速度',shutter_text],
        ['光圈',f'f/{aperture:.2f}'.rstrip('0').rstrip('.') if aperture and aperture>0 else '未记录'],
        ['感光度',f'ISO {iso:g}' if iso and iso>0 else '未记录'],
        ['白平衡',wb or '未记录'],
        ['焦距',f'{focal:.2f}'.rstrip('0').rstrip('.')+' mm' if focal and focal>0 else '未记录'],
    ]
    depth=bit_depth(path,tags)
    fields.insert(2,['原文件色深',depth['text']])
    if path.suffix.lower() in RAW_EXTENSIONS:
        fields.append(['RAW 解码器','LibRaw '+'.'.join(map(str,rawpy.libraw_version))+' · AHD'])
    if equivalent and equivalent>0:fields.append(['等效焦距',f'{equivalent:g} mm'])
    if ev is not None:fields.append(['曝光补偿',f'{ev:+.2f} EV' if ev else '0 EV'])
    if light:fields.append(['记录光源',light])
    if temperature and 1000<=temperature<=50000:fields.append(['记录色温',f'{temperature:g} K'])
    mode={1:'M 手动',2:'P 程序自动',3:'A / Av 光圈优先',4:'S / Tv 快门优先',
          5:'创意程序',6:'运动',7:'人像',8:'风景'}.get(number('EXIF ExposureProgram'))
    if mode:fields.append(['曝光程序',mode])
    # RAW IFD0 ImageWidth can describe a tiny embedded preview instead of the photograph.
    width=number('EXIF ExifImageWidth')
    height=number('EXIF ExifImageLength')
    return {'fields':fields,'width':int(width or 0),'height':int(height or 0),'warning':warning,'bit_depth':depth,
            'note':'位深依据：'+depth['source']+'。16 bit 解码输出不代表原片是 16 bit；屏幕最终色深受浏览器、系统和显示器影响。'}
