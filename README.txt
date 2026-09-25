拾光图库 1.0.0beta10 源码与构建说明

本项目的应用代码、界面、图标和安装脚本按 GNU GPL v3 或更新版本
（SPDX: GPL-3.0-or-later）发布，不提供任何担保，完整条款见 LICENSE.txt。
第三方文件保留原作者的版权及各自许可，见 packaging/licenses。
源代码可以修改、重新构建和再分发；随二进制再分发时请保留许可证及对应源码。

构建 Windows x64 版本
1. 将本 ZIP 解压到一个独立的开发目录，不要解压到照片目录。
2. 安装 Python 3.12 x64、NSIS 3.12（https://nsis.sourceforge.io/Download）。
3. PowerShell 中运行：
   .\packaging\build_release.ps1 -Python python -MakeNSIS 'NSIS所在目录\makensis.exe'
   此步骤从 PyPI 安装 requirements.txt 中固定版本的依赖，需要联网。
4. 生成 release-1.0.0beta10 中的独立程序以及“发布包/1.0.0beta10”中的安装包和源码包。
   Python 不需要安装在使用者的电脑上。无需项目作者电脑上的文件或磁盘盘符。
5. 开发调试：python app.py --root 'D:\自己的照片' --data-dir 'D:\图库测试数据'
   --root 仅用于首次初始化；已保存的来源选择优先。
   不传 --root 时从 HKCU\Software\ShiguangGallery\PhotoRoot 读取配置，
   无配置时使用系统“图片”目录。source-settings.json 会保存软件内选择的文件夹或磁盘组合，优先于首次安装的目录设置。每种来源使用独立索引，切换时拒绝旧窗口的跨来源照片操作。

桌面窗口使用 pywebview 的 Windows Forms 后端和 Microsoft Edge WebView2 Runtime。
Windows 11 通常已包含 WebView2；安装脚本会检查 Evergreen Runtime，缺失时运行
packaging/tools/MicrosoftEdgeWebview2Setup.exe 静默安装。该文件是微软官方签名的
Evergreen Bootstrapper。调试时可设置 SHIGUANG_WEBVIEW2_DEBUG_PORT 开启本机调试端口，
正式运行默认不开启。

第三方源码
packaging/upstream-source 包含原始上游源码压缩包、下载地址和 SHA-256。
rawpy 源码包包含 external/LibRaw 及 LibRaw-cmake；原版 LibRaw 为 0.22.1。
pillow-heif 源码包包含 libheif/build_libs.py、Windows 构建配方和构建配置。
实际 Windows 运行组件：libheif 1.23.3、libde265 1.1.1、
x265 4.3+1-e9b8812（完整提交 e9b88125dc21393b3fd8d68e98083bdfb89778a8）。
以上原生组件对应的源码亦在 upstream-source 中，未对其做本地代码修改。
HEIF wheel 的通用许可清单中可能列有其他平台的版本；实际版本见 versions.json。
如需修改或重建这些原生库，按上游源码中的 CMake/README 和 pillow-heif
的 Windows 构建配方使用 MSYS2 UCRT64 / Visual Studio 构建工具重建，
然后安装自己构建的 wheel，再执行 PyInstaller 和 assemble_release.py。
正常重建本应用使用固定版本的官方 wheel，不要求逐个编译原生库。

安装包本身包含 Source/拾光图库-1.0.0beta10-源码.zip 及 THIRD-PARTY-NOTICES。
本源码包只包含应用代码、构建文件、上游组件与许可，没有个人照片、
个人相册数据库、缓存、运行日志或访问令牌。上游库可能附带公开测试样例。
构建产物未做代码签名；不同编译环境不保证二进制逐字节相同。

界面本地化：web/i18n.js 定义语言列表、本地化名称及即时切换。翻译源为 packaging/i18n-work/translations.tsv（每行以 | 分隔：中文原文、英、日、韩、法、德、西、葡、俄），packaging/i18n-work/keys.json 记录所需消息；运行 python packaging/build_locales.py 生成 web/locales.js，标准构建脚本也会自动运行。参数使用 {0}、{1} 等占位符，保留其编号。照片、相册名称及路径作为原始用户内容显示，不加入翻译。

发布更新时：在 release_notes.py 的 CURRENT_RELEASE 中填写新版版本号、简述和分组条目（新增功能、体验优化、问题修复），并同步更新版本资源、界面版本与打包脚本。仅描述实际完成的变更。每个版本按版本号记录已读状态，文件保存在 control/release-notes-seen.json，与照片来源无关；新版本未读时首次打开自动提示。
