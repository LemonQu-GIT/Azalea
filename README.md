# Azalea Project

中文 | [日本語](README.ja.md)

> DesktopPet for all students in Kivotos

---

## 功能特性

### 对话与智能

- **大模型接入**：兼容 OpenAI API 格式
- **Tool Calling**：所有使用的 Tools 如下
  - `get_windows_list` — 获取当前所有可见窗口列表
  - `keyboard_input` — 模拟键盘输入
  - `cmd_run` — 执行系统命令（较？安全）
- **自适应对话频率**：用户长时间不回复时自动延长思考间隔
- **长期记忆**：对话上下文持久化保存，支持语义记忆检索

### 语音合成

详见 https://github.com/High-Logic/Genie-TTS

可使用 Genie-TTS 将 GPT-SoVITS 兼容的模型转换为 ONNX 模型

GPT-SoVITS Model by [**@SLNeil**](https://space.bilibili.com/523537077)

若希望生成的语音为日语，请在设置中将 TTS 语言设置为 `jp`

### API 接口

- FastAPI 提供 HTTP + WebSocket 接口
- 支持通过 API 控制模型的位置、旋转、缩放、动画播放
- 支持 `local` / `global` 两种旋转坐标系

---

## 环境要求

- Python **≥ 3.12**
- 支持 Windows 与 Linux（~~我没有经济实力使用 Mac~~）。Linux 推荐使用 X11；在 Wayland 下窗口交互相关功能会优雅降级
- Ollama 或 OpenAI 兼容的 API
- （可选）Genie-TTS 本地语音合成 API
- （可选）Embedding 本地词向量 API

---

## 快速开始

### 使用启动 / 部署脚本

```bash
python run_project.py
```

### 手动部署

#### 1. 克隆项目

```bash
git clone https://github.com/LemonQu-GIT/Azalea.git
cd Azalea
```

#### 2. 安装依赖 (uv)

* 若所有的 API (TTS, Embedding) 都在云端：

```bash
uv sync
```

* 若无 TTS, Embedding API，项目可以本地运行这两个 API

  项目不提供 LLM API 的本地运行，请自己使用 Ollama, OpenAI 等模型提供商

```bash
uv sync --extra local
```

#### 3. 配置文件

复制示例配置并按需要修改：

Windows：

```bash
copy configs\config.example.json configs\config.json
```

Linux：

```bash
cp configs/config.example.json configs/config.json
```

编辑 `configs\config.json`，至少填入 **LLM 配置**（endpoint、api_key、model）

界面语言可通过顶层的 `"language"` 字段设置（`"zh"` / `"ja"`），环境变量 `AZALEA_LANG` 可覆盖该配置

#### 4. 启动应用

主程序：

```bash
python main.py
```

若需启动 Embedding API：

```bash
python embedding_api.py
```

若需启动 TTS API：

```bash
python tts_api.py
```

启动后：

- 桌面会出现桌宠窗口
- 系统托盘出现 Azalea 图标，右键可打开设置或对话
- 默认 API 服务运行在 `http://127.0.0.1:8001`

---

## 使用指南

### 基本操作

| 操作                           | 说明                               |
| ------------------------------ | ---------------------------------- |
| **左键拖拽**             | 移动桌宠，松开后按物理规律扔出     |
| **头部区域右键按住滑动** | 摸头                               |
| **右键桌宠**             | 打开对话界面                       |
| **右键托盘图标 → 设置** | 打开设置界面（LLM / TTS / 主题等） |
| **右键托盘图标 → 退出** | 关闭应用                           |

## 安全说明

- `cmd_run` 工具内置危险命令黑名单（shutdown/rm/reg 等），请避免一切的提示词注入攻击
- 建议不要赋予不必要的系统权限，使用普通用户权限运行即可

### TODOs

详见 [TODO.md](./TODO.md)

---

## License

本项目仅供学习交流使用。项目中的 3D 模型、贴图等素材版权归原作者所有。
