import re
import json
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
import pyautogui
import subprocess

import pet.windows_utils
import pet.utils

config = pet.utils.loadConfig()
client = OpenAI(
    base_url=config['llm']['endpoint'], api_key=config['llm']['api_key'])
model = config['llm']['model']


def get_windows_list() -> str:
    windows = []
    window_hwnds = pet.windows_utils.getWindowsInZOrder()
    for hwnd in window_hwnds:
        title = pet.windows_utils.getWindowTitle(hwnd)
        if not title:
            continue
        if not pet.windows_utils.isWindowVisible(hwnd):
            continue

        x, y, width, height = pet.windows_utils.getWindowRect(hwnd)
        if x is not None and y is not None and width is not None and height is not None:
            windows.append({
                "hwnd": hwnd,
                "title": title
            })
    return json.dumps(windows, ensure_ascii=False)


def keyboard_input(text: str) -> str:
    pyautogui.typewrite(text, interval=0.05)
    return f"已成功模拟键盘输入: {text}"


def cmd_run(command: str) -> str:
    DANGEROUS_PATTERNS = [
        r'\b(shutdown|reboot|restart|logoff)\b',
        r'\b(del|rm|rmdir|rd|format|diskpart|cipher)\b',
        r'\b(reg)\b',
        r'\b(net\s+user|net\s+localgroup|net\s+share)\b',
        r'\b(powershell|cmd)\b.*\b(/c|/k)\b',
        r'\b(curl|wget|Invoke-WebRequest)\b.*\|.*\b(iex|Invoke-Expression)\b'
    ]

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"[Security Blocked] 命令被拒绝，包含危险操作。"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            errors='ignore'
        )

        max_len = 4000
        stdout = result.stdout[:max_len] if result.stdout else ""
        stderr = result.stderr[:max_len] if result.stderr else ""

        if result.returncode == 0:
            return stdout.strip() if stdout.strip() else "[No Output] 命令执行成功，但没有输出。"
        else:
            return f"Error (Code {result.returncode}): {stderr.strip()}"

    except subprocess.TimeoutExpired:
        return "[Timeout] 命令执行超时，已强制终止。"
    except Exception as e:
        return f"[Exception] {str(e)}"


AVAILABLE_FUNCTIONS = {
    "get_windows_list": get_windows_list,
    "keyboard_input": keyboard_input,
    "cmd_run": cmd_run
}

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_windows_list",
            "description": "获取当前所有窗口的列表",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard_input",
            "description": "模拟键盘输入",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要输入的文本"
                    }
                },
                "required": ["text"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cmd_run",
            "description": "运行系统命令并返回输出",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的系统命令，命令将在Windows的cmd环境中执行。"
                    }
                },
                "required": ["command"]
            },
        },
    }
]


def run_llm_with_tools(messages: list[ChatCompletionMessageParam], model: str = model, max_iterations: int = 15, reasoning_effort: str = config['llm']['reasoning_effort']) -> str:
    assert reasoning_effort in ["none", "minimal", "low", "medium", "high"]
    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,  # type:ignore
            tool_choice="auto",
            reasoning_effort=reasoning_effort,  # type: ignore
        )
        msg = response.choices[0].message

        msg_dict = msg.model_dump(exclude_none=True)
        messages.append(msg_dict)  # type:ignore

        if not msg.tool_calls:
            return msg.content  # type:ignore

        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name  # type:ignore
            pet.utils.log(f"模型正在调用工具: {func_name}", "INFO")
            try:
                func_args = json.loads(
                    tool_call.function.arguments)  # type:ignore
                func_to_call = AVAILABLE_FUNCTIONS[func_name]
                func_response = func_to_call(**func_args)
                pet.utils.log(f"工具 {func_name} 执行结果: {func_response}", "INFO")
            except Exception as e:
                func_response = json.dumps({"error": str(e)})
                pet.utils.log(f"工具调用错误: {e}", "ERROR")

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "content": str(func_response),
            })
    pet.utils.log(f"工具调用超过最大迭代次数 ({max_iterations})", "WARNING")
    return ""
