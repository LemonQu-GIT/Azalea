import json
import os
import sys
from datetime import datetime

from rich.console import Console

console = Console()


def _config_path() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "./configs/config.json"))


def loadConfig() -> dict:
    with open(_config_path(), 'r', encoding='utf-8') as f:
        return json.load(f)


def saveConfig(config: dict):
    with open(_config_path(), 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def log(content: str, eventType: str, show: bool = True, save: bool = True):
    back_frame = sys._getframe().f_back
    if back_frame is not None:
        back_filename = os.path.basename(back_frame.f_code.co_filename)
        back_funcname = back_frame.f_code.co_name
        back_lineno = back_frame.f_lineno
    else:
        back_filename = "Unknown"
        back_funcname = "Unknown"
        back_lineno = "Unknown"
    now = datetime.now()
    time = now.strftime("%Y-%m-%d %H:%M:%S")
    logger = f"[{time}] <{back_filename}:{back_lineno}> <{back_funcname}()> {eventType}: {content}"
    if eventType.lower() == "info":
        style = "green"
    elif eventType.lower() == "error":
        style = "red"
    elif eventType.lower() == "critical":
        style = "bold red"
    elif eventType.lower() == "event":
        style = "#ffab70"
    elif eventType.lower() == "warning":
        style = "yellow"
    else:
        style = ""
    if show:
        console.print(logger, style=style)
    if save:
        with open('latest.log', 'a', encoding='utf-8') as f:
            f.write(f'{logger}\n')
