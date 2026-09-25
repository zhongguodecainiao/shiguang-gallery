"""Read recorded sample precision; never infer capture depth from a uint16 buffer."""
from PIL import Image

RAW_EXTENSIONS={'.rw2','.dng','.cr2','.cr3','.nef','.arw','.orf','.raf','.pef','.srw'}


def sample_values(tags,key):
    item=tags.get(key)
    value=getattr(item,'values',item)
    try:
        values=[int(v) for v in value] if isinstance(value,(list,tuple)) else [int(value)]
        return values
    except (TypeError,ValueError,OverflowError):return []


def bit_depth(path,tags):
    suffix=path.suffix.lower()
    bits=[];source='';raw=suffix in RAW_EXTENSIONS
    if suffix=='.rw2':
        # PanasonicRaw IFD0 0x000a, NOT the JPEG preview's BitsPerSample.
        bits=sample_values(tags,'Image Tag 0x000A')
        source='Panasonic RAW BitsPerSample'
    elif raw:
        candidates=[]
        for key in tags:
            if not key.endswith('BitsPerSample'):continue
            prefix=key[:-len('BitsPerSample')]
            photo=sample_values(tags,prefix+'PhotometricInterpretation')
            # CFA and LinearRaw identify the raw IFD; preview IFD0 is often 8 bit.
            if photo in ([32803],[34892]) or prefix+'CFAPattern' in tags:
                values=sample_values(tags,key)
                if values:candidates.append((values,key))
        unique={tuple(v) for v,_ in candidates}
        if len(unique)==1:bits,source=candidates[0]
    else:
        try:
            with Image.open(path) as image:
                if image.format=='PNG':
                    with path.open('rb') as stream:header=stream.read(26)
                    if header[:8]==b'\x89PNG\r\n\x1a\n':
                        bits=[header[24]];source='PNG IHDR'
                        if header[25]==3:
                            return {'bits':header[24],'text':f'{header[24]} bit 索引 · 调色板 RGB 为 8 bit / 通道','source':source}
                elif image.format=='JPEG':bits=[image.bits];source='JPEG SOF'
                elif image.format=='TIFF':
                    value=image.tag_v2.get(258)
                    bits=list(value) if isinstance(value,tuple) else [value];source='TIFF BitsPerSample'
                elif image.format=='WEBP':bits=[8];source='WebP 编码'
                elif image.format=='GIF':
                    return {'bits':None,'text':'索引色 · 调色板 RGB 为 8 bit / 通道','source':'GIF 调色板'}
                elif image.info.get('bit_depth'):
                    bits=[int(image.info['bit_depth'])];source='图像解码器的源文件信息'
        except (OSError,ValueError,AttributeError,TypeError):pass
    if not bits or any(not isinstance(b,int) or not 1<=b<=64 for b in bits):
        return {'bits':None,'text':'未能可靠读取','source':'未使用内嵌预览或解码缓冲区位数推算'}
    unique=sorted(set(bits))
    value=unique[0] if len(unique)==1 else None
    text='/'.join(map(str,unique))+' bit'+(' / RAW 样本' if raw else ' / 通道')
    return {'bits':value,'text':text,'source':source}
