from PyQt6.QtGui import (QAction, QColor, QCursor, QIcon, QMouseEvent, QPixmap)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget)
from qfluentwidgets import (
    FluentIcon as FIF,
    SplitFluentWindow,
    SubtitleLabel,
    setFont,
)


class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("settingsInterface")
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 48, 20, 20)

        label = SubtitleLabel("AI 桌宠设置")
        setFont(label, 24)
        self.vBoxLayout.addWidget(label)


class SettingsWindow(SplitFluentWindow):
    def __init__(self):
        super().__init__()
        self.settingsInterface = SettingsWidget(self)
        self.initNavigation()
        self.initWindow()

    def initNavigation(self):
        self.addSubInterface(self.settingsInterface, FIF.SETTING, "设置")

    def initWindow(self):
        self.resize(800, 600)
        self.setWindowTitle("桌宠设置")
        self.setWindowIcon(QIcon('./front/icon.png'))
        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)


class SystemTray(QSystemTrayIcon):
    def __init__(self, pet_window, parent=None):
        super().__init__(parent)
        self.pet_window = pet_window

        self.setIcon(QIcon("./front/icon.png"))
        self.setToolTip("AI 桌宠")

        menu = QMenu()
        show_action = QAction("显示/隐藏桌宠", self)
        show_action.triggered.connect(self.toggle_pet)

        settings_action = QAction("打开设置", self)
        settings_action.triggered.connect(self.show_settings)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)

        menu.addAction(show_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self.on_tray_activated)
        self.settings_win = None

    def toggle_pet(self):
        if self.pet_window.isVisible():
            self.pet_window.hide()
        else:
            self.pet_window.show()

    def show_settings(self):
        if not self.settings_win:
            self.settings_win = SettingsWindow()
        self.settings_win.show()
        self.settings_win.raise_()
        self.settings_win.activateWindow()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_pet()
