import asyncio
import time
import json
import functools
import traceback
import pyautogui
from datetime import datetime
from openai.types.chat import ChatCompletionMessageParam

import pet.utils
import pet.ai_utils
import pet.memory_utils
import pet.tool_calling
from pet.ai_utils import Actions

_active_window = None
config = pet.utils.loadConfig()

chat_sys_prompt = pet.ai_utils.chat_sys_prompt
control_sys_prompt = pet.ai_utils.control_sys_prompt


def _to_thread_kw(func, *args, **kwargs):
    return asyncio.to_thread(functools.partial(func, *args, **kwargs))


def register_active_window(window):
    global _active_window
    _active_window = window


def unregister_active_window():
    global _active_window
    _active_window = None


def _get_user_message_nowait() -> str | None:
    try:
        import pet.server as _srv
        return _srv.user_message_queue.get_nowait()
    except Exception:
        return None


def _get_head_pat_nowait() -> bool:
    try:
        import pet.server as _srv
        _srv.head_pat_queue.get_nowait()
        return True
    except Exception:
        return False


async def _push_ai_reply(reply: str):
    try:
        import pet.server as _srv
        _srv.ai_reply_queue.put_nowait(str(reply))
    except Exception:
        pass


async def ai_brain_core(action: Actions | None = None):
    if action is None:
        action = Actions(_active_window)

    fcm = await _to_thread_kw(pet.ai_utils.load_context, "control_context")
    if fcm:
        control_messages: list[ChatCompletionMessageParam] = fcm
    else:
        control_messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": control_sys_prompt}]
        await _to_thread_kw(pet.ai_utils.save_context, control_messages, "control_context")

    fcm_chat = await _to_thread_kw(pet.ai_utils.load_context, "chat_context")
    if fcm_chat:
        chat_messages: list[ChatCompletionMessageParam] = fcm_chat
    else:
        chat_messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": chat_sys_prompt}]
        await _to_thread_kw(pet.ai_utils.save_context, chat_messages, "chat_context")

    last_activity_time = time.time()

    manager = await asyncio.to_thread(pet.memory_utils.MemoryManager)

    SLEEP_TIME = 10
    schedule: list[dict] = []
    schedule_run = None

    consecutive_failures = 0
    pending_user_msg: str | None = None
    pending_head_pat: bool = False

    while True:
        this_round_user_msg: str | None = pending_user_msg
        pending_user_msg = None
        this_round_head_pat: bool = bool(pending_head_pat)
        pending_head_pat = False

        if this_round_user_msg is None:
            this_round_user_msg = _get_user_message_nowait()
        if not this_round_head_pat:
            this_round_head_pat = _get_head_pat_nowait()

        user_triggered = this_round_user_msg is not None
        head_pat_triggered = bool(this_round_head_pat)

        try:
            print("\n--- Next Loop ---" +
                  (" [USER MESSAGE TRIGGERED]" if user_triggered else "") +
                  (" [HEAD PAT TRIGGERED]" if head_pat_triggered else ""))
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now_time = time.time()

            screenshot = await asyncio.to_thread(pyautogui.screenshot)
            screenshot_base64 = pet.ai_utils.img2base64(screenshot)

            # ========= 优先级：用户聊天 > 摸头 > 计划触发 > 常规 idle =========
            # 全部统一进入 control_reply 大脑决策，不再绕过大脑
            if user_triggered and this_round_user_msg:
                user_text = this_round_user_msg
                print(f"[User Chat] {user_text}")
                assembled_content = f"现在是 {now}。用户主动对桌宠发消息，消息内容为：\n'''{user_text}'''\n请根据截屏判断桌宠的行为。"
                schedule_run = None

            elif head_pat_triggered:
                print(f"[Head Pat] 用户摸了摸桌宠的头。")
                assembled_content = f"现在是 {now}。用户摸了摸桌宠的头。请根据截屏判断桌宠的行为。"
                schedule_run = None

            elif schedule_run:
                print(
                    f"[Schedule Triggered] 计划触发: {schedule_run['content']} (计划时间: "
                    f"{datetime.fromtimestamp(schedule_run['time']).strftime('%Y-%m-%d %H:%M:%S')})"
                )
                assembled_content = f"计划触发: {schedule_run['content']} (计划时间: {datetime.fromtimestamp(schedule_run['time']).strftime('%Y-%m-%d %H:%M:%S')})"
                schedule.remove(schedule_run)
                schedule_run = None
            else:
                assembled_content = f"现在是 {now}，距离桌宠上一次做出行为过去了{now_time - last_activity_time:.2f}秒。请根据截屏判断桌宠的行为。"

            control_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": assembled_content},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{screenshot_base64}"}},
                ],
            })

            control_reply = str(await _to_thread_kw(
                pet.tool_calling.run_llm_with_tools, control_messages
            ))
            pet.ai_utils.remove_image(control_messages)
            control_messages = pet.ai_utils.truncate_context(
                control_messages, sys_prompt=control_sys_prompt, max_recent=15
            )

            if control_reply:
                last_activity_time = time.time()
                control_reply_json = pet.ai_utils.format_response(
                    control_reply)

                if control_reply_json and isinstance(control_reply_json, list):
                    for task in control_reply_json:
                        print(f"Task executed: {task}")

                        if task.get("action") == "chat":
                            reason = task.get("reason", "")

                            retrieved_mems = await _to_thread_kw(
                                manager.retrieve_for_chat, reason
                            )
                            if retrieved_mems:
                                mem_text = "\n".join(
                                    f"- {m.get('content', '')}" for m in retrieved_mems)
                                mem_sys_prompt = {
                                    "role": "system",
                                    "content": f"[相关历史记忆]:\n{mem_text}",
                                }
                                chat_messages.append(
                                    mem_sys_prompt)  # type:ignore

                            chat_ss = await asyncio.to_thread(pyautogui.screenshot)
                            if user_triggered and this_round_user_msg:
                                chat_user_prompt_text = f"现在是:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}。用户主动给你发了消息：\n'''{this_round_user_msg}'''\n大脑给出的对话原因：{reason}"
                            elif head_pat_triggered:
                                chat_user_prompt_text = f"现在是:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}。用户摸了摸你的头。大脑给出的对话原因：{reason}"
                            else:
                                chat_user_prompt_text = f"现在是:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}。大脑指令对话原因：{reason}"

                            chat_prompt = {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": chat_user_prompt_text},
                                    {"type": "image_url",
                                     "image_url": {"url": f"data:image/jpeg;base64,{pet.ai_utils.img2base64(chat_ss)}"}},
                                ],
                            }
                            chat_messages.append(chat_prompt)  # type:ignore

                            chat_reply = await _to_thread_kw(
                                pet.tool_calling.run_llm_with_tools, chat_messages
                            )
                            pet.ai_utils.remove_image(chat_messages)
                            chat_messages = pet.ai_utils.truncate_context(
                                chat_messages, sys_prompt=chat_sys_prompt, max_recent=15
                            )

                            if chat_reply:
                                print(f"<<< {chat_reply}")
                                reply_text = str(chat_reply)
                                duration = max(10.0, len(reply_text) * 0.1)
                                await action.show_message(reply_text, duration=duration)
                                await _push_ai_reply(reply_text)
                                if user_triggered and this_round_user_msg:
                                    mem_for = this_round_user_msg
                                else:
                                    mem_for = reason
                                new_memories = await _to_thread_kw(
                                    manager.generate_memories, mem_for, chat_reply
                                )
                                if new_memories:
                                    for mem in new_memories:
                                        if isinstance(mem, dict):
                                            mem_content = mem.get("content")
                                            if mem_content is None:
                                                continue
                                            await _to_thread_kw(
                                                manager.add_memory,
                                                content=mem_content,
                                                type=mem.get("type", "fact"),
                                                importance=mem.get(
                                                    "importance", 5),
                                            )
                                            print(
                                                f"[Memory Saved] 成功记录新的长期记忆: {mem_content}"
                                            )
                        elif task.get("action") == "schedule":
                            time_str = task.get("time")
                            content = task.get("content")
                            parse_time = pet.ai_utils.parse_time(
                                int(now_time), time_str
                            )
                            if time_str and content:
                                schedule.append(
                                    {"time": parse_time, "content": content}
                                )
                                print(
                                    f"[Schedule Added] 成功添加计划: {time_str} - {content}"
                                )
                        elif task.get("action") == "walk":
                            distance = task.get("distance")
                            sit_after = task.get("sit", False)
                            if distance is not None:
                                last_activity_time = now_time
                                print(f"[Action] 桌宠行走: 距离={distance}")
                                await action.walk(int(distance), sit_after=sit_after)
                        elif task.get("action") == "walk_to":
                            x = task.get("x")
                            sit_after = task.get("sit", False)
                            if x is not None:
                                last_activity_time = now_time
                                print(f"[Action] 桌宠走到x坐标: x={x}")
                                await action.walk_to(int(x), sit_after=sit_after)
                        elif task.get("action") == "climb_window":
                            hwnd = task.get("hwnd")
                            sit_after = task.get("sit", False)
                            if hwnd:
                                last_activity_time = now_time
                                print(f"[Action] 桌宠爬窗口: hwnd={hwnd}")
                                await action.climb_window(int(hwnd), sit_after=sit_after)
                        elif task.get("action") == "jump_on_window":
                            hwnd = task.get("hwnd")
                            sit_after = task.get("sit", False)
                            if hwnd:
                                last_activity_time = now_time
                                print(f"[Action] 桌宠跳到窗口上: hwnd={hwnd}")
                                await action.jump_on_window(int(hwnd), sit_after=sit_after)
                        elif task.get("action") == "jump_into_window":
                            hwnd = task.get("hwnd")
                            sit_after = task.get("sit", False)
                            if hwnd:
                                last_activity_time = now_time
                                print(f"[Action] 桌宠跳入窗口: hwnd={hwnd}")
                                await action.jump_into_window(int(hwnd), sit_after=sit_after)
                        elif task.get("action") == "jump":
                            height = int(task.get("height", 95))
                            times = int(task.get("times", 1))
                            last_activity_time = now_time
                            print(
                                f"[Action] 桌宠原地跳跃: 高度={height} 次数={times}")
                            await action.jump(height=height, times=times)
                        elif task.get("action") == "stand":
                            last_activity_time = now_time
                            print(f"[Action] 桌宠站立")
                            await action.stand()
                        elif task.get("action") == "sit":
                            last_activity_time = now_time
                            print(f"[Action] 桌宠坐下")
                            await action.sit()

            await _to_thread_kw(pet.ai_utils.save_context, control_messages, "control_context")
            await _to_thread_kw(pet.ai_utils.save_context, chat_messages, "chat_context")

            print("--- End loop ---")
            consecutive_failures = 0

            pending_user_msg = _get_user_message_nowait()
            pending_head_pat = _get_head_pat_nowait()
            if pending_user_msg is not None or pending_head_pat:
                continue

        except Exception as exc:
            consecutive_failures += 1
            backoff = min(SLEEP_TIME * consecutive_failures, 60)
            err_header = f"[AI Brain Loop] 本轮执行异常 (连续失败 {consecutive_failures} 次, 将退避 {backoff}s 后继续): {type(exc).__name__}: {exc}"
            pet.utils.log(err_header + "\n" + traceback.format_exc(), "ERROR")
            pending_user_msg = _get_user_message_nowait()
            pending_head_pat = _get_head_pat_nowait()
            if pending_user_msg is not None or pending_head_pat:
                continue
            await asyncio.sleep(backoff)
            continue

        sleep_broken_by_user = False
        for _ in range(SLEEP_TIME):
            now_time = time.time()
            for task in schedule:
                if now_time >= task["time"]:
                    schedule_run = task
                    break
            pending_user_msg = _get_user_message_nowait()
            if pending_user_msg is not None:
                sleep_broken_by_user = True
                break

            if _get_head_pat_nowait():
                pending_head_pat = True
                sleep_broken_by_user = True
                break
            await asyncio.sleep(1)

        if sleep_broken_by_user:
            continue
        if pending_user_msg is None:
            pending_user_msg = _get_user_message_nowait()
        if not pending_head_pat:
            pending_head_pat = _get_head_pat_nowait()


async def ai_brain_loop():
    global _active_window

    crash_count = 0
    while True:
        try:
            action = Actions(_active_window)
            await asyncio.sleep(3)
            if config['llm']['enabled']:
                await ai_brain_core(action)
            else:
                pet.utils.log(
                    "[AI Brain Loop] LLM 未启用，跳过 AI 大脑核心执行", "INFO", save=False)
                while not config['llm']['enabled']:
                    await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            crash_count += 1
            backoff = min(5 * (2 ** min(crash_count, 5)), 60)
            header = f"[AI Brain Loop FATAL] AI 大脑核心崩溃 (第 {crash_count} 次), {backoff}s 后重启: {type(exc).__name__}: {exc}"
            pet.utils.log(header + "\n" +
                          traceback.format_exc(), "CRITICAL")
            await asyncio.sleep(backoff)
