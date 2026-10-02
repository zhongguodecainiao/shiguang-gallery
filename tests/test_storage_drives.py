"""Storage detection contracts: Windows removable and fixed USB disks, empty readers."""
import ctypes
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from folder_browser import local_drives, storage_drives, list_folders, _storage_bus


class StorageTests(unittest.TestCase):
    def kernel(self):
        k = Mock()
        kinds = {'C:\\': 3, 'D:\\': 3, 'E:\\': 2, 'F:\\': 2, 'G:\\': 2, 'H:\\': 4, 'I:\\': 5}
        k.GetLogicalDrives.return_value = sum(1 << (ord(p[0])-65) for p in kinds)
        k.GetDriveTypeW.side_effect = kinds.__getitem__
        def volume(root, label, *unused):
            if root == 'G:\\': return 0
            label.value = '照片卡' if root == 'E:\\' else 'Test volume'
            return 1
        def space(root, free, total, unused):
            free._obj.value, total._obj.value = 20 * 1024**3, 64 * 1024**3
            return 1
        def error_mode(mode, previous):
            if previous is not None: previous._obj.value = 0x10
            return 1
        k.GetVolumeInformationW.side_effect = volume
        k.GetDiskFreeSpaceExW.side_effect = space
        k.SetThreadErrorMode.side_effect = error_mode
        return k

    def test_cards_and_fixed_usb_disks_are_listed_without_network_or_optical_drives(self):
        k = self.kernel()
        buses = {'C:\\': 17, 'D:\\': 7, 'E:\\': 12, 'F:\\': None}
        with patch('folder_browser._kernel', return_value=k), patch('folder_browser._storage_bus', side_effect=lambda k, p: buses[p]):
            drives = {d['path']: d for d in storage_drives()}
            self.assertEqual(local_drives(), ['C:\\','D:\\','E:\\','F:\\','G:\\'])
        self.assertEqual([d['kind'] for d in drives.values()], ['fixed','usb','sd','removable','removable'])
        self.assertTrue(drives['C:\\']['default'])
        self.assertFalse(any(d['default'] for p, d in drives.items() if p != 'C:\\'))
        self.assertEqual(drives['E:\\']['label'], '照片卡')
        self.assertEqual(drives['E:\\']['total_bytes'], 64 * 1024**3)
        self.assertFalse(drives['G:\\']['ready'])
        self.assertIsNone(drives['G:\\']['total_bytes'])
        self.assertEqual(k.SetThreadErrorMode.call_args.args, (0x10, None))

    def test_bus_descriptor_retains_64_bit_handle_and_closes_it(self):
        k = Mock()
        k.CreateFileW.return_value = 0x123456789
        def ioctl(handle, code, query, size, output, capacity, returned, unused):
            ctypes.memmove(output, struct.pack('<IIIIIIII', 36,36,0,0,0,0,0,7), 32)
            returned._obj.value = 32
            return 1
        k.DeviceIoControl.side_effect = ioctl
        self.assertEqual(_storage_bus(k, 'D:\\'), 7)
        self.assertEqual(k.DeviceIoControl.call_args.args[0], 0x123456789)
        self.assertEqual(k.CreateFileW.call_args.args[1], 0)
        k.CloseHandle.assert_called_once_with(0x123456789)

    def test_failed_and_short_descriptors_fall_back_without_guessing(self):
        for returned_size, success in [(0, 0), (12, 1)]:
            k = Mock(); k.CreateFileW.return_value = 50
            def ioctl(*args):
                args[6]._obj.value = returned_size
                return success
            k.DeviceIoControl.side_effect = ioctl
            self.assertIsNone(_storage_bus(k, 'E:\\'))
            k.CloseHandle.assert_called_once_with(50)
        k = Mock(); k.CreateFileW.return_value = ctypes.c_void_p(-1).value
        self.assertIsNone(_storage_bus(k, 'E:\\'))
        k.CloseHandle.assert_not_called()

    def test_thread_error_mode_is_restored_after_detection_failure(self):
        k = self.kernel(); k.GetVolumeInformationW.side_effect = OSError('disconnected')
        with patch('folder_browser._kernel', return_value=k):
            with self.assertRaises(OSError): storage_drives()
        self.assertEqual(k.SetThreadErrorMode.call_args.args, (0x10, None))

    def test_removable_folders_are_browsable_and_unplug_errors_are_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'DCIM').mkdir()
            with patch('folder_browser._drive_roots', return_value=[(root.anchor, 2)]):
                self.assertEqual(list_folders(temp)['folders'][0]['name'], 'DCIM')
                with patch('folder_browser.os.scandir', side_effect=OSError('removed')):
                    with self.assertRaisesRegex(ValueError, '设备已断开'): list_folders(temp)


if __name__ == '__main__': unittest.main()
