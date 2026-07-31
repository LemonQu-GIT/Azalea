import re
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QFrame, QSizePolicy
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIcon, QPainter, QColor, QFont
from qfluentwidgets import (LineEdit, PushButton, SubtitleLabel, FluentWindow, PrimaryPushButton, PasswordLineEdit,
                            ScrollArea, ExpandLayout, SettingCardGroup,
                            SwitchSettingCard, OptionsSettingCard, SettingCard,
                            TextEdit, QConfig, ConfigItem, OptionsConfigItem, RangeConfigItem,
                            BoolValidator, OptionsValidator, RangeValidator, Theme, setTheme, ColorConfigItem, setThemeColor,
                            SpinBox, Slider, qconfig, EnumSerializer, ConfigSerializer, CustomColorSettingCard)
from qfluentwidgets import FluentIcon as FIF


class PasswordLineEditSettingCard(SettingCard):
    """ Setting card with password line edit """

    def __init__(self, configItem, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.lineEdit = PasswordLineEdit(self)
        self.lineEdit.setText(str(configItem.value))
        self.lineEdit.setFixedWidth(300)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.lineEdit.textChanged.connect(self._onValueChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onValueChanged(self, value):
        qconfig.set(self.configItem, value)

    def setValue(self, value):
        self.lineEdit.setText(str(value))


class LineEditSettingCard(SettingCard):
    """ Setting card with line edit """

    def __init__(self, configItem, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.lineEdit = LineEdit(self)
        self.lineEdit.setText(str(configItem.value))
        self.lineEdit.setFixedWidth(300)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.lineEdit.textChanged.connect(self._onValueChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onValueChanged(self, value):
        qconfig.set(self.configItem, value)

    def setValue(self, value):
        self.lineEdit.setText(str(value))


class SpinBoxSettingCard(SettingCard):
    """ Setting card with spin box """

    def __init__(self, configItem, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.spinBox = SpinBox(self)
        self.spinBox.setRange(1, 100000)
        self.spinBox.setValue(int(configItem.value))
        self.spinBox.setFixedWidth(150)
        self.hBoxLayout.addWidget(self.spinBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.spinBox.valueChanged.connect(self._onValueChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onValueChanged(self, value):
        qconfig.set(self.configItem, value)

    def setValue(self, value):
        self.spinBox.setValue(int(value))


class SliderSettingCard(SettingCard):
    """ Setting card with slider """

    def __init__(self, configItem, icon, title, content=None, parent=None, range=(0, 100)):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.slider = Slider(Qt.Horizontal, self)
        self.slider.setRange(*range)
        self.slider.setValue(int(configItem.value))
        self.slider.setFixedWidth(200)
        self.valueLabel = QLabel(str(configItem.value), self)

        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(10)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.slider.valueChanged.connect(self._onValueChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onValueChanged(self, value):
        qconfig.set(self.configItem, value)
        self.valueLabel.setText(str(value))

    def setValue(self, value):
        self.slider.setValue(int(value))
        self.valueLabel.setText(str(value))


class TextEditSettingCard(SettingCard):
    """ Setting card with text edit and JSON support """

    def __init__(self, configItem, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.textEdit = TextEdit(self)
        try:
            import json
            # JSON format initialization
            val = configItem.value
            if isinstance(val, (list, dict)):
                text = json.dumps(val, indent=2, ensure_ascii=False)
            else:
                text = str(val)
        except:
            text = str(configItem.value)

        self.textEdit.setText(text)
        self.textEdit.setFixedHeight(120)

        # Add to layout
        # We will add it to the right side and let it expand.
        self.hBoxLayout.addWidget(self.textEdit, 1)
        self.hBoxLayout.addSpacing(16)

        self.textEdit.textChanged.connect(self._onValueChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onValueChanged(self):
        import json
        text = self.textEdit.toPlainText()
        try:
            # Try to parse as JSON first if it looks like it
            if text.strip().startswith(('[', '{')):
                value = json.loads(text)
            else:
                value = text  # fallback string

            qconfig.set(self.configItem, value)
            # self.textEdit.setStyleSheet("") # Clear error style if valid
        except json.JSONDecodeError:
            pass
            # self.textEdit.setStyleSheet("border: 1px solid red;")

    def setValue(self, value):
        import json
        try:
            if isinstance(value, (list, dict)):
                formatted_value = json.dumps(
                    value, indent=2, ensure_ascii=False)
            else:
                formatted_value = str(value)
        except:
            formatted_value = str(value)

        if self.textEdit.toPlainText() != formatted_value:
            self.textEdit.setText(formatted_value)


class Config(QConfig):
    # ui
    themeMode = OptionsConfigItem(
        "ui", "theme", Theme.AUTO, OptionsValidator(Theme), EnumSerializer(Theme), restart=True)
    themeColor = ColorConfigItem("QFluentWidgets", "ThemeColor", '#009faa')
    opacity = RangeConfigItem("ui", "opacity", 100, RangeValidator(10, 100))
    enableVoice = ConfigItem("ui", "enableVoice", True, BoolValidator())
    enableVision = ConfigItem("ui", "enableVision", True, BoolValidator())
    modelSize = ConfigItem(
        "ui", "modelSize", 15, RangeValidator(5, 30))
    userName = ConfigItem("ui", "username", "your name")
    # openaiAPI
    idleCooldown = ConfigItem(
        "openaiAPI", "idleCooldown", 15, RangeValidator(0, 120))
    chatCooldown = ConfigItem(
        "openaiAPI", "chatCooldown", 10, RangeValidator(0, 30))
    openaiBaseURL = ConfigItem(
        "openaiAPI", "baseURL", "http://localhost:11434/v1")
    openaiModel = ConfigItem("openaiAPI", "model",
                             "qwen3-vl:235b-instruct-cloud")
    openaiKey = ConfigItem("openaiAPI", "key", "ollama")
    openaiMaxTokens = ConfigItem("openaiAPI", "maxTokens", 2048)

    # ttsAPI
    ttsBaseURL = ConfigItem("ttsAPI", "baseURL", "http://127.0.0.1:8000")

    # live2d
    live2dModelPath = ConfigItem(
        "live2d", "modelPath", "./assets/model/tsumiki.model3.json")

    # tools
    definedTools = ConfigItem("tools", "definedTools",
                              [], None, ConfigSerializer())
    mcpServers = ConfigItem("tools", "mcpServers", {},
                            None, ConfigSerializer())


cfg = Config()
cfg.themeMode.value = Theme.AUTO
# Set custom config path
qconfig.load('config.json', cfg)


class BubbleMessage(QWidget):
    def __init__(self, text, role, parent=None):
        super().__init__(parent)
        self.role = role
        self.text = text
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)

        self.bubble = QLabel()
        self.bubble.setWordWrap(True)
        self.bubble.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.bubble.setOpenExternalLinks(True)

        # Set size policy
        self.bubble.setSizePolicy(
            QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)

        self.update_style()
        cfg.themeColor.valueChanged.connect(lambda: self.update_style())

        self.layout.setSpacing(0)
        if role == 'user':
            self.layout.addStretch(1)
            self.layout.addWidget(self.bubble, 0)
        elif role == 'assistant' or role == 'tool':
            self.layout.addWidget(self.bubble, 0)
            self.layout.addStretch(1)
        else:
            self.layout.addStretch(1)
            self.layout.addWidget(self.bubble, 0)
            self.layout.addStretch(1)

        self.set_content(text)

    def update_style(self):
        if self.role == 'user':
            # Use theme color for user
            color_val = cfg.themeColor.value
            if isinstance(color_val, QColor):
                color_hex = color_val.name()
            else:
                color_hex = str(color_val)

            self.bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: {color_hex};
                    color: white;
                    border-radius: 12px;
                    padding: 12px;
                    font-family: 'Microsoft YaHei', sans-serif;
                    font-size: 16px;
                }}
            """)
        elif self.role == 'assistant':
            self.bubble.setStyleSheet("""
                QLabel {
                    background-color: #f9f9f9;
                    color: black;
                    border: 1px solid #e0e0e0;
                    border-radius: 12px;
                    padding: 12px;
                    font-family: 'Microsoft YaHei', sans-serif;
                    font-size: 16px;
                }
            """)
        elif self.role == 'tool':
            self.bubble.setStyleSheet("""
                QLabel {
                    background-color: #fff9c4;
                    color: #555;
                    border: 1px solid #ffd54f;
                    border-radius: 8px;
                    padding: 12px;
                    font-family: 'Consolas', monospace;
                    font-size: 14px;
                }
            """)
        else:
            self.bubble.setStyleSheet("""
                QLabel {
                    color: gray;
                    font-size: 12px;
                    padding: 5px;
                    font-family: 'Microsoft YaHei', sans-serif;
                }
            """)

    def set_content(self, text):
        self.text = text
        html_text = self._markdown_to_html(text)
        self.bubble.setText(html_text)

    def _markdown_to_html(self, text):
        import re
        text = text.replace("&", "&amp;").replace(
            "<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(
            r'```(.*?)```', r'<pre style="background-color: #f0f0f0; padding: 5px;">\1</pre>', text, flags=re.DOTALL)
        text = re.sub(
            r'`(.*?)`', r'<code style="background-color: #f0f0f0; padding: 2px;">\1</code>', text)
        text = re.sub(r'^# (.*)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.*)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = text.replace('\n', '<br>')
        return text

    def resizeEvent(self, event):
        available_width = event.size().width()
        if available_width > 50:
            target_max_width = int(available_width * 0.8)
            self.bubble.setMaximumWidth(target_max_width)
        super().resizeEvent(event)

    def set_text(self, text):
        self.set_content(text)


class ChatInterface(QWidget):
    send_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("Chat-Interface")

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)

        # Title
        self.titleContainer = QWidget()
        self.titleLayout = QVBoxLayout(self.titleContainer)
        self.titleLayout.setContentsMargins(30, 30, 30, 10)
        self.titleLabel = SubtitleLabel("Conversation", self.titleContainer)
        self.titleLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.titleContainer)

        # History (Scroll Area)
        self.scrollArea = ScrollArea(self)
        self.scrollArea.setObjectName("chatScrollArea")
        self.scrollWidget = QWidget()
        self.scrollLayout = QVBoxLayout(self.scrollWidget)
        self.scrollLayout.setContentsMargins(20, 10, 20, 10)
        self.scrollLayout.setSpacing(10)
        self.scrollLayout.addStretch(1)  # Push messages to bottom initially

        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setStyleSheet("""
            QScrollArea, #chatScrollArea {
                background-color: transparent;
                border: none;
            }
            QWidget#qt_scrollarea_viewport {
                background-color: transparent;
            }
        """)

        # We need the scroll widget to be transparent too
        # Removed WA_TranslucentBackground to try and fix trailing ghost artifacts
        # self.scrollWidget.setAttribute(Qt.WA_TranslucentBackground)
        self.scrollWidget.setStyleSheet("background-color: transparent;")
        self.vBoxLayout.addWidget(self.scrollArea, 1)

        # Input area
        self.inputContainer = QWidget()
        self.inputContainerLayout = QVBoxLayout(self.inputContainer)
        self.inputContainerLayout.setContentsMargins(30, 10, 30, 30)

        self.inputLayout = QHBoxLayout()
        self.input = LineEdit()
        self.input.setPlaceholderText("Type a message to Tsumiki...")
        self.input.setClearButtonEnabled(True)

        self.send_btn = PrimaryPushButton("Send")
        self.send_btn.setIcon(FIF.SEND)

        self.inputLayout.addWidget(self.input, 1)  # Stretch input
        self.inputLayout.addWidget(self.send_btn)

        self.inputContainerLayout.addLayout(self.inputLayout)
        self.vBoxLayout.addWidget(self.inputContainer)

        self.send_btn.clicked.connect(self._on_send)
        self.input.returnPressed.connect(self._on_send)

        self.last_bubble = None

    def _on_send(self):
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.add_message('user', text)
            self.send_signal.emit(text)

    def add_reply(self, text):
        self.add_message('assistant', text)

    def add_message(self, role, content, tool_name=None):
        if role == 'tool':
            display_text = f"🛠️ Calling {tool_name} {content}"
        else:
            display_text = content

        bubble = BubbleMessage(display_text, role)
        # Add before the stretch item
        # But wait, I put stretch at top (index 0) or bottom?
        # Usually stretch is at top to push items down if few items,
        # or at bottom if we want them top-aligned.
        # Chat usually starts top-aligned. Use stretch at bottom.
        # Let's remove the initial stretch if it exists and add it back at the end?
        # No, standard VBox just adds items.
        # If I want items to start at top, I place them, and stretch at end.
        # If I want items to start at bottom, I place stretch at top.

        # Let's just append.
        self.scrollLayout.addWidget(bubble)
        self.last_bubble = bubble

        # Scroll to bottom
        QTimer.singleShot(10, self._scroll_to_bottom)

    def update_last_message(self, text):
        if self.last_bubble and self.last_bubble.role == 'assistant':
            self.last_bubble.set_text(text)
            self._scroll_to_bottom()
        else:
            # If last bubble wasn't assistant (or doesn't exist), create new
            self.add_message('assistant', text)

    def _scroll_to_bottom(self):
        scrollbar = self.scrollArea.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class SettingsInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.setObjectName("Settings-Interface")

        # Title
        self.settingLabel = SubtitleLabel("Settings", self.scrollWidget)

        # General Group
        self.generalGroup = SettingCardGroup("General", self.scrollWidget)

        self.enableVoiceCard = SwitchSettingCard(
            FIF.MICROPHONE,
            "Enable Voice Interaction",
            "Allow Tsumiki to respond with voice",
            configItem=cfg.enableVoice,
            parent=self.generalGroup
        )

        self.enableVisionCard = SwitchSettingCard(
            FIF.CAMERA,
            "Enable Vision",
            "Allow Tsumiki to see and process visual input",
            configItem=cfg.enableVision,
            parent=self.generalGroup
        )

        self.themeCard = OptionsSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            "Theme",
            "Change the appearance of the application",
            texts=["Light", "Dark", "System"],
            parent=self.generalGroup
        )
        self.themeCard.optionChanged.connect(lambda mode: setTheme(mode.value))

        self.themeColorCard = CustomColorSettingCard(
            cfg.themeColor,
            FIF.PALETTE,
            "Theme Color",
            "Change the theme color of the application",
            parent=self.generalGroup
        )
        self.themeColorCard.colorChanged.connect(setThemeColor)

        self.opacityCard = SliderSettingCard(
            cfg.opacity,
            FIF.TRANSPARENT,
            "Window Opacity",
            parent=self.generalGroup, range=(10, 100)
        )

        self.modelSizeCard = SliderSettingCard(
            cfg.modelSize,
            FIF.ZOOM,
            "Model Size",
            parent=self.generalGroup, range=(5, 30)
        )

        self.userNameCard = LineEditSettingCard(
            cfg.userName,
            FIF.PEOPLE,
            "User Name",
            "Set your name to be used in conversations",
            parent=self.generalGroup
        )

        self.generalGroup.addSettingCard(self.enableVoiceCard)
        self.generalGroup.addSettingCard(self.enableVisionCard)
        self.generalGroup.addSettingCard(self.themeCard)
        self.generalGroup.addSettingCard(self.themeColorCard)
        self.generalGroup.addSettingCard(self.opacityCard)
        self.generalGroup.addSettingCard(self.modelSizeCard)
        self.generalGroup.addSettingCard(self.userNameCard)

        # OpenAI Group
        self.openaiGroup = SettingCardGroup("OpenAI API", self.scrollWidget)

        self.openaiBaseURLCard = LineEditSettingCard(
            cfg.openaiBaseURL,
            FIF.CLOUD,
            "Base URL",
            parent=self.openaiGroup
        )

        self.openaiModelCard = LineEditSettingCard(
            cfg.openaiModel,
            FIF.LIBRARY,
            "Model",
            parent=self.openaiGroup
        )

        self.openaiKeyCard = PasswordLineEditSettingCard(
            cfg.openaiKey,
            FIF.VPN,
            "API Key",
            parent=self.openaiGroup
        )
        self.openaiKeyCard.lineEdit.setEchoMode(LineEdit.Password)

        self.openaiMaxTokensCard = SpinBoxSettingCard(
            cfg.openaiMaxTokens,
            FIF.EDIT,
            "Max Tokens",
            parent=self.openaiGroup
        )

        self.openaiIdleCooldownCard = SliderSettingCard(
            cfg.idleCooldown,
            FIF.RINGER,
            "Idle Cooldown",
            parent=self.openaiGroup,
            range=(0, 120)
        )
        self.openaiChatCooldownCard = SliderSettingCard(
            cfg.chatCooldown,
            FIF.RINGER,
            "Chat Cooldown",
            parent=self.openaiGroup,
            range=(0, 30)
        )

        self.openaiGroup.addSettingCard(self.openaiBaseURLCard)
        self.openaiGroup.addSettingCard(self.openaiModelCard)
        self.openaiGroup.addSettingCard(self.openaiKeyCard)
        self.openaiGroup.addSettingCard(self.openaiMaxTokensCard)
        self.openaiGroup.addSettingCard(self.openaiIdleCooldownCard)
        self.openaiGroup.addSettingCard(self.openaiChatCooldownCard)
        # TTS Group
        self.ttsGroup = SettingCardGroup("TTS API", self.scrollWidget)
        self.ttsBaseURLCard = LineEditSettingCard(
            cfg.ttsBaseURL,
            FIF.SPEAKERS,
            "Base URL",
            parent=self.ttsGroup
        )
        self.ttsGroup.addSettingCard(self.ttsBaseURLCard)

        # Live2D Group
        self.live2dGroup = SettingCardGroup("Live2D", self.scrollWidget)
        self.live2dModelCard = LineEditSettingCard(
            cfg.live2dModelPath,
            FIF.FOLDER,
            "Model Path",
            parent=self.live2dGroup
        )
        self.live2dGroup.addSettingCard(self.live2dModelCard)

        # Tools Group
        self.toolsGroup = SettingCardGroup("Tools", self.scrollWidget)

        self.definedToolsCard = TextEditSettingCard(
            cfg.definedTools,
            FIF.APPLICATION,
            "Defined Tools",
            "List of available tools (JSON format)",
            parent=self.toolsGroup
        )

        self.mcpServersCard = TextEditSettingCard(
            cfg.mcpServers,
            FIF.IOT,
            "MCP Servers",
            "Configuration for MCP Servers (JSON format)",
            parent=self.toolsGroup
        )

        self.toolsGroup.addSettingCard(self.definedToolsCard)
        self.toolsGroup.addSettingCard(self.mcpServersCard)

        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.settingLabel)
        self.expandLayout.addWidget(self.generalGroup)
        self.expandLayout.addWidget(self.openaiGroup)
        self.expandLayout.addWidget(self.ttsGroup)
        self.expandLayout.addWidget(self.live2dGroup)
        self.expandLayout.addWidget(self.toolsGroup)

        # Prepare Config
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        # Make the scroll area and its widget transparent so the window background shows through
        self.setObjectName('settingsInterface')
        self.scrollWidget.setObjectName('scrollWidget')
        self.setStyleSheet("""
                    QScrollArea, #scrollWidget {
                        background-color: transparent;
                        border: none;
                    }
                """)


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tsumiki")
        self.resize(800, 600)

        self.setWindowIcon(QIcon('./assets/icon.png'))
        # Create interfaces
        self.chatInterface = ChatInterface(self)
        self.settingsInterface = SettingsInterface(self)

        # Add to navigation
        self.initNavigation()

    def initNavigation(self):
        self.addSubInterface(self.chatInterface, FIF.CHAT, "Chat")
        self.addSubInterface(self.settingsInterface, FIF.SETTING, "Settings")

        # Add Navigation Separator if needed (e.g. at bottom)
        # self.navigationInterface.addSeparator()

    def switchToChat(self):
        self.switchTo(self.chatInterface)
        self.show()
        self.activateWindow()

    def switchToSettings(self):
        self.switchTo(self.settingsInterface)
        self.show()
        self.activateWindow()


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    setTheme(cfg.themeMode.value)
    app = QApplication(sys.argv)
    window = MainWindow()

    # Debug / Test messages
    window.chatInterface.add_message(
        'user', '这是一个测试，这是一个测试，这是一个测试，这是一个测试，这是一个测试，这是一个测试，这是一个测试，这是一个测试。')
    window.chatInterface.add_message('tool', '', tool_name='run_cmd')
    window.chatInterface.add_message(
        'assistant', '这是一个助手的回复。这是一个助手的回复。这是一个助手的回复。这是一个助手  ')

    window.switchToChat()
    window.show()
    sys.exit(app.exec_())
