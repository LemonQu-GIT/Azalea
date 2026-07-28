from typing import Union
import openai
import json
import base64
import cv2
from PIL import Image
import numpy as np
import io

from openai.types.chat import ChatCompletionMessageParam

import pet.utils
import pet.tool_calling


client = pet.tool_calling.client
config = pet.tool_calling.config


def format_response(resp: str) -> list | dict | None:
    try:
        answer = json.loads(resp)
        return answer
    except:
        if "```" in resp:
            resp = resp.replace(
                "```json\n", "").replace("\n```", "")
        try:
            answer = json.loads(resp)
            return answer
        except:
            try:
                answer = eval(resp)
                return answer
            except:
                print("unparseable:", resp)
                return None


def img2base64(img: np.ndarray | Image.Image) -> str:
    if isinstance(img, np.ndarray):
        img = Image.fromarray(img)
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return base64.b64encode(img_buffer.read()).decode('utf-8')


def generate_response(messages: list[ChatCompletionMessageParam], reasoning_effort: str = "medium") -> str | None:
    assert reasoning_effort in ["none", "medium", "high"]
    response = client.chat.completions.create(
        model=config['llm']['model'],
        messages=messages,
        reasoning_effort=reasoning_effort,  # type: ignore
    )
    if response.choices:
        return response.choices[0].message.content
    else:
        return None


def remove_image(messages: list[ChatCompletionMessageParam]):
    for msg in reversed(messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for i, part in enumerate(msg["content"]):  # type:ignore
                if isinstance(part, dict) and part.get("type") == "image_url":
                    del msg["content"][i]  # type:ignore
                    return


def truncate_context(
    messages: list[ChatCompletionMessageParam],
    sys_prompt: str | None = None,
    max_recent: int = 10
) -> list[ChatCompletionMessageParam]:
    if not messages:
        return []

    max_recent = max(0, max_recent)
    has_sys = messages[0]["role"] == "system"
    if sys_prompt is not None:
        final_sys_msg = {"role": "system", "content": sys_prompt}
        start_idx = 1 if has_sys else 0
    else:
        final_sys_msg = messages[0] if has_sys else None
        start_idx = 1 if has_sys else 0
    conv_messages = messages[start_idx:]
    actual_recent = max_recent - 1 if final_sys_msg else max_recent
    actual_recent = max(0, actual_recent)
    recent_messages = conv_messages[-actual_recent:] if actual_recent > 0 else []
    result = []
    if final_sys_msg:
        result.append(final_sys_msg)
    result.extend(recent_messages)
    return result
