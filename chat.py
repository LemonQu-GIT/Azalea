import pyautogui
import time
import json
from datetime import datetime
from openai.types.chat import ChatCompletionMessageParam

import pet.utils
import pet.ai_utils
import pet.memory_utils
import pet.tool_calling
import pet.ai

chat_sys_prompt = pet.ai_utils.chat_sys_prompt
control_sys_prompt = pet.ai_utils.control_sys_prompt

control_messages: list[ChatCompletionMessageParam] = [
    {"role": "system", "content": control_sys_prompt}]
chat_messages: list[ChatCompletionMessageParam] = [
    {"role": "system", "content": chat_sys_prompt}]

last_activity_time = time.time()
manager = pet.memory_utils.MemoryManager()
SLEEP_TIME = 5
schedule: list[dict] = []
schedule_run = None

while True:
    print("\n--- Next Loop ---")
    screenshot = pyautogui.screenshot()
    screenshot_base64 = pet.ai_utils.img2base64(screenshot)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_time = time.time()
    if schedule_run:
        print(
            f"[Schedule Triggered] 计划触发: {schedule_run['content']} (计划时间: {datetime.fromtimestamp(schedule_run['time']).strftime('%Y-%m-%d %H:%M:%S')})")
        assembled_content = f"计划触发: {schedule_run['content']} (计划时间: {datetime.fromtimestamp(schedule_run['time']).strftime('%Y-%m-%d %H:%M:%S')})"
        schedule.remove(schedule_run)
        schedule_run = None
    else:
        assembled_content = f"现在是 {now}，距离桌宠上一次做出行为过去了{now_time - last_activity_time:.2f}秒。请根据截屏判断桌宠的行为。"
    control_messages.append({
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": assembled_content
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{screenshot_base64}"
                }
            }
        ]
    })

    control_reply = pet.tool_calling.run_llm_with_tools(control_messages)
    pet.ai_utils.remove_image(control_messages)
    control_messages = pet.ai_utils.truncate_context(
        control_messages, sys_prompt=control_sys_prompt, max_recent=10)

    if control_reply:
        last_activity_time = time.time()
        control_reply_json = pet.ai_utils.format_response(control_reply)

        if control_reply_json and isinstance(control_reply_json, list):
            for task in control_reply_json:
                print(f"Task executed: {task}")

                if task.get("action") == "chat":
                    reason = task.get("reason", "")
                    retrieved_mems = manager.retrieve_for_chat(reason)
                    if retrieved_mems:
                        mem_text = "\n".join(
                            [f"- {m['content']}" for m in retrieved_mems])
                        mem_sys_prompt = {"role": "system",
                                          "content": f"[相关历史记忆]:\n{mem_text}"}
                        chat_messages.append(mem_sys_prompt)  # type:ignore
                    chat_prompt = {"role": "user", "content": [
                        {
                            "type": "text",
                            "text": f"大脑指令对话原因：{reason}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{pet.ai_utils.img2base64(pyautogui.screenshot())}"
                            }
                        }
                    ]}
                    chat_messages.append(chat_prompt)  # type:ignore
                    chat_reply = pet.tool_calling.run_llm_with_tools(
                        chat_messages)  # type:ignore
                    pet.ai_utils.remove_image(
                        chat_messages)

                    chat_messages = pet.ai_utils.truncate_context(
                        chat_messages, sys_prompt=chat_sys_prompt, max_recent=10)

                    if chat_reply:
                        print(f"<<< {chat_reply}")
                        new_memories = manager.generate_memories(
                            reason, chat_reply)
                        for mem in new_memories:
                            if isinstance(mem, dict) and "content" in mem:
                                manager.add_memory(
                                    content=mem["content"],
                                    type=mem.get("type", "fact"),
                                    importance=mem.get("importance", 5)
                                )
                                print(
                                    f"[Memory Saved] 成功记录新的长期记忆: {mem['content']}")

                elif task.get("action") == "walk":
                    distance = task.get("distance")
                    if distance is not None:
                        pet.ai.walk(distance=int(distance))
                        last_activity_time = now_time
                        print(f"[Action] 桌宠行走: 距离={distance}")
                elif task.get("action") == "walk_to":
                    x = task.get("x")
                    if x is not None:
                        pet.ai.walk_to(x=int(x))
                        last_activity_time = now_time
                        print(f"[Action] 桌宠走到x坐标: x={x}")
                elif task.get("action") == "climb_window":
                    hwnd = task.get("hwnd")
                    if hwnd:
                        pet.ai.climb_window(int(hwnd))
                        last_activity_time = now_time
                        print(f"[Action] 桌宠爬窗口: hwnd={hwnd}")
                elif task.get("action") == "jump_on_window":
                    hwnd = task.get("hwnd")
                    if hwnd:
                        pet.ai.jump_on_window(int(hwnd))
                        last_activity_time = now_time
                        print(f"[Action] 桌宠跳到窗口上: hwnd={hwnd}")
                elif task.get("action") == "jump_into_window":
                    hwnd = task.get("hwnd")
                    if hwnd:
                        pet.ai.jump_into_window(int(hwnd))
                        last_activity_time = now_time
                        print(f"[Action] 桌宠跳入窗口: hwnd={hwnd}")
                elif task.get("action") == "jump":
                    height = int(task.get("height", 95))
                    times = int(task.get("times", 1))
                    pet.ai.jump(height=height, times=times)
                    last_activity_time = now_time
                    print(f"[Action] 桌宠原地跳跃: 高度={height} 次数={times}")
                elif task.get("action") == "schedule":
                    time_str = task.get("time")
                    content = task.get("content")
                    parse_time = pet.ai_utils.parse_time(
                        int(now_time), time_str)
                    if time_str and content:
                        schedule.append(
                            {"time": parse_time, "content": content})
                        print(
                            f"[Schedule Added] 成功添加计划: {time_str} - {content}")

    print("End loop")

    for i in range(SLEEP_TIME):
        now_time = time.time()
        for task in schedule:
            if now_time >= task["time"]:
                schedule_run = task
                break
        time.sleep(1)
