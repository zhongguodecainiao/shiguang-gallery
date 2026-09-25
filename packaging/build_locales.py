from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
CODES=['en','ja','ko','fr','de','es','pt','ru']
rows={}
for i,line in enumerate((ROOT/'packaging/i18n-work/translations.tsv').read_text(encoding='utf-8-sig').splitlines(),1):
    if not line.strip():continue
    parts=line.split('|')
    assert len(parts)==9,(i,len(parts),parts[0])
    key,*values=parts;key=key.replace('\\n','\n');values=[v.replace('\\n','\n') for v in values]
    assert key not in rows,key
    rows[key]=values
aliases={
 '暂时无法预览':'无法预览','点击左下角刷新，读取所选文件夹中的照片。':'点击左下角刷新，读取所选照片文件夹。',
 '已选 {0} 张照片':'已选 {0} 张','{0} 张':'{0} 张照片','正在读取你的照片…':'正在读取照片…','收藏照片':'收藏',
 '更早位置的缩略图':'上一组缩略图','更后位置的缩略图':'下一组缩略图',
 '复制后，在聊天输入框按 Ctrl+V 粘贴。RAW 复制浏览预览；动图复制当前首帧。':'复制后，在聊天输入框按 Ctrl+V 粘贴。RAW 复制浏览预览；动图复制首帧。'
}
def lookup(key):
    if key in rows:return rows[key]
    if key in aliases:return lookup(aliases[key])
    trimmed=key.strip()
    if trimmed!=key:
        result=lookup(trimmed)
        if result:return [key[:len(key)-len(key.lstrip())]+v+key[len(key.rstrip()):] for v in result]
    for prefix in ['＋ ','⚙ ','▸ ','▾ ','— ',' · ']:
        if key.startswith(prefix):
            result=lookup(key[len(prefix):])
            if result:return [prefix+v for v in result]
    if key.endswith(' · 测试版'):return [key.removesuffix('测试版')+v for v in lookup('测试版')]
    if key=='已选 0 张':return [v.replace('{0}','0') for v in lookup('已选 {0} 张')]
    if key=='第 {0} 张：{1}{2}{3}':return [v+'{2}{3}' for v in lookup('第 {0} 张：{1}')]
    if key=='文件夹 / ':return [v+' / ' for v in lookup('文件夹')]
    if key=='原文件 · ':return [v+' · ' for v in lookup('原文件')]
    if key=='本机照片 · {0}':return [v+' · {0}' for v in lookup('本机照片')]
    if key.startswith('例如 '):return ['e.g. '+key[3:].replace('照片副本','PhotoCopies').replace('资料库','Photos').replace('照片','Photos') if c=='en' else prefix+key[3:].replace('照片副本','PhotoCopies').replace('资料库','Photos').replace('照片','Photos') for c,prefix in zip(CODES,['e.g. ','例：','예: ','Ex. : ','z. B. ','P. ej., ','Ex.: ','Например: '])]
keys=list(dict.fromkeys(json.loads((ROOT/'packaging/i18n-work/keys.json').read_text(encoding='utf-8'))))
missing=[k for k in keys if not lookup(k)]
(ROOT/'packaging/i18n-work/missing.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2),encoding='utf-8')
for key in keys:
    value=lookup(key)
    if value:rows[key]=value
catalog={code:{key:values[i] for key,values in rows.items()} for i,code in enumerate(CODES)}
(ROOT/'web/locales.js').write_text("'use strict';\nconst GALLERY_LOCALES="+json.dumps(catalog,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
print(json.dumps({'translated_keys':len(rows),'missing':missing},ensure_ascii=False))

