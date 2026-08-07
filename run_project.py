import os
import sys
import platform
import subprocess
import json
import threading
import time
import collections
import signal

try:
    from modelscope import snapshot_download
except ImportError:
    print("modelscope未安装，正在安装modelscope...")
    subprocess.run([sys.executable, "-m", "pip",
                   "install", "modelscope"], check=True)
    from modelscope import snapshot_download

os.environ["UV_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "configs", "config.json")
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def interactive_select(title: str, options: list[str], default_index: int = 0) -> str:
    """
    Windows 控制台交互式选择菜单：
    - ↑/↓ 方向键切换选项
    - Enter 确定
    若在非 Windows 控制台或不支持 msvcrt 的环境下，自动降级为数字输入模式。
    """
    try:
        import msvcrt
    except ImportError:
        # 降级：普通数字选择
        print(f"\n{title}")
        for i, opt in enumerate(options):
            mark = " (默认)" if i == default_index else ""
            print(f"  {i + 1}. {opt}{mark}")
        while True:
            raw = input(f"请输入选择（1-{len(options)}，回车使用默认）：").strip()
            if not raw:
                return options[default_index]
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1]
            print("输入无效，请重新输入。")

    current = default_index
    n = len(options)

    def render_menu(first_time: bool = False):
        if not first_time:
            sys.stdout.write(f"\033[{n + 1}A")
        print(title)
        for i, opt in enumerate(options):
            if i == current:
                print(f"  > \033[1;32m{opt}\033[0m")
            else:
                print(f"    {opt}")
        sys.stdout.flush()

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

    render_menu(first_time=True)

    while True:
        ch = msvcrt.getwch()
        if ch in ("\xe0", "\x00"):
            arrow = msvcrt.getwch()
            if arrow == "H":
                current = (current - 1) % n
                render_menu()
            elif arrow == "P":
                current = (current + 1) % n
                render_menu()
            elif arrow == "M":
                current = (current + 1) % n
                render_menu()
            elif arrow == "K":
                current = (current - 1) % n
                render_menu()
        elif ch in ("\r", "\n"):
            print()
            return options[current]
        elif ch == "\x1b":
            print()
            return options[default_index]
        elif ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < n:
                current = idx
                render_menu()


def config_llm():
    llm_providers = ["Openai", "本地 Ollama"]
    llm_provider = interactive_select(
        "请选择 LLM 提供商：", llm_providers, default_index=0)

    if llm_provider == "Openai":
        endpoint = input(
            "请输入OpenAI的API地址（默认值为https://api.openai.com/v1）：") or "https://api.openai.com/v1"
        while True:
            api_key = input("请输入API Key：")
            if api_key:
                break
            print("API Key 不能为空！")
        while True:
            model = input("请输入模型名称：")
            if model:
                break
            print("模型名称不能为空！")

    elif llm_provider == "本地 Ollama":
        endpoint = input(
            "请输入Ollama的API地址（默认值为http://localhost:11434/v1/）：") or "http://localhost:11434/v1/"
        api_key = "ollama"
        model = input("请输入模型名称（默认值为gemma4:31b-cloud）：") or "gemma4:31b-cloud"

    else:
        raise RuntimeError(f"未知的提供商：{llm_provider}")

    return endpoint, api_key, model


def check_uv():
    try:
        result = subprocess.run(["uv", "--version"],
                                capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def install_dependencies():
    config = load_config()
    uv_installed = check_uv()
    if uv_installed:
        subprocess.run(["uv", "sync", "--extra", "local"],
                       check=True, cwd=BASE_DIR)
    else:
        print("uv未安装，正在安装uv...")
        subprocess.run([sys.executable, "-m", "pip",
                       "install", "uv"], check=True)
        subprocess.run(["uv", "sync", "--extra", "local"],
                       check=True, cwd=BASE_DIR)

    embedding_exists = os.path.exists(
        os.path.join(DATA_DIR, "bge-small-zh-v1.5", "model.safetensors"))
    force_download_embedding = False

    tts_exists = os.path.exists(
        os.path.join(DATA_DIR, "tts_model", "vits_fp32.onnx"))
    force_download_tts = False

    os.makedirs(DATA_DIR, exist_ok=True)

    if not embedding_exists or force_download_embedding:
        print("正在下载模型 bge-small-zh-v1.5，请耐心等待...")
        snapshot_download(
            'BAAI/bge-small-zh-v1.5',
            local_dir=os.path.join(DATA_DIR, "bge-small-zh-v1.5"))
    else:
        print("模型 bge-small-zh-v1.5 已存在，跳过下载。")
    config['llm']['embedding_model'] = os.path.abspath(
        os.path.join(DATA_DIR, "bge-small-zh-v1.5"))

    if not tts_exists or force_download_tts:
        print("正在下载模型 tts_model，请耐心等待...")
        snapshot_download(
            'LemonQu/Mika_GenieTTS',
            local_dir=os.path.join(DATA_DIR, "tts_model"))
    else:
        print("模型 tts_model 已存在，跳过下载。")
    config['tts']['onnx_model_dir'] = os.path.abspath(
        os.path.join(DATA_DIR, "tts_model"))
    config['tts']['reference_audio_path'] = os.path.abspath(
        os.path.join(DATA_DIR, "tts_model", "reference_audio", "mika_normal.wav"))

    print("正在配置LLM服务...")
    endpoint, api_key, model = config_llm()
    config['llm']['endpoint'] = endpoint
    config['llm']['api_key'] = api_key
    config['llm']['model'] = model
    save_config(config)


# ============================================================
# TUI 多终端运行器
# ============================================================

# 每个日志面板保留的最大行数（环形缓冲）
LOG_BUFFER_SIZE = 1000
# TUI 刷新间隔（秒）
REFRESH_INTERVAL = 0.08
# DETACHED_PROCESS 值（Windows），让子进程不共享 Ctrl-C
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


class ProcessOutputCapturer:
    """负责启动一个子进程并把 stdout/stderr 捕获进环形缓冲。"""

    def __init__(self, name: str, cmd: list[str], cwd: str, env: dict | None = None):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env or os.environ.copy()
        # 让子进程不缓冲 print 输出
        self.env.setdefault("PYTHONUNBUFFERED", "1")

        self.buffer: collections.deque[str] = collections.deque(
            maxlen=LOG_BUFFER_SIZE)
        self.buffer_lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self._exit_code: int | None = None
        self._threads: list[threading.Thread] = []

    def add_line(self, line: str):
        # 去掉可能的末尾换行
        if line.endswith("\n"):
            line = line[:-1]
        if line.endswith("\r"):
            line = line[:-1]
        # Windows 控制台换行符
        line = line.replace("\r\n", "\n").replace("\r", "\n")
        for sub in line.split("\n"):
            if sub or line:  # 空行也保留，但全空跳过
                with self.buffer_lock:
                    self.buffer.append(sub)

    def start(self):
        # Windows: DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
        # 这样子进程不会收到父进程的 Ctrl-C 事件
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
            # DETACHED 可能导致 GUI 进程的 stdin/stdout 无法交互，所以这里用管道

        # 先打一个"新终端起始 banner"，切面板 / 启动时看起来像真的独立终端
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        cmd_str = " ".join(
            # 简单转义带空格的参数
            (f'"{a}"' if " " in a else a) for a in self.cmd
        )
        self.add_line("=" * 72)
        self.add_line(f"  [终端 {self.name}]  启动时间: {ts}")
        self.add_line(f"  工作目录: {self.cwd}")
        self.add_line(f"  执行命令: {cmd_str}")
        self.add_line("=" * 72)

        try:
            self.process = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                creationflags=creationflags,
            )
            pid = self.process.pid
            self.add_line(f"进程已启动，PID={pid}，等待输出...")
        except FileNotFoundError as e:
            self.add_line(f"[ERROR] 启动失败：找不到可执行文件 {self.cmd[0]} - {e}")
            self._exit_code = -1
            return

        def pump(stream):
            try:
                # 按行读；对字节流 decode，用 surrogateescape 避免奇怪字符崩
                for raw in stream:
                    try:
                        text = raw.decode("utf-8", errors="replace")
                    except Exception:
                        text = str(raw)
                    if text:
                        self.add_line(text)
            except Exception as e:
                self.add_line(f"[ERROR] 输出管道异常：{e}")
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        t = threading.Thread(target=pump, args=(
            self.process.stdout,), daemon=True)
        t.start()
        self._threads.append(t)

        def wait():
            try:
                self._exit_code = self.process.wait()  # type:ignore
                self.add_line(f"[进程已退出，退出码={self._exit_code}]")
            except Exception as e:
                self.add_line(f"[ERROR] 等待进程异常：{e}")

        wt = threading.Thread(target=wait, daemon=True)
        wt.start()
        self._threads.append(wt)

    @property
    def is_alive(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    def terminate_tree(self):
        """Windows 下用 taskkill 强制杀进程树（包括 uv 再起的所有子进程）。"""
        if self.process is None:
            return
        pid = self.process.pid
        try:
            # 先温柔点，再强杀
            self.process.terminate()
        except Exception:
            pass
        if platform.system() == "Windows":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        else:
            try:
                self.process.kill()
            except Exception:
                pass

    def snapshot_lines(self) -> list[str]:
        with self.buffer_lock:
            return list(self.buffer)

    def clear_buffer(self):
        """清空当前终端的日志缓冲（模拟终端清屏）。"""
        with self.buffer_lock:
            self.buffer.clear()
        # 加一个清屏标记，方便识别
        ts = time.strftime("%H:%M:%S")
        self.add_line(f"[清屏 {ts}] ------------ 已清空此终端的历史日志 ------------")


# ----------- TUI 渲染 -----------
# 简单的 ANSI 辅助
ANSI_CLEAR = "\033[2J"
ANSI_HOME = "\033[H"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE_BG = "\033[47m"
ANSI_BLUE_BG = "\033[44m"
ANSI_DARK = "\033[100m"


def _enable_vt_mode():
    """Windows 10+ 开启 VT100 支持。"""
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
    except Exception:
        return False
    return False


def _get_console_size() -> tuple[int, int]:
    """返回 (cols, rows)，失败用 (120, 30)。"""
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        try:
            import ctypes

            class COORD(ctypes.Structure):
                _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

            class SMALL_RECT(ctypes.Structure):
                _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                            ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                            ("wAttributes", ctypes.c_ushort), ("srWindow", SMALL_RECT),
                            ("dwMaximumWindowSize", COORD)]
            kernel32 = ctypes.windll.kernel32
            h = kernel32.GetStdHandle(-11)
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if kernel32.GetConsoleScreenBufferInfo(h, ctypes.byref(csbi)):
                cols = csbi.srWindow.Right - csbi.srWindow.Left + 1
                rows = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
                return cols, rows
        except Exception:
            pass
        return 120, 30


def _truncate(text: str, width: int) -> str:
    """按显示宽度（简易版：中文算 2）截断，结尾加 …。"""
    w = 0
    out = []
    for ch in text:
        cw = 2 if ord(ch) > 127 else 1
        if w + cw > width:
            out.append("…")
            break
        out.append(ch)
        w += cw
    return "".join(out)


def _pad(text: str, width: int) -> str:
    w = sum(2 if ord(c) > 127 else 1 for c in text)
    if w >= width:
        return _truncate(text, width)
    return text + " " * (width - w)


class MultiTerminalUI:
    def __init__(self, capturers: list[ProcessOutputCapturer]):
        self.capturers = capturers
        self.names = [c.name for c in capturers]
        self.active_idx = 0
        # 每个面板自己维护滚动偏移；True 表示自动追最新
        self.scroll_tails = [True] * len(capturers)
        self.scroll_offsets = [0] * len(capturers)  # 从倒数第几行开始看（如果非 tail 模式）

        self.stop_requested = threading.Event()
        self.key_lock = threading.Lock()
        self.vt_supported = _enable_vt_mode()
        self.last_render_ts = 0.0
        self.status_msg = ""
        self.status_ts = 0.0

    def set_status(self, msg: str, duration: float = 3.0):
        self.status_msg = msg
        self.status_ts = time.time() + duration

    # ------- 键盘处理 -------
    def handle_key(self, key_seq: tuple[str, ...]):
        """处理一个按键元组：
            ("char", ch) / ("arrow", "H"|"P"|"M"|"K") / ("key", "I"|"Q"|"R"|"S")
            I=PgUp / Q=非扩展 PgDn(PgDn 扩展是 'Q' 吗？实际是 'I'=PgUp 'Q'=PgDn)
        """
        n = len(self.capturers)
        if len(key_seq) == 2 and key_seq[0] == "arrow":
            arrow = key_seq[1]
            if arrow == "M":  # 右：下一个 tab
                with self.key_lock:
                    self.active_idx = (self.active_idx + 1) % n
                    self.set_status(f"已切换到：{self.names[self.active_idx]}")
            elif arrow == "K":  # 左：上一个 tab
                with self.key_lock:
                    self.active_idx = (self.active_idx - 1) % n
                    self.set_status(f"已切换到：{self.names[self.active_idx]}")
            elif arrow == "H":  # 上：向上滚
                self._scroll_panel(self.active_idx, -3)
            elif arrow == "P":  # 下：向下滚
                self._scroll_panel(self.active_idx, +3)
            elif arrow == "I":  # PgUp（扩展序列里 I 是 Home？待确认，后面实测覆盖）
                self._scroll_panel(self.active_idx, -20)
            elif arrow == "Q":  # PgDn
                self._scroll_panel(self.active_idx, +20)
            elif arrow == "G":  # Home
                self._scroll_panel_to(self.active_idx, "top")
            elif arrow == "O":  # End
                self._scroll_panel_to(self.active_idx, "tail")
        elif len(key_seq) == 2 and key_seq[0] == "char":
            ch = key_seq[1]
            if ch == "q":
                self.stop_requested.set()
            elif ch in ("c", "C", "\x0c"):
                # c / C / Ctrl+L 清空当前面板的日志（模拟终端清屏）
                cur = self.active_idx
                self.capturers[cur].clear_buffer()
                self.scroll_tails[cur] = True
                self.scroll_offsets[cur] = 0
                self.set_status(f"{self.names[cur]}：已清屏", duration=2.0)
            elif ch in ("\r", "\n"):
                self._scroll_panel_to(self.active_idx, "tail")
            elif ch in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
                idx = int(ch) - 1
                if 0 <= idx < n:
                    with self.key_lock:
                        self.active_idx = idx
                        self.set_status(f"已切换到：{self.names[self.active_idx]}")
            elif ch in ("h", "H"):
                with self.key_lock:
                    self.active_idx = (self.active_idx - 1) % n
                    self.set_status(f"已切换到：{self.names[self.active_idx]}")
            elif ch in ("l", "L"):
                with self.key_lock:
                    self.active_idx = (self.active_idx + 1) % n
                    self.set_status(f"已切换到：{self.names[self.active_idx]}")
            elif ch in ("j", "J"):
                self._scroll_panel(self.active_idx, +3)
            elif ch in ("k", "K"):
                self._scroll_panel(self.active_idx, -3)
            elif ch in ("g", "G"):
                self._scroll_panel_to(self.active_idx, "top")
        elif len(key_seq) == 2 and key_seq[0] == "key":
            k = key_seq[1]
            if k == "I":  # 扩展 PgUp
                self._scroll_panel(self.active_idx, -20)
            elif k == "Q":  # 扩展 PgDn
                self._scroll_panel(self.active_idx, +20)
            elif k == "G":  # Home
                self._scroll_panel_to(self.active_idx, "top")
            elif k == "O":  # End
                self._scroll_panel_to(self.active_idx, "tail")

    def _scroll_panel(self, idx: int, delta: int):
        with self.key_lock:
            cap = self.capturers[idx]
            lines = cap.snapshot_lines()
            total = len(lines)
            if self.scroll_tails[idx]:
                # 切到手动模式：先以当前 tail 算 offset
                self.scroll_tails[idx] = False
                self.scroll_offsets[idx] = 0
            # offset 含义：显示末尾 - offset 开始往上一屏。offset=0 表示最后一屏，越大越靠前
            self.scroll_offsets[idx] = max(0, min(max(0, total - 1),
                                                  self.scroll_offsets[idx] - delta))
            # 如果滚到接近末尾，回到 tail
            if self.scroll_offsets[idx] <= 0:
                self.scroll_tails[idx] = True
                self.scroll_offsets[idx] = 0
            self.set_status(
                f"{self.names[idx]} 滚动：{total} 行"
                + ("（追最新）" if self.scroll_tails[idx] else f"（距末尾 {self.scroll_offsets[idx]} 行）"),
                duration=1.5,
            )

    def _scroll_panel_to(self, idx: int, where: str):
        with self.key_lock:
            if where == "tail":
                self.scroll_tails[idx] = True
                self.scroll_offsets[idx] = 0
                self.set_status(f"{self.names[idx]}：回到最新输出", duration=1.5)
            else:
                self.scroll_tails[idx] = False
                cap = self.capturers[idx]
                total = len(cap.snapshot_lines())
                self.scroll_offsets[idx] = max(0, total - 1)
                self.set_status(f"{self.names[idx]}：回到顶部", duration=1.5)

    # ------- 渲染 -------
    def render_once(self):
        cols, rows = _get_console_size()
        rows = max(10, rows)
        cols = max(40, cols)
        # 结构：行0 = 标签栏；行1 = 分隔线；行2..rows-3 = 日志；rows-2 = 状态栏；rows-1 = 帮助
        # 注意用整屏清空以防闪烁
        if self.vt_supported:
            out = [ANSI_HOME]
        else:
            # fallback: cls 命令（比较慢，但能用）
            os.system("cls")
            out = []

        # ---- 标签栏 ----
        tabs_line = []
        for i, name in enumerate(self.names):
            is_active = (i == self.active_idx)
            cap = self.capturers[i]
            alive = cap.is_alive
            if alive:
                dot = f"{ANSI_GREEN}●{ANSI_RESET}"
            else:
                dot = f"{ANSI_RED}●{ANSI_RESET}"
            label_plain = f" {i + 1}. {name} ● "
            if is_active:
                tab = f"{ANSI_BOLD}{ANSI_BLUE_BG}\033[97m{label_plain}{ANSI_RESET}"
            else:
                tab = f"{ANSI_DARK}{label_plain}{ANSI_RESET}"
            tabs_line.append(tab)
            tabs_line.append(" ")
        out.append("".join(tabs_line).rstrip())
        out.append("")

        # ---- 内容区 ----
        # 扣除 tab(1) + sep(1) + status(1) + help(1)
        content_rows = max(3, rows - 4)
        active_cap = self.capturers[self.active_idx]
        active_lines = active_cap.snapshot_lines()
        total_lines = len(active_lines)

        if self.scroll_tails[self.active_idx]:
            start = max(0, total_lines - content_rows)
        else:
            # offset=0 表示最后一屏；offset 越大，越往前
            off = self.scroll_offsets[self.active_idx]
            start = max(0, total_lines - content_rows - off)
        end = start + content_rows

        # 左侧加行号？简洁起见不加，只加时间/滚动提示
        shown = active_lines[start:end]
        # 补齐底部空行
        if len(shown) < content_rows:
            shown = shown + [""] * (content_rows - len(shown))
        for line in shown:
            cut = _truncate(line, cols)
            out.append(cut)

        # 分隔线
        sep = "─" * cols if self.vt_supported else "-" * cols
        out.append(sep)

        # ---- 状态栏 ----
        status_parts = []
        # 活动进程信息
        name = self.names[self.active_idx]
        cap = active_cap
        if cap.is_alive:
            status_parts.append(
                f"{name}: {ANSI_GREEN}运行中 (pid={cap.process and cap.process.pid}){ANSI_RESET}")
        else:
            ec = cap.exit_code if cap.exit_code is not None else "?"
            status_parts.append(
                f"{name}: {ANSI_RED}已退出 (code={ec}){ANSI_RESET}")
        # 滚动位置
        visible_start = start + 1 if total_lines > 0 else 0
        visible_end = min(total_lines, end)
        status_parts.append(
            f"行 {visible_start}-{visible_end}/{total_lines}"
            + ("（追最新）" if self.scroll_tails[self.active_idx] else "")
        )
        # 临时提示
        if time.time() < self.status_ts and self.status_msg:
            status_parts.append(f"{ANSI_YELLOW}{self.status_msg}{ANSI_RESET}")
        status_line = " | ".join(status_parts)
        out.append(_truncate(status_line, cols))

        # ---- 帮助栏 ----
        help_msg = (
            "←/→ 或 h/l 切面板  |  ↑/↓ 或 j/k 滚  |  PgUp/PgDn 翻  |  "
            "Home/End 顶/底  |  1-9 切面板  |  c 或 Ctrl+L 清本屏  |  q 退出全部"
        )
        out.append(f"{ANSI_DARK}{_truncate(help_msg, cols)}{ANSI_RESET}")

        text = "\n".join(out)
        if self.vt_supported:
            text = ANSI_CLEAR + ANSI_HOME + text + ANSI_RESET
        sys.stdout.write(text)
        sys.stdout.flush()

    # ------- 主循环 -------
    def loop(self):
        try:
            import msvcrt

            def kbd_loop():
                while not self.stop_requested.is_set():
                    try:
                        if not msvcrt.kbhit():
                            time.sleep(0.02)
                            continue
                        ch = msvcrt.getwch()
                        if ch in ("\xe0", "\x00"):
                            arrow = msvcrt.getwch()
                            self.handle_key(("arrow", arrow))
                        else:
                            self.handle_key(("char", ch))
                    except Exception:
                        time.sleep(0.05)
                        continue

            threading.Thread(target=kbd_loop, daemon=True).start()
        except ImportError:
            self.set_status(
                "当前环境不支持 msvcrt，按 Enter 继续（将不支持键盘导航）", duration=99999)

        try:
            while not self.stop_requested.is_set():
                try:
                    self.render_once()
                except Exception:
                    # 渲染失败不要崩主循环
                    pass
                # 用 Event.wait 可让 stop 立即响应
                self.stop_requested.wait(REFRESH_INTERVAL)
        finally:
            # 退出时清掉颜色
            if self.vt_supported:
                sys.stdout.write(ANSI_RESET + "\n")
                sys.stdout.flush()


def run_with_tui():
    """
    按配置启动 tts_api / embedding_api / main 三个进程，用 TUI 多终端显示输出。
    支持 ←/→ 切换面板，Ctrl-C 或 q 键终止全部子进程。
    """
    config = load_config()

    # 决定启动哪些进程（有顺序：TTS、Embedding、Main）
    capturers: list[ProcessOutputCapturer] = []

    def make_cmd(script: str) -> list[str]:
        # 用 uv run + python 脚本（或直接 uv run 脚本），保持一致
        return ["uv", "run", script]

    tts_enabled = config.get("tts", {}).get("enabled", False)
    llm_enabled = config.get("llm", {}).get("enabled", False)

    if tts_enabled:
        print("准备启动 TTS 服务...")
        capturers.append(ProcessOutputCapturer(
            "TTS", make_cmd("tts_api.py"), cwd=BASE_DIR,
        ))
    if llm_enabled:
        print("准备启动 Embedding 服务...")
        capturers.append(ProcessOutputCapturer(
            "Embedding", make_cmd("embedding_api.py"), cwd=BASE_DIR,
        ))
    # main.py 总是启动
    capturers.append(ProcessOutputCapturer(
        "Main", make_cmd("main.py"), cwd=BASE_DIR,
    ))

    if not capturers:
        print("没有任何要启动的进程，退出。")
        return

    # 启动：API 服务先起，给一点时间再启动 main，避免 PyQt 启动时 API 没 ready
    delay_between_starts = 1.5
    for idx, cap in enumerate(capturers):
        cap.start()
        # 如果是 Main 且前面有 API，多等一会
        if cap.name == "Main" and len(capturers) > 1:
            time.sleep(max(0.0, delay_between_starts * 2))
        elif idx < len(capturers) - 1:
            time.sleep(delay_between_starts)

    ui = MultiTerminalUI(capturers)

    # 处理 Ctrl-C：优雅地请求退出
    def on_sigint(signum, frame):
        ui.set_status(
            f"{ANSI_RED}收到中断信号，正在清理所有子进程...{ANSI_RESET}", duration=99999)
        ui.stop_requested.set()

    original_sigint = signal.signal(signal.SIGINT, on_sigint)

    # Windows: SetConsoleCtrlHandler 捕获关闭窗口事件
    try:
        if platform.system() == "Windows":
            import ctypes
            HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

            def ctrl_handler(ctrl_type):
                # CTRL_C=0, CTRL_BREAK=1, CTRL_CLOSE=2, CTRL_LOGOFF=5, CTRL_SHUTDOWN=6
                ui.stop_requested.set()
                return True
            _ctrl_cb = HandlerRoutine(ctrl_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_ctrl_cb, True)
    except Exception:
        pass

    try:
        print("\nTUI 启动中...（退出请按 q 或 Ctrl-C）\n")
        time.sleep(0.5)
        ui.loop()
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        print("\n正在终止所有子进程...")
        # 逆序终止：先杀 Main（GUI），再杀 API
        for cap in reversed(capturers):
            try:
                cap.terminate_tree()
            except Exception:
                pass
        # 给一点时间让它们真的死
        deadline = time.time() + 5.0
        while any(c.is_alive for c in capturers) and time.time() < deadline:
            time.sleep(0.2)
        # 最后再试一次强杀
        for cap in reversed(capturers):
            try:
                cap.terminate_tree()
            except Exception:
                pass
        print("已完成清理，退出。")


def main():
    if platform.system() != "Windows":
        print("本项目仅支持Windows系统，请在Windows系统下运行")
        sys.exit(1)

    if not os.path.exists(CONFIG_PATH):
        print(f"找不到配置文件：{CONFIG_PATH}")
        print("请确保在正确的项目目录下运行此脚本。")
        sys.exit(1)

    runtypes = ["安装依赖", "运行项目"]
    runtype = interactive_select("请选择要执行的操作：", runtypes, default_index=1)

    if runtype == "安装依赖":
        install_dependencies()
    elif runtype == "运行项目":
        run_with_tui()


if __name__ == "__main__":
    main()
