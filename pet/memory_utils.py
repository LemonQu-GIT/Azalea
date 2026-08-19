import os
import json
import uuid
from datetime import datetime

import numpy as np
try:
    import faiss
except ImportError:
    faiss = None
import requests
from openai.types.chat import ChatCompletionMessageParam

import pet.ai_utils
import pet.utils
from pet.i18n import t

config = pet.ai_utils.config

if faiss is None:
    pet.utils.log(
        "faiss 未安装（缺少 faiss-cpu 可选依赖），长期记忆的语义检索功能已禁用，仅保留基础记忆存储。",
        "WARNING", save=False)


class MemoryManager:
    def __init__(self, path="./memory"):
        self.path = path
        self.embedding_endpoint = config["llm"].get("embedding_model_endpoint")
        self.embedding_api_key = config["llm"].get("embedding_model_key", "")

        self.memory_file = os.path.join(path, "memory.json")
        self.index_file = os.path.join(path, "index.faiss")
        self.id_map_file = os.path.join(path, "id_map.json")

        self.memories = {}
        self.id_map = []
        self.index = None

        self.llmMaxLen = 15
        self.chat_messages: list[ChatCompletionMessageParam] = []

        os.makedirs(path, exist_ok=True)
        self.load()

    def get_embedding(self, text):
        headers = {
            "Content-Type": "application/json",
        }
        if self.embedding_api_key:
            headers["Authorization"] = f"Bearer {self.embedding_api_key}"

        payload = {
            "input": text,
            "model": "bge-small-zh-v1.5",
        }

        try:
            response = requests.post(  # type: ignore
                self.embedding_endpoint,
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            if "data" in result and len(result["data"]) > 0:
                return np.array(result["data"][0]["embedding"], dtype="float32")
            else:
                raise ValueError("Empty embedding response")
        except Exception as e:
            pet.utils.log(
                f"Embedding API call failed: {e}", "ERROR", save=False)
            raise

    def load(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf8") as f:
                self.memories = json.load(f)
        else:
            self.memories = {}

        if os.path.exists(self.id_map_file):
            with open(self.id_map_file, "r", encoding="utf8") as f:
                self.id_map = json.load(f)
        else:
            self.id_map = []

        if faiss is None:
            self.index = None
        elif os.path.exists(self.index_file):
            self.index = faiss.read_index(self.index_file)

            if self.index.ntotal != len(self.id_map):
                pet.utils.log(
                    "FAISS index mismatch, rebuilding...", "INFO", save=False)
                self.rebuild_index()

        elif self.memories:
            self.rebuild_index()

    def get_embedding_text(self, memory):
        return f"""
类型：{memory['type']}
重要程度：{memory.get('importance', 5)}

用户长期信息：
{memory['content']}
"""

    def rebuild_index(self):
        if faiss is None:
            self.index = None
            return

        self.id_map = []
        vectors = []

        try:
            for memory_id, memory in self.memories.items():
                vector = self.get_embedding(self.get_embedding_text(memory))
                vectors.append(vector)
                self.id_map.append(memory_id)
        except Exception:
            # Embedding API 不可用：跳过索引重建（不能让启动/决策因此崩溃）
            self.id_map = []
            self.index = None
            return

        if not vectors:
            self.index = None
            return

        vectors = np.array(vectors, dtype="float32")

        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)

        self.save()

    def add_memory(self, content, type="fact", importance=5):
        memory_id = str(uuid.uuid4())

        memory = {
            "id": memory_id,
            "type": type,
            "content": content,
            "importance": importance,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_used": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "times_used": 0
        }

        if faiss is None:
            self.memories[memory_id] = memory
            self.save()
            return memory_id

        try:
            vector = self.get_embedding(self.get_embedding_text(memory))
        except Exception:
            # Embedding API 不可用时退化为仅存储（与 faiss 缺失同样的行为），
            # 不能让记忆功能拖垮整轮 AI 决策
            self.memories[memory_id] = memory
            self.save()
            return memory_id
        vector = np.array([vector], dtype="float32")

        if self.index is None:
            self.index = faiss.IndexFlatIP(vector.shape[1])

        self.index.add(vector)

        self.id_map.append(memory_id)
        self.memories[memory_id] = memory

        self.save()

        return memory_id

    def search(self, query, top_k=5, threshold=0.45):
        if self.index is None:
            return []

        query = f"""
你是AI桌宠的长期记忆检索模块。
请寻找能够帮助回答用户（老师）的问题的长期记忆。

用户问题：
{query}
"""

        try:
            vector = self.get_embedding(query)
        except Exception:
            # Embedding API 不可用：检索退化为空结果，不中断本轮决策
            return []
        vector = np.array([vector], dtype="float32")

        scores, ids = self.index.search(vector, top_k)

        result = []

        for score, index_id in zip(scores[0], ids[0]):
            if index_id == -1 or score < threshold:
                continue

            memory_uuid = self.id_map[index_id]

            if memory_uuid not in self.memories:
                continue

            memory = self.memories[memory_uuid]

            memory["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memory["times_used"] += 1

            result.append((float(score), memory))

        self.save()

        return result

    def delete_memory(self, memory_id):
        if memory_id in self.memories:
            del self.memories[memory_id]
            self.rebuild_index()

    def save(self):
        with open(self.memory_file, "w", encoding="utf8") as f:
            json.dump(self.memories, f, ensure_ascii=False, indent=2)

        with open(self.id_map_file, "w", encoding="utf8") as f:
            json.dump(self.id_map, f, ensure_ascii=False, indent=2)

        if self.index:
            faiss.write_index(self.index, self.index_file)

    def retrieve_for_chat(self, queries: list[str]):
        if not isinstance(queries, list):
            return []
        result = []
        all_memories = {}
        for q in queries:
            for score, memory in self.search(q):
                memory_id = memory["id"]

                if memory_id not in all_memories:
                    all_memories[memory_id] = (score, memory)
                else:
                    old_score, old_memory = all_memories[memory_id]
                    all_memories[memory_id] = (
                        max(old_score, score), old_memory)

        result = list(all_memories.values())
        result.sort(key=lambda x: x[0], reverse=True)

        return [memory for score, memory in result]

    def generate_memories(self, userInput: str, llmInput: str | None):
        mem_sys_prompt = t("""你是一个AI桌宠的长期记忆管理器。
你的任务是从用户和AI的对话中提取值得长期保存的信息。
注意：由于AI桌宠是《蔚蓝档案》中的角色，因此会把用户称作“老师”。因此“老师”实际是指用户本人。你可能需要把所有的“老师”换成“用户”以便长期记忆的保存。
应该保存：
- 用户身份信息
- 用户长期兴趣
- 用户习惯和偏好
- 用户长期项目
- 用户重要经历

不要保存：
- 一次性问题
- 临时状态
- 普通聊天
- 当前正在做的小事情

输出JSON列表：

[
 {
   "type":"fact|preference|identity|experience",
   "content":"一句完整描述",
   "importance":1-10
 }
]

如果没有值得保存的信息，返回[]。""")
        if len(self.chat_messages) > self.llmMaxLen:
            self.chat_messages = self.chat_messages[-self.llmMaxLen:]
        if not self.chat_messages or self.chat_messages[0]["role"] != "system":
            self.chat_messages.insert(
                0, {"role": "system", "content": mem_sys_prompt})
        self.chat_messages.append(
            {"role": "user", "content": f"用户输入：{userInput}\nAI回复：{llmInput}"})
        reply = pet.ai_utils.generate_response(
            self.chat_messages)

        if not reply:
            return []

        result = pet.ai_utils.format_response(reply)

        if isinstance(result, list):
            self.chat_messages.append({"role": "assistant", "content": reply})
            return result

        return []


if __name__ == "__main__":
    manager = MemoryManager()

    result = manager.retrieve_for_chat("用户在编写AI桌宠")

    print(json.dumps(result, ensure_ascii=False, indent=2))
