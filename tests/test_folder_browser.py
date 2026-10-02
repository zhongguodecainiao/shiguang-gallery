import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from folder_browser import list_folders


class FolderBrowserTests(unittest.TestCase):
    def test_browse_existing_parent_and_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'保存照片').mkdir();(root/'another').mkdir();(root/'file.txt').write_text('keep')
            with patch('folder_browser.local_drives',return_value=[root.anchor]):
                r=list_folders(str(root))
                self.assertEqual({x['name'] for x in r['folders']},{'保存照片','another'})
                self.assertEqual(r['parent'],str(root.parent))
                self.assertEqual(list_folders()['folders'][0]['path'],root.anchor)
                self.assertEqual(list_folders(str(root/'保存照片'))['folders'],[])
                self.assertEqual(list_folders(str(root/'not-yet'/'nested'),True)['path'],str(root))
                self.assertFalse((root/'not-yet').exists())
                with self.assertRaises(ValueError):list_folders(str(root/'missing'))
                with self.assertRaises(ValueError):list_folders(str(root/'file.txt'))

    def test_nonlocal_and_permission_errors(self):
        for path in ['relative', r'\\server\share']:
            with self.assertRaises(ValueError):list_folders(path)
        with tempfile.TemporaryDirectory() as temp:
            with patch('folder_browser.local_drives',return_value=[Path(temp).anchor]),patch('folder_browser.os.scandir',side_effect=PermissionError):
                with self.assertRaisesRegex(ValueError,'权限'):list_folders(temp)


if __name__=='__main__':unittest.main()
