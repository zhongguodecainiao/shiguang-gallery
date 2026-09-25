"""在本机提供拾光图库更新清单和安装包。

用法：python update_server.py --directory 发布包/1.0.0 --port 8765
将本机通过公网提供服务时，还需要路由器端口转发、DNS/公网地址和防火墙规则。
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='拾光图库更新服务器')
    parser.add_argument('--directory', default='发布包/1.0.0', help='发布文件目录')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--bind', default='0.0.0.0', help='监听地址；仅本机测试可用 127.0.0.1')
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / 'update-channel.json'
    if not manifest.exists():
        manifest.write_text(json.dumps({
            'app': '拾光图库', 'version': '1.0.0', 'display_version': 'v 1.0.0',
            'published_at': '2026-09-26', 'summary': '拾光图库 1.0.0 已发布。',
            'download_url': '', 'sha256': '', 'mandatory': False,
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    request_handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer((args.bind, args.port), request_handler)
    print(f'更新服务器已启动：http://{args.bind}:{args.port}/update-channel.json')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
