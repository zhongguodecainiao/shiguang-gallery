"""联网更新通道：读取远程版本清单并比较语义化版本。"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CURRENT_VERSION = '1.0.1'
DISPLAY_VERSION = 'v 1.0.1'
DEFAULT_UPDATE_URL = 'https://raw.githubusercontent.com/zhongguodecainiao/shiguang-gallery-updates/main/update-channel.json'
_VERSION_RE = re.compile(r'^\s*[vV]?\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?(beta|alpha|rc)(\d+)?)?\s*$')


def version_key(value: str):
    """Return a comparable key; stable releases sort after prereleases."""
    match = _VERSION_RE.match(str(value or ''))
    if not match:
        raise ValueError(f'无效的版本号：{value}')
    major, minor, patch, stage, number = match.groups()
    stage_rank = {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage]
    return (int(major), int(minor or 0), int(patch or 0), stage_rank, int(number or 0))


class UpdateChannel:
    def __init__(self, control, url=None):
        self.control = Path(control)
        self.config_path = self.control / 'update-channel.json'
        self.url = self._read_url(url)
        self.lock = threading.Lock()
        self.last_result = None

    def _read_url(self, override=None):
        if override:
            return str(override).strip()
        env_url = os.environ.get('SHIGUANG_UPDATE_URL', '').strip()
        if env_url:
            return env_url
        try:
            saved = json.loads(self.config_path.read_text(encoding='utf-8'))
            if isinstance(saved, dict) and saved.get('url'):
                return str(saved['url']).strip()
        except (OSError, ValueError, TypeError):
            pass
        return DEFAULT_UPDATE_URL

    def _validate(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('更新清单不是 JSON 对象')
        if payload.get('app') not in (None, '拾光图库', 'Shiguang Gallery'):
            raise ValueError('更新清单不是拾光图库的清单')
        version = str(payload.get('version', '')).strip()
        version_key(version)
        download_url = str(payload.get('download_url', '')).strip()
        if download_url and urllib.parse.urlparse(download_url).scheme not in ('http', 'https'):
            raise ValueError('下载地址必须使用 HTTP 或 HTTPS')
        return {
            'app': '拾光图库',
            'version': version,
            'display_version': str(payload.get('display_version') or f'v {version}'),
            'published_at': str(payload.get('published_at') or ''),
            'summary': str(payload.get('summary') or '有新的拾光图库版本可用。'),
            'download_url': download_url,
            'sha256': str(payload.get('sha256') or ''),
            'mandatory': bool(payload.get('mandatory', False)),
        }

    def check(self):
        request = urllib.request.Request(self.url, headers={'Accept': 'application/json', 'User-Agent': 'ShiguangGallery/1.0.1'})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read(1024 * 1024).decode('utf-8'))
            latest = self._validate(payload)
            result = {
                'ok': True,
                'current_version': CURRENT_VERSION,
                'current_display_version': DISPLAY_VERSION,
                'channel_url': self.url,
                'latest': latest,
                'update_available': version_key(latest['version']) > version_key(CURRENT_VERSION),
                'checked_at': dt.datetime.now().isoformat(timespec='seconds'),
            }
        except (OSError, urllib.error.URLError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            result = {
                'ok': False,
                'current_version': CURRENT_VERSION,
                'current_display_version': DISPLAY_VERSION,
                'channel_url': self.url,
                'error': f'暂时无法连接更新服务器：{exc}',
                'checked_at': dt.datetime.now().isoformat(timespec='seconds'),
            }
        with self.lock:
            self.last_result = result
        return result

    def describe(self):
        with self.lock:
            return dict(self.last_result) if self.last_result else {
                'ok': False,
                'current_version': CURRENT_VERSION,
                'current_display_version': DISPLAY_VERSION,
                'channel_url': self.url,
                'checked_at': None,
            }
