"""Read-only, one-level browsing of local folders for export destinations."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetLogicalDrives.restype = wintypes.DWORD
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                            wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeInformationW.restype = wintypes.BOOL
    kernel.GetDiskFreeSpaceExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
                                         ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
    kernel.GetDiskFreeSpaceExW.restype = wintypes.BOOL
    kernel.SetThreadErrorMode.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    return kernel


def _drive_roots(kernel):
    mask = kernel.GetLogicalDrives()
    return [(f'{chr(65+n)}:\\', kind) for n in range(26) if mask & (1 << n)
            and (kind := kernel.GetDriveTypeW(f'{chr(65+n)}:\\')) in (2, 3)]


def _storage_bus(kernel, root):
    # Zero requested access: read device metadata without opening photos or requiring admin.
    handle = kernel.CreateFileW('\\\\.\\' + root[:2], 0, 3, None, 3, 0, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        return None
    try:
        query = ctypes.create_string_buffer(struct.pack('<III', 0, 0, 0))
        descriptor = ctypes.create_string_buffer(4096)
        returned = wintypes.DWORD()
        if kernel.DeviceIoControl(handle, 0x2D1400, query, 12, descriptor, len(descriptor),
                                  ctypes.byref(returned), None) and returned.value >= 32:
            return struct.unpack_from('<I', descriptor.raw, 28)[0]
    finally:
        kernel.CloseHandle(handle)
    return None


def storage_drives():
    """Mounted local storage; USB disks may report DRIVE_FIXED, unlike SD cards."""
    kernel = _kernel()
    previous = wintypes.DWORD()
    changed = kernel.SetThreadErrorMode(0x8001, ctypes.byref(previous))
    try:
        drives = []
        for root, kind in _drive_roots(kernel):
            label = ctypes.create_unicode_buffer(261)
            ready = bool(kernel.GetVolumeInformationW(root, label, len(label), None, None, None, None, 0))
            bus = _storage_bus(kernel, root) if ready else None
            category = ('sd' if bus in (12, 13) else 'usb' if bus == 7
                        else 'removable' if kind == 2 else 'fixed')
            free, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
            space_ok = ready and kernel.GetDiskFreeSpaceExW(root, ctypes.byref(free), ctypes.byref(total), None)
            drives.append({'path': root, 'label': label.value if ready else '', 'kind': category,
                           'ready': ready, 'bus': bus, 'removable': kind == 2,
                           'total_bytes': total.value if space_ok else None,
                           'free_bytes': free.value if space_ok else None,
                           'default': ready and category == 'fixed' and root[:1].upper() != 'G'})
        return drives
    finally:
        if changed:
            kernel.SetThreadErrorMode(previous.value, None)


def local_drives():
    return [root for root, _ in _drive_roots(_kernel())]


def list_folders(value='', initial=False):
    roots = local_drives()
    raw = str(value or '').strip().strip('"')
    if not raw:
        return {'path': '', 'parent': None, 'roots': roots,
                'folders': [{'name': p, 'path': p} for p in roots], 'notice': ''}
    path = Path(raw)
    if not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ':':
        raise ValueError('请输入本机文件夹的完整路径，例如 E:\\资料库。')
    path = path.resolve()
    if path.anchor.upper() not in [r.upper() for r in roots]:
        raise ValueError('请选择已连接的本机磁盘、SD 卡或外接存储上的文件夹。')
    notice = ''
    if initial:
        while not path.exists() and path.parent != path:
            path = path.parent
            notice = '原路径尚不存在，已显示最近的上级文件夹。'
    if not path.is_dir():
        raise ValueError('文件夹不存在，请检查路径。')
    try:
        folders = []
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    # Avoid system/private folders and directory reparse-point redirects.
                    stat = entry.stat(follow_symlinks=False)
                    if stat.st_file_attributes & (0x2 | 0x4 | 0x400):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        folders.append({'name': entry.name, 'path': str(path/entry.name)})
                except OSError:
                    continue
    except PermissionError:
        raise ValueError('没有权限读取这个文件夹，请选择其他位置。') from None
    except OSError:
        raise ValueError('设备已断开或无法读取，请重新连接后刷新。') from None
    folders.sort(key=lambda r: r['name'].casefold())
    return {'path': str(path), 'parent': str(path.parent) if path.parent != path else '',
            'roots': roots, 'folders': folders, 'notice': notice}
