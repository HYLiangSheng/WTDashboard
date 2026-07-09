"""War Thunder Dashboard 入口。

两种运行模式：
  1. 直连模式（默认）   python main.py
  2. 远程模式           python main.py --remote --host 192.168.1.x

快捷键:
    F11       — 全屏切换
    Ctrl+Q   — 退出
    Ctrl+N   — 连接设置
"""

import sys
import argparse
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from wtdb.dashboard_window import DashboardWindow
from wtdb.styles import DARK_THEME_QSS


def parse_args():
    parser = argparse.ArgumentParser(
        description="War Thunder Dashboard — 实时看板"
    )
    # 运行模式
    parser.add_argument(
        "--remote", action="store_true",
        help="连接远程游戏主机（需配合 --host 使用）"
    )

    parser.add_argument(
        "--host", default="localhost",
        help="游戏主机 IP（默认 localhost）"
    )
    parser.add_argument(
        "--port", type=int, default=8111,
        help="游戏端口（默认 8111）"
    )
    parser.add_argument(
        "--refresh", type=int, default=100,
        help="刷新间隔 ms (默认: 100)"
    )
    parser.add_argument(
        "--fullscreen", action="store_true",
        help="全屏启动"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ---- 启动仪表盘 ----
    app = QApplication(sys.argv)
    app.setApplicationName("War Thunder Dashboard")
    app.setStyleSheet(DARK_THEME_QSS)

    window = DashboardWindow(
        host=args.host,
        port=args.port,
        refresh_ms=args.refresh,
        remote=args.remote,
    )

    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
