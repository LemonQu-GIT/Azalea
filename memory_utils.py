import traceback
import json
import pet.utils
import pet.ai_utils
from datetime import datetime
from openai.types.chat import ChatCompletionMessageParam

config = pet.utils.loadConfig()


def generate_memories(userInput: str, llmInput: str | None, messages: list[ChatCompletionMessageParam], max_len=15) -> list[ChatCompletionMessageParam]:
    mem_sys_prompt = '''你是一个管理记忆的AI助手，你需要从用户对话中提取长期有效的信息。
    应该保存：
    - 普遍记忆
    - 用户偏好、爱好
    - 用户身份
    - 重要经历

    不要保存：
    - 临时问题
    - 一次性请求
    - 普通闲聊

    我会向你提供用户和AI模型的对话内容，你需要从中提取有价值的记忆。
    输出JSON列表。格式如下：
    [{
        "type": "", // 可以是 fact, preference, identity, experience
        "content": "", // 记忆内容
        "importance": 1, // 重要性，1-10
    }]
    若你觉得没有需要记忆的内容，你可以返回空列表[]。
    你直接输出JSON即可，不需要任何额外的解释或文本，也不需要使用markdown代码块或是用```json标记。'''
    if len(messages) > max_len:
        messages = messages[-max_len:]
    if not messages:
        messages = [{"role": "system", "content": mem_sys_prompt}]
    if messages[0]['role'] != 'system':
        messages.insert(0, {"role": "system", "content": mem_sys_prompt})
    messages.append(
        {"role": "user", "content": f"用户输入：{userInput}\nAI回复：{llmInput}"})
    mem_agent_reply = pet.ai_utils.generate_response(
        messages, reasoning_effort="none")
    if mem_agent_reply:
        mem_agent_json = pet.ai_utils.format_response(mem_agent_reply)
        if mem_agent_json and isinstance(mem_agent_json, list):
            save_memories(mem_agent_json)
            messages.append(
                {"role": "assistant", "content": mem_agent_reply})
    return messages


def save_memories(memories: list[dict]) -> None:
    with open("./memory/memory.json", "r", encoding="utf-8") as f:
        existing_memories: list[dict] = json.load(f)
    parsed = []
    for mem in memories:
        if "type" in mem and "content" in mem and "importance" in mem:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pmem = {
                "type": mem["type"],
                "content": mem["content"],
                "importance": mem["importance"],
                "created": date,
                "last_used": date,
                "times_used": 0
            }
            parsed.append(pmem)
    existing_memories.extend(parsed)
    with open("./memory/memory.json", "w", encoding="utf-8") as f:
        json.dump(existing_memories, f, ensure_ascii=False, indent=4)


def main():
    chat_messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": "你是一个乐于助人的AI助手。"}
    ]
    mem_messages: list[ChatCompletionMessageParam] = []
    while True:
        try:
            user_input = input("\n>>> ").strip()
            if not user_input:
                continue

            chat_messages.append({"role": "user", "content": user_input})
            assistant_reply = pet.ai_utils.generate_response(chat_messages)
            if assistant_reply:
                chat_messages.append(
                    {"role": "assistant", "content": assistant_reply})

            print(f"<<< {assistant_reply}")
            mem_messages = generate_memories(
                user_input, assistant_reply, mem_messages)

        except Exception as e:
            traceback.print_exc()
            break


if __name__ == "__main__":
    main()
