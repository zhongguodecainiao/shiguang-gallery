"""Windows folder selection and recycle-only deletion."""
import pythoncom
from win32com.shell import shell, shellcon
from win32com.server.exception import COMException
from send2trash.win.IFileOperationProgressSink import FileOperationProgressSink


class RecycleOnlySink(FileOperationProgressSink):
    def PreDeleteItem(self, flags, item):
        if not flags & shellcon.TSF_DELETE_RECYCLE_IF_POSSIBLE:
            # COM methods must raise: returning an HRESULT integer is not an error in pywin32.
            raise COMException('拒绝永久删除：此文件无法放入回收站。', scode=-2147467260)

    def PostDeleteItem(self, flags, item, hr_delete, newly_created):
        self.result = hr_delete
        self.recycled = newly_created is not None


def recycle_file(path):
    pythoncom.CoInitialize()
    try:
        sink = RecycleOnlySink()
        sink.result = None
        sink.recycled = False
        wrapped = pythoncom.WrapObject(sink, shell.IID_IFileOperationProgressSink)
        operation = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None,
                                               pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IFileOperation)
        flags = (shellcon.FOF_NOCONFIRMATION | shellcon.FOF_NOERRORUI | shellcon.FOF_SILENT
                 | 0x20000000 | 0x00080000 | 0x00100000)
        operation.SetOperationFlags(flags)
        operation.DeleteItem(shell.SHCreateItemFromParsingName(str(path), None, shell.IID_IShellItem), wrapped)
        operation.PerformOperations()
        if operation.GetAnyOperationsAborted() or sink.result is None or sink.result & 0x80000000 or not sink.recycled:
            raise OSError('未完成放入回收站；请刷新检查。不会尝试永久删除。')
    finally:
        pythoncom.CoUninitialize()


def choose_folder():
    pythoncom.CoInitialize()
    try:
        result = shell.SHBrowseForFolder(0, None, '选择保存照片或分享包的文件夹', 0x40 | 0x01)
        if not result or not result[0]:
            return None
        path = shell.SHGetPathFromIDList(result[0])
        return path.decode('mbcs') if isinstance(path, bytes) else path
    finally:
        pythoncom.CoUninitialize()
