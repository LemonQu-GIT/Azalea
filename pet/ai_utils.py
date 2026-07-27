import openai
import json
import base64
import pet.utils
import cv2
from PIL import Image
import numpy as np
import io
from openai.types.chat import ChatCompletionMessageParam

config = pet.utils.loadConfig()
client = openai.OpenAI(
    base_url=config['llm']['endpoint'], api_key=config['llm']['api_key'])


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


def identity() -> list[dict[str, str]]:
    return [{"role": "system", "content": ""}]


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
