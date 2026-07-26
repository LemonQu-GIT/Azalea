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


emitter = SignalEmitter()
