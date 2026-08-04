from PyQt6.QtCore import QObject, pyqtSignal


class SignalEmitter(QObject):
    click_through_changed = pyqtSignal(bool)
    model_hit_tested = pyqtSignal(bool, int, int)

    drag_started = pyqtSignal(int, int)
    drag_moved = pyqtSignal(int, int)
    drag_ended = pyqtSignal()

    global_mouse_press = pyqtSignal(int, int)
    global_mouse_move = pyqtSignal(int, int)
    global_mouse_release = pyqtSignal(int, int)

    # 全局鼠标右键事件（专门用于摸头手势：pynput 线程 emit，主线程槽安全处理）
    global_right_press = pyqtSignal(int, int)
    global_right_move = pyqtSignal(int, int)
    global_right_release = pyqtSignal(int, int)

    # 用户对话消息：内容字符串
    user_chat_message = pyqtSignal(str)
    # AI 对话回复信号：内容字符串
    ai_chat_reply = pyqtSignal(str)
    # 请求打开对话框
    request_open_chat = pyqtSignal()
    # 请求关闭对话框（前端发送消息 /ESC 后触发）
    request_close_chat = pyqtSignal()
    # 桌宠被右键点击 (screen_x, screen_y)
    model_right_clicked = pyqtSignal(int, int)
    # 桌宠被摸头：触发时不带参，由 ai 侧直接读 assembled_content
    pet_head_patted = pyqtSignal()
    # 请求播放 TTS 音频 (wav 文件路径)
    play_tts_requested = pyqtSignal(str)


emitter = SignalEmitter()
