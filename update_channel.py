"""联网更新通道：读取远程版本清单并比较语义化版本。"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import hashlib
from pathlib import Path


CURRENT_VERSION = '1.0.6'
DISPLAY_VERSION = 'v 1.0.6'
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
        self.install_state = {'state': 'idle', 'message': ''}
        self.install_thread = None

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
        request = urllib.request.Request(self.url, headers={'Accept': 'application/json', 'User-Agent': f'ShiguangGallery/{CURRENT_VERSION}'})
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

    def install_status(self):
        with self.lock:
            return dict(self.install_state)

    def start_install(self, process_id, application_path, close_application,
                      prepare_update=None, cancel_update=None):
        """Download a verified installer, then hand off replacement to a helper process."""
        with self.lock:
            if self.install_state.get('state') in ('checking', 'downloading', 'verifying', 'installing'):
                return {'ok': True, **self.install_state}
            self.install_state = {'state': 'checking', 'message': '正在检查更新信息…'}
            self.install_thread = threading.Thread(
                target=self._install_worker,
                args=(int(process_id), str(application_path), close_application,
                      prepare_update, cancel_update),
                name='ShiguangGalleryUpdater', daemon=True)
            self.install_thread.start()
        return {'ok': True, **self.install_status()}

    def _set_install_state(self, state, message):
        with self.lock:
            self.install_state = {'state': state, 'message': message}

    def _install_worker(self, process_id, application_path, close_application,
                        prepare_update=None, cancel_update=None):
        installer = None
        helper = None
        pending_backup = ''
        handed_off = False
        try:
            result = self.check()
            if not result.get('ok'):
                raise RuntimeError(result.get('error') or '无法获取更新信息。')
            if not result.get('update_available'):
                raise RuntimeError('当前已经是最新版本。')
            latest = result['latest']
            url = latest['download_url']
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != 'https' or not parsed.hostname:
                raise ValueError('自动更新只接受 HTTPS 下载地址。')
            if Path(urllib.parse.unquote(parsed.path)).suffix.lower() != '.exe':
                raise ValueError('更新地址必须直接指向 Windows 安装程序（.exe）。')
            expected_hash = latest['sha256'].strip().lower()
            if not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
                raise ValueError('更新清单缺少有效的 SHA-256，暂不能安全地自动安装。')

            self._set_install_state('downloading', '正在下载更新…')
            request = urllib.request.Request(url, headers={'User-Agent': f'ShiguangGallery/{CURRENT_VERSION}'})
            with urllib.request.urlopen(request, timeout=30) as response:
                length = response.headers.get('Content-Length')
                if length and int(length) > 1024 * 1024 * 1024:
                    raise ValueError('安装包超过 1 GB，已取消下载。')
                name = Path(urllib.parse.unquote(parsed.path)).name or 'ShiguangGallery-Setup.exe'
                if not name.lower().endswith('.exe'):
                    name += '.exe'
                stage = Path(tempfile.mkdtemp(prefix='ShiguangGallery-update-'))
                installer = stage / name
                digest = hashlib.sha256()
                received = 0
                with installer.open('wb') as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > 1024 * 1024 * 1024:
                            raise ValueError('安装包超过 1 GB，已取消下载。')
                        digest.update(block)
                        output.write(block)
                        total = int(length) if length and length.isdigit() else 0
                        message = (f'正在下载更新… {received // (1024 * 1024)} MB' +
                                   (f' / {max(1, total // (1024 * 1024))} MB' if total else ''))
                        self._set_install_state('downloading', message)

            self._set_install_state('verifying', '正在校验安装包…')
            if digest.hexdigest().lower() != expected_hash:
                raise ValueError('安装包 SHA-256 校验失败，未运行该文件。')
            if not getattr(sys, 'frozen', False):
                raise RuntimeError('自动安装仅支持已安装的 Windows 版本。')
            if prepare_update:
                self._set_install_state('verifying', '正在备份照片来源、收藏和相册…')
                pending_backup = str(prepare_update() or '')

            script = r'''param([int]$WaitPid,[string]$InstallerPath,[string]$ApplicationPath,[string]$PendingBackupPath)
$ErrorActionPreference = 'Stop'
$installSucceeded = $false
try {
  while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 300 }
  $run = Start-Process -FilePath $InstallerPath -ArgumentList '/S' -Wait -PassThru
  if ($run.ExitCode -ne 0) { throw "安装程序退出代码：$($run.ExitCode)" }
  $installSucceeded = $true
  if (-not (Test-Path -LiteralPath $ApplicationPath)) { throw '安装完成后未找到应用程序。' }
  Start-Process -FilePath $ApplicationPath
} catch {
  if (-not $installSucceeded -and $PendingBackupPath -and (Test-Path -LiteralPath $PendingBackupPath)) {
    Remove-Item -LiteralPath $PendingBackupPath -Force -ErrorAction SilentlyContinue
  }
  try {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("自动更新未能完成：$($_.Exception.Message)`n旧版本可能仍可从桌面快捷方式启动。", '拾光图库更新', 'OK', 'Warning') | Out-Null
  } catch {}
  if (Test-Path -LiteralPath $ApplicationPath) { Start-Process -FilePath $ApplicationPath -ErrorAction SilentlyContinue }
} finally {
  Start-Sleep -Seconds 2
  $stage = Split-Path -Parent $InstallerPath
  Remove-Item -LiteralPath $InstallerPath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $stage -Force -ErrorAction SilentlyContinue
}'''
            helper = installer.parent / 'install-update.ps1'
            # Windows PowerShell 5.1 needs a BOM to read UTF-8 scripts containing Chinese.
            helper.write_text(script, encoding='utf-8-sig')
            powershell = shutil.which('powershell.exe') or str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe')
            if not Path(powershell).is_file():
                raise RuntimeError('找不到 Windows PowerShell，无法安全替换程序。')
            creation_flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.Popen([
                powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-WindowStyle', 'Hidden', '-File', str(helper),
                '-WaitPid', str(process_id), '-InstallerPath', str(installer),
                '-ApplicationPath', application_path, '-PendingBackupPath', pending_backup,
            ], close_fds=True, creationflags=creation_flags)
            handed_off = True
            installer = None  # The helper owns the staged files now.
            helper = None
            self._set_install_state('installing', f'正在退出旧版本并安装 {latest["display_version"]}…')
            threading.Timer(0.8, close_application).start()
        except Exception as exc:
            if not handed_off and cancel_update:
                try:
                    cancel_update()
                except Exception:
                    pass
            if installer:
                try:
                    shutil.rmtree(installer.parent, ignore_errors=True)
                except OSError:
                    pass
            if helper:
                try:
                    helper.unlink(missing_ok=True)
                except OSError:
                    pass
            self._set_install_state('failed', str(exc))
