"""Assemble an allowlisted, data-free release and its exact uninstall manifest."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / 'packaging'
APP = ROOT / 'release-1.0.7' / '拾光图库'
OUT = ROOT / '发布包' / '1.0.7'
RUNTIME = ['app.py', 'ui_preferences.py', 'folder_actions.py', 'app_paths.py', 'photo_sources.py', 'release_notes.py', 'update_channel.py', 'user_data_backup.py', 'update_server.py', 'update-channel.example.json', 'file_actions.py', 'native_ops.py',
           'photo_info.py', 'photo_depth.py', 'photo_clipboard.py', 'photo_filters.py',
           'full_resolution.py', 'folder_browser.py', 'requirements.txt', 'shiguang.ico']
WEB = ['index.html', 'style.css', 'stitch-theme.css', 'beta8.css', 'beta9.css', 'cursor-left.png', 'cursor-right.png', 'material-symbols-outlined.woff2', 'photo-grid-actions.js', 'app.js', 'interactions.js', 'histogram.js', 'release-notes.js', 'viewer-navigation.js', 'brand-icon.png', 'favicon.ico', 'i18n.js', 'locales.js', 'folder-rename.js', 'viewer-layout.js']
BUILD = ['setup.nsi', 'version_info.txt', 'README-发布版.txt',
         'README-源码.txt', 'build_release.ps1', 'assemble_release.py',
         'build_locales.py', 'qa_native_shell.cjs',
         'i18n-work/translations.tsv', 'i18n-work/keys.json']
TESTS = ['test_user_data_backup.py', 'test_storage_drives.py', 'test_photo_sources.py', 'test_folder_browser.py']
PACKAGES = ['Pillow', 'pillow-heif', 'rawpy', 'numpy', 'pywin32',
            'ExifRead', 'Send2Trash', 'pypng', 'pyinstaller', 'pywebview',
            'pythonnet', 'clr-loader', 'bottle', 'proxy-tools', 'cffi', 'pycparser']


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main():
    assert (APP / '拾光图库.exe').is_file(), 'Build the application first.'
    OUT.mkdir(parents=True, exist_ok=True)
    notices = APP / 'THIRD-PARTY-NOTICES'
    versions = {}
    for name in PACKAGES:
        dist = metadata.distribution(name)
        versions[name] = dist.version
        for file in dist.files or []:
            if any(x in str(file).lower() for x in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    copy(source, notices / name / str(file))
    import png
    copy(Path(png.__file__), notices / 'pypng' / 'png.py')
    copy(Path(sys.base_prefix) / 'LICENSE.txt', notices / 'Python' / 'LICENSE.txt')
    nsis_license = PACK / 'tools' / 'nsis-3.12' / 'COPYING'
    if nsis_license.exists():
        copy(nsis_license, notices / 'NSIS' / 'COPYING')
    else:
        copy(PACK / 'licenses' / 'NSIS' / 'COPYING', notices / 'NSIS' / 'COPYING')
    # Preserve full upstream licenses, including files inside source archives.
    for archive in (PACK / 'upstream-source').glob('*.tar.gz'):
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                name = Path(member.name)
                if member.isfile() and name.name.lower().startswith(('copying', 'license')):
                    target = notices / 'upstream' / archive.name / name
                    assert target.resolve().is_relative_to(notices.resolve())
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
    import rawpy, pillow_heif
    versions.update(Python=sys.version.split()[0], LibRaw=list(rawpy.libraw_version),
                    HEIF=pillow_heif.libheif_info(), NSIS='3.12')
    (notices / 'versions.json').write_text(json.dumps(versions, ensure_ascii=False, indent=2), encoding='utf-8')
    copy(PACK / 'upstream-source' / 'GPL-3.0.txt', APP / 'LICENSE.txt')
    copy(PACK / 'licenses' / 'Material-Symbols' / 'LICENSE.txt', notices / 'Material-Symbols' / 'LICENSE.txt')
    copy(PACK / 'README-发布版.txt', APP / '使用说明.txt')
    copy(ROOT / 'shiguang.ico', APP / 'shiguang-brand-v1.ico')
    copy(PACK / 'README-发布版.txt', OUT / '发布说明.txt')
    source_zip = OUT / '拾光图库-1.0.7-源码.zip'
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in RUNTIME:
            z.write(ROOT / file, file)
        for file in WEB:
            z.write(ROOT / 'web' / file, 'web/' + file)
        for file in BUILD:
            z.write(PACK / file, 'packaging/' + file)
        z.write(PACK / 'qa_storage.cjs', 'packaging/qa_storage.cjs')
        for file in TESTS:
            z.write(ROOT / 'tests' / file, 'tests/' + file)
        z.write(ROOT / 'branding' / 'make_beta8_logo.py', 'branding/make_beta8_logo.py')
        z.write(ROOT / 'branding' / 'make_page_cursors.py', 'branding/make_page_cursors.py')
        z.write(ROOT / 'branding' / 'shiguang-logo-master.png', 'branding/shiguang-logo-master.png')
        z.write(PACK / 'tools' / 'MicrosoftEdgeWebview2Setup.exe',
                'packaging/tools/MicrosoftEdgeWebview2Setup.exe')
        z.write(PACK / 'README-源码.txt', 'README.txt')
        z.write(APP / 'LICENSE.txt', 'LICENSE.txt')
        for file in sorted((PACK / 'upstream-source').rglob('*')):
            if file.is_file():
                z.write(file, 'packaging/upstream-source/' + file.relative_to(PACK / 'upstream-source').as_posix())
        for file in sorted(notices.rglob('*')):
            if file.is_file():
                z.write(file, 'packaging/licenses/' + file.relative_to(notices).as_posix())
    copy(source_zip, APP / 'Source' / source_zip.name)
    copy(PACK / 'README-源码.txt', APP / 'Source' / 'README.txt')

    def escaped(path):
        return str(path).replace('$', '$$').replace('"', '$\\"')
    files = sorted(p.relative_to(APP) for p in APP.rglob('*') if p.is_file())
    dirs = sorted((p.relative_to(APP) for p in APP.rglob('*') if p.is_dir()),
                  key=lambda p: len(p.parts), reverse=True)
    lines = ['; Generated: only remove files shipped by this release.']
    lines += ['Delete "$INSTDIR\\' + escaped(p) + '"' for p in files]
    lines += ['RMDir "$INSTDIR\\' + escaped(p) + '"' for p in dirs]
    (PACK / 'uninstall-files.nsh').write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
    print(json.dumps({'files': len(files), 'source_bytes': source_zip.stat().st_size,
                      'source_sha256': hashlib.sha256(source_zip.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
