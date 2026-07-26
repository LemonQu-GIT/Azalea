from PyQt6.QtCore import Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView


class PetWebView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setMouseTracking(True)

    def contextMenuEvent(self, a0):
        if a0 is not None:
            a0.ignore()
