# Shiguang Gallery

拾光图库（Shiguang Gallery）是一款本地优先的 Windows 照片图库。照片文件和相册数据保留在用户自己的电脑上；程序不要求账号登录。

## Features

- 浏览本地照片与文件夹
- 本地收藏、相册和照片信息
- 可选的联网更新检查
- Windows 10/11 x64 桌面应用

## Build

Install Python 3.12 x64 and NSIS 3.12, then run:

```powershell
.\packaging\build_release.ps1 -Python python -MakeNSIS 'path\to\makensis.exe'
```

The build downloads Python dependencies from PyPI. The resulting installer is published through the [release repository](https://github.com/zhongguodecainiao/shiguang-gallery-updates/releases).

## Privacy

The application does not upload photos, albums, or other user content. When a user explicitly chooses to check for updates, it retrieves a public version manifest; opening a download link is also initiated by the user.

## License

GPL-3.0-or-later. See [LICENSE.txt](LICENSE.txt).

## Code signing policy

See [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md).
