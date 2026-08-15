from pet.tray import SettingsWindow
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QEvent
from PyQt6.QtWidgets import QApplication
import os
import sys
import socket
import threading

# 注意：这个文件是设置窗口的独立进程入口。
# 这里开启 QT_ENABLE_HIGHDPI_SCALING，让 qfluentwidgets 正常显示。
# 桌宠主进程 (main.py) 会关闭这个设置，两者通过进程隔离解决DPI缩放冲突。
#
# 为了让"打开设置"瞬间响应，本进程在启动时就创建 SettingsWindow 并隐藏，
# 之后通过本地 TCP 端口接收主进程发来的 SHOW/HIDE/QUIT 命令来控制显示或退出。

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
if sys.platform == "win32":
    os.environ["QT_QPA_PLATFORM"] = "windows:dpiawareness=3"


DEFAULT_CMD_PORT = 52341


class CommandBridge(QObject):
    """线程安全的命令桥：TCP 线程通过信号把命令投递到 Qt 主线程。"""

    show_requested = pyqtSignal()
    hide_requested = pyqtSignal()
    quit_requested = pyqtSignal()


class ManagedSettingsWindow(SettingsWindow):
    """带关闭拦截的设置窗口：点 X 时只隐藏，不退出进程。"""

    def closeEvent(self, event: QCloseEvent):  # type: ignore
        # 只隐藏，不真正关闭（进程保持预创建状态）
        event.ignore()
        self.hide()


def parse_port(argv: list[str]) -> int:
    for i, arg in enumerate(argv):
        if arg.startswith("--port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                pass
    return DEFAULT_CMD_PORT


def run_cmd_server(port: int, bridge: CommandBridge):
    """本地 TCP 命令服务器线程入口。

    协议：主进程连接后发送一行文本（以换行或EOF结尾）即可。
    支持的命令：SHOW / HIDE / TOGGLE / QUIT / PING
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_sock.bind(("127.0.0.1", port))
    except OSError:
        # 端口被占：把监听端口写一个文件告知？简单起见直接退出。
        # 正常情况下由主进程选一个空闲端口传进来，这里不会失败。
        return

    server_sock.listen(8)
    server_sock.settimeout(0.5)

    while True:
        try:
            conn, _ = server_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            conn.settimeout(2.0)
            chunks: list[bytes] = []
            while True:
                try:
                    data = conn.recv(256)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
                # 遇到换行就当命令结束
                if b"\n" in data or b"\r" in data:
                    break
            raw = b"".join(chunks).decode(
                "utf-8", errors="ignore").strip().upper()
            # 取第一行
            if "\n" in raw:
                raw = raw.split("\n", 1)[0]
            if "\r" in raw:
                raw = raw.split("\r", 1)[0]
            cmd = raw.strip()

            if cmd == "SHOW":
                bridge.show_requested.emit()
                try:
                    conn.sendall(b"OK SHOW\n")
                except OSError:
                    pass
            elif cmd == "HIDE":
                bridge.hide_requested.emit()
                try:
                    conn.sendall(b"OK HIDE\n")
                except OSError:
                    pass
            elif cmd == "TOGGLE":
                # 本进程自己不知道当前显隐状态，统一走show逻辑（显示并置顶）
                bridge.show_requested.emit()
                try:
                    conn.sendall(b"OK TOGGLE\n")
                except OSError:
                    pass
            elif cmd == "PING":
                try:
                    conn.sendall(b"PONG\n")
                except OSError:
                    pass
            elif cmd == "QUIT":
                try:
                    conn.sendall(b"OK QUIT\n")
                except OSError:
                    pass
                bridge.quit_requested.emit()
                # quit 信号触发 app.quit，退出进程
                break
            else:
                try:
                    conn.sendall(b"ERR UNKNOWN\n")
                except OSError:
                    pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    try:
        server_sock.close()
    except OSError:
        pass


def main():
    port = parse_port(sys.argv)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    # 最后一个窗口关闭时不退出进程（保持预创建）
    app.setQuitOnLastWindowClosed(False)

    win = ManagedSettingsWindow()
    # 预创建，但不显示
    # 不调用 win.show()

    bridge = CommandBridge()

    def _show_settings():
        # 强制应用目标尺寸 + 居中，解决预创建后尺寸被拉成正方形的问题
        from PyQt6.QtCore import QSize
        win.resize(QSize(900, 700))
        screen = win.screen() or QApplication.screens()[0]
        geom = screen.availableGeometry()
        win.move(
            geom.x() + (geom.width() - 900) // 2,
            geom.y() + (geom.height() - 700) // 2,
        )
        win.show()
        win.raise_()
        win.activateWindow()

    bridge.show_requested.connect(_show_settings)
    bridge.hide_requested.connect(win.hide)
    bridge.quit_requested.connect(app.quit)

    server_thread = threading.Thread(
        target=run_cmd_server, args=(port, bridge), daemon=True,
        name="settings-cmd-server",
    )
    server_thread.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
