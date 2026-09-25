"""Local UI preferences, independent of photo catalogs and server port."""
import json
from pathlib import Path
import threading
from photo_sources import write_json
LANGUAGES = ('zh-CN','en','ja','ko','fr','de','es','pt','ru')
class UIPreferences:
    def __init__(self, control):
        self.path=Path(control)/'ui-preferences.json'
        self.lock=threading.Lock()
    def read(self):
        with self.lock:
            try:
                value=json.loads(self.path.read_text(encoding='utf-8'))
                language=value.get('language') if isinstance(value,dict) else None
            except (OSError,ValueError):language=None
            return {'language':language if language in LANGUAGES else 'zh-CN'}
    def save(self,language):
        if language not in LANGUAGES:raise ValueError('不支持此界面语言')
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            write_json(self.path,{'language':language})
        return {'language':language}
