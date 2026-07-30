import os
import json
import uuid
from datetime import datetime

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from openai.types.chat import ChatCompletionMessageParam

import pet.ai_utils

config = pet.ai_utils.config


class MemoryManager:
    def __init__(self, path="./memory"):
        self.path = path
        self.model = SentenceTransformer(config["llm"]["embedding_model"])

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

        if os.path.exists(self.index_file):
            self.index = faiss.read_index(self.index_file)

            if self.index.ntotal != len(self.id_map):
                print("FAISS index mismatch, rebuilding...")
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
        self.id_map = []
        vectors = []

        for memory_id, memory in self.memories.items():
            vector = self.model.encode(self.get_embedding_text(
                memory), normalize_embeddings=True)
            vectors.append(vector)
            self.id_map.append(memory_id)

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

        vector = self.model.encode(self.get_embedding_text(
            memory), normalize_embeddings=True)
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

        vector = self.model.encode(query, normalize_embeddings=True)
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

    def retrieve_for_chat(self, user_input):
        router_prompt = """你是AI桌宠的记忆检索模块。
根据AI大脑当前输入，判断回答时需要哪些长期用户信息。
注意：由于AI桌宠是《蔚蓝档案》中的角色，因此会把用户称作“老师”。因此“老师”实际是指用户本人。你可能需要把所有的“老师”换成“用户”。
只输出JSON列表。
例如：
AI大脑：
帮我写一个Python程序
输出：["用户编程经验", "用户使用的技术栈"]
如果不需要记忆：[]
不要输出解释。"""
        messages = [
            {
                "role": "system",
                "content": router_prompt
            },
            {
                "role": "user",
                "content": user_input
            }
        ]

        reply = pet.ai_utils.generate_response(
            messages)
        if not reply:
            return []
        queries = pet.ai_utils.format_response(reply)
        print(f"queries: {queries}")
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
        mem_sys_prompt = """你是一个AI桌宠的长期记忆管理器。
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

如果没有值得保存的信息，返回[]。"""
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
