"""Bundled release notes and a local, source-independent read receipt."""
import json
from pathlib import Path
import threading
from photo_sources import write_json

CURRENT_RELEASE = {
    'version': '1.0.4',
    'summary': '修复应用内更新下载后无法启动安装的问题。',
    'sections': [
        {'title': '应用内更新', 'items': [
            '修复 Windows PowerShell 5.1 读取更新安装脚本时的中文编码问题。',
            '下载并校验安装包后，后台安装流程可继续运行并重新启动图库。',
        ]},
    ],
}
PREVIOUS_RELEASE_1_0_3 = {
    'version': '1.0.3',
    'summary': '版本显示与更新按钮视觉统一。',
    'sections': [
        {'title': '版本与更新入口', 'items': [
            '窗口标题和顶部版本标识统一显示当前应用版本。',
            '检查更新按钮改为与深色界面适配的金色底、深色图标和文字。',
            '保留应用内检查、下载、校验并安装新版本的流程。',
        ]},
    ],
}
PREVIOUS_RELEASE_1_0_1 = {
    'version': '1.0.1',
    'summary': '支持联网检查更新，也可以连接你自己的更新服务器。',
    'sections': [
        {'title': '更新通道', 'items': [
            '可通过互联网连接更新服务器，检查是否有新版本。',
            '支持把自己的电脑作为更新服务器，提供版本清单和安装包。',
            '更新检查失败时不会影响本地照片浏览和相册数据。',
        ]},
        {'title': '独立桌面应用', 'items': [
            '使用应用内嵌的 Microsoft WebView2 显示图库，不再启动 Edge 或 Chrome 浏览器窗口。',
            '深色原生标题栏、任务栏图标和窗口按钮由拾光图库自身管理。',
            '再次启动拾光图库会唤回已有窗口，不会重复打开多个浏览器窗口。',
        ]},
        {'title': '兼容与迁移', 'items': [
            '大图全屏现在控制整个原生窗口，Esc 退出、缩略图和时间进度条等操作保持不变。',
            '继续使用原来的照片索引、相册、收藏和语言设置，无需重新导入照片。',
        ]},
    ],
}
PREVIOUS_BETA10 = {
    'version': '1.0.0beta10',
    'summary': '从浏览器窗口迁移为独立的 Windows 应用。',
    'sections': [{'title': '独立桌面应用', 'items': [
        '使用应用内嵌的 Microsoft WebView2 显示图库，不再启动 Edge 或 Chrome 浏览器窗口。',
        '深色原生标题栏、任务栏图标和窗口按钮由拾光图库自身管理。',
    ]}],
}
PREVIOUS_BETA9 = {
    'version': '1.0.0beta9',
    'summary': '筛选更自由，全屏翻页更直接。',
    'sections': [
        {'title': '筛选与选片', 'items': [
            '每类筛选可勾选多个选项，选择“只看所选”或“排除所选”；也可对单项一键只看或排除。',
            '主界面多选照片时按 Esc 可退出多选并清空选择。',
        ]},
        {'title': '大图浏览', 'items': [
            '可手动切换适应屏幕或 100% 原图，选择后切换照片仍保持该模式；F 键可快捷切换。',
            '全屏时点击照片左半区或右半区翻页，方向光标提示操作；上下控制栏同步显隐，移近边缘才展开。',
            '图库窗口顶部标题栏改为深色，与界面背景保持一致。',
        ]},
    ],
}
PREVIOUS_BETA8 = {
    'version': '1.0.0beta8',
    'summary': '选片操作、照片筛选与深色视觉进一步统一。',
    'sections': [
        {'title': '浏览与整理', 'items': [
            '多选照片时操作栏跟随页面滚动；单击查看右侧信息、双击打开大图。',
            '右击照片可加入相册、收藏、复制、分享、打开所在文件夹或确认后删除。',
            '全部照片可按来源线索、拍摄相机、文件类型、焦距和光圈筛选。',
        ]},
        {'title': '视觉更新', 'items': [
            '侧栏使用本地打包的 Google Material Symbols 图标，窗口与品牌图标采用深色暖金配色。',
        ]},
    ],
}
PREVIOUS_RELEASE = {
    'version': '1.0.0beta7',
    'summary': '熟悉的图库功能，换上更专注的深色界面。',
    'sections': [
        {'title': '视觉更新', 'items': [
            '采用深色图库界面、暖金色重点操作和更紧凑的照片网格。',
            '照片信息与颜色直方图在图库右侧预览，打开大图后仍可查看完整信息。',
            '搜索、格式筛选、多选、相册、收藏和照片来源继续沿用现有操作。',
        ]},
    ],
}
CURRENT_NOTICE_ID = CURRENT_RELEASE['version'] + '-history'

# The first beta predates release notes; its entry describes the shipped baseline.
RELEASE_HISTORY = [
    CURRENT_RELEASE,
    PREVIOUS_RELEASE_1_0_3,
    PREVIOUS_RELEASE_1_0_1,
    PREVIOUS_BETA10,
    PREVIOUS_BETA9,
    PREVIOUS_BETA8,
    PREVIOUS_RELEASE,
    {'version': '1.0.0beta6.1', 'summary': '全屏浏览更清晰，更新记录一目了然。', 'sections': [
        {'title': '问题修复', 'items': ['修复全屏下放大缩略图被裁切的问题。']},
        {'title': '体验优化', 'items': [
            '缩略图区域背景透明，仅底部时间进度条保留底色。',
            '缩略图连续紧贴排列，放大预览按照片原始比例显示。',
            '全屏中的照片日期与缩略图说明移至顶部菜单，避免文字与照片颜色冲突。',
            '左侧下方可滚动查看 beta1 至 beta6.1 的全部更新内容。',
        ]},
    ]},
    {'version': '1.0.0beta6', 'summary': '整理文件夹，沉浸看照片。', 'sections': [
        {'title': '新增功能', 'items': [
            '右击文件夹，或进入后点击文件夹名称，即可重命名；相册和收藏归属保留。',
            '照片信息默认展开，可通过右侧箭头收起或重新展开。',
            '右上角按钮进入全屏预览，底部缩略图和时间轴在鼠标靠近时展开，离开后自动收起。',
        ]},
        {'title': '体验优化', 'items': [
            '退出全屏恢复信息栏状态；滚轮缩放、原图细节和多选继续可用。',
            '新增操作和提示同步支持九种界面语言。',
        ]},
    ]},
    {'version': '1.0.0beta5', 'summary': '用熟悉的语言，留住喜欢的瞬间。', 'sections': [
        {'title': '新增功能', 'items': [
            '支持中文、英语、日语、韩语、法语、德语、西班牙语、葡萄牙语和俄语。',
            '点击地球图标切换语言，即时更新界面并记住选择，无需重新启动。',
            '各语言使用独立的本地化名称，日期、提示和照片操作同步翻译。',
        ]},
        {'title': '体验优化', 'items': [
            '切换语言时保留当前照片、已选项目和未提交的相册名称。',
            '文件名、文件夹名和自建相册名称保持原样。',
        ]},
    ]},
    {'version': '1.0.0beta4', 'summary': '拾光图库，换上新的图标。', 'sections': [
        {'title': '视觉更新', 'items': [
            '全新深翡翠绿图标，以暖白叠片和柔金色光点表现照片与光。',
            '统一桌面快捷方式、程序图标、窗口图标及左上角品牌标识。',
        ]},
        {'title': '体验优化', 'items': [
            '提供多尺寸 Windows 图标，适配不同缩放比例与桌面图标大小。',
        ]},
    ]},
    {'version': '1.0.0beta3', 'summary': '浏览位置不丢失，大图选片与时间定位更顺手。', 'sections': [
        {'title': '新增功能', 'items': [
            '关闭大图或按 Esc 后，主界面自动定位并高亮刚刚浏览的照片，支持跨越已加载范围。',
            '缩略图旁新增“回到当前照片”，滚远后可一键让当前大图的缩略图回到中央。',
            '底部定位条新增可点击的日期坐标：全部照片或长时间范围显示年月日，31 天内的文件夹、相册及筛选范围显示月日和时分。',
            '大图界面可选择当前照片或多选缩略图，已选照片与主界面同步，可批量加入现有相册或新建相册。',
        ]},
        {'title': '体验优化', 'items': [
            '坐标点对应真实照片时间，随浏览范围、日期排序和窗口宽度更新。',
            '缩略图选择状态与当前大图位置分别标记，退出多选模式会保留已选照片。',
        ]},
    ]},
    {'version': '1.0.0beta2', 'summary': '照片来源更自由，浏览和整理更顺手。', 'sections': [
        {'title': '新增功能', 'items': [
            '新增“照片来源”：随时更换照片文件夹，也可开启全盘浏览，自行选择要扫描的磁盘。',
            '不同照片来源分别保留相册与收藏，切回原来源即可继续整理。',
            '新增更新说明窗口，新版本首次打开时提示，也可从侧栏随时查看。',
        ]},
        {'title': '体验优化', 'items': [
            '照片进度条显示真实缩略图；悬停时中心图片放大、两侧渐小，并预加载附近图片。',
        ]},
        {'title': '问题修复', 'items': [
            '修复进度条粗选后，目标照片没有处于缩略图带正中央的问题。',
            '切换照片来源后，拦截旧窗口对新来源照片的误操作。',
        ]},
    ]},
    {'version': '1.0.0beta1', 'summary': '拾光图库初版。', 'sections': [
        {'title': '初版功能', 'items': [
            '扫描本机照片并按日期、文件夹浏览，支持搜索和排序。',
            '可创建相册、收藏照片，并在大图窗口查看照片。',
            '支持常见图片以及 RAW、HEIC 等照片格式的预览。',
        ]},
    ]},
]


class ReleaseNotes:
    def __init__(self, control, release=None):
        self.path = Path(control) / 'release-notes-seen.json'
        self.release = release if release is not None else CURRENT_RELEASE
        self.lock = threading.Lock()

    def seen_versions(self):
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            values = saved.get('versions', []) if isinstance(saved, dict) else []
            return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []
        except (OSError, ValueError):
            return []

    def describe(self):
        with self.lock:
            history = [self.release, *(item for item in RELEASE_HISTORY if item['version'] != self.release['version'])]
            notice_id = CURRENT_NOTICE_ID if self.release is CURRENT_RELEASE else self.release['version']
            return {**self.release, 'history': history,
                    'unread': notice_id not in self.seen_versions()}

    def acknowledge(self, version):
        if version != self.release['version']:
            raise ValueError('更新说明版本已改变，请重新打开更新说明。')
        with self.lock:
            versions = self.seen_versions()
            notice_id = CURRENT_NOTICE_ID if self.release is CURRENT_RELEASE else version
            if notice_id not in versions:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                write_json(self.path, {'versions': [*versions, notice_id]})
        return {'ok': True}
