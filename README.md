<div align="center">

# MindMatrix 智谱矩阵 (hu-chenfeng.skill v2.0)

> *「普通人买东西就选大品牌——不会踩坑；普通人学习系统就选全集成——开箱即用。」*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.100+-blue.svg)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57.svg)](https://sqlite.org)
[![FastEmbed](https://img.shields.io/badge/RAG-FastEmbed-green.svg)](https://github.com/qdrant/fastembed)

<br>

**MindMatrix 是一款基于 FastAPI + SQLite + RAG 打造的多角色数字分身交互系统。**<br>
不仅集成了户晨风的“消费现实主义”视角，还支持风哥、马斯克、川普等多角色切换。<br>
系统已深度整合前端界面、充值邀请码系统、多账号计费以及本地离线向量库。

[在线预览](#新版界面效果) · [离线向量库整合](#1-离线向量库整合) · [注册邀请码系统](#2-邀请码注册系统) · [快速安装与运行](#快速开始)

</div>

---

## 新版界面效果

本次升级重构了前端与后端，打造了极具科技感的毛玻璃（Glassmorphism）响应式聊天界面，支持：
* **多角色自由切换**：侧边栏支持一键切换角色（户晨风、风哥、Elon Musk、川普等）。
* **拟真交互体验**：自动提取聊天上下文，进行高频提问交互。
* **语音合成 (TTS) 与识别 (ASR)**：深度集成 MiniMax 拟真声音克隆与 Groq Whisper 语音流。
* **个人账户与充值**：完善的额度计费、邀请码注册与余额管理。

<div align="center">
  <img width="50%" alt="MindMatrix Chat Interface" src="https://github.com/user-attachments/assets/c15cf1ef-b188-4a21-bc2f-7a3ee8cdab3e" />
</div>

---

## 核心整合亮点

### 1. 离线向量库整合 (免网打包上传 Git)

为了解决云端部署或离线环境下因网络无法拉取模型的问题，项目实现了 **bge-small 向量模型本地闭环整合**：
* **模型集成**：已将 `BAAI/bge-small-zh-v1.5` 的所有 ONNX 权重 and Tokenizer 文件（`fast-bge-small-zh-v1.5.tar.gz` 约 54MB）打包置于项目根目录中。
* **一键提取**：解压至项目根目录的 `models/` 文件夹下即可运行。
* **离线无网依赖**：在 `app/rag.py` 等加载模块中，通过指定 `cache_dir` 或 `FASTEMBED_CACHE_PATH` 环境变量指向本地 `models/`，系统将**完全停止**向 Hugging Face 或公网下载模型，彻底消除网络堵塞风险，打包成 Zip/Tar 极速分发与部署。

### 2. 邀请码注册系统 (防刷充值门槛)

在尚未接入第三方聚合支付接口的过渡阶段，系统专门设计了**指定充值邀请码注册机制**，以防范任意注册与接口盗刷：
* **派发人 (Distributor) 追踪**：邀请码表（`invite_codes`）包含派发人字段，显示由哪位销售/管理员派发该码，方便对账。
* **一次性失效 (Single-Use)**：每个邀请码有且仅能被使用一次，注册时即刻绑定用户，防止二次扩散。
* **本地安全落库**：通过内置 SQLite 数据库（`data/app.db`）管理用户及邀请码记录，安全性极高。

---

## 数据库架构设计

系统采用 SQLite 作为轻量化持久介质，包含四张核心表：

```mermaid
erDiagram
    users {
        int id PK
        string username UNIQUE
        string password_hash
        decimal balance
        string invite_code
    }
    invite_codes {
        int id PK
        string code UNIQUE
        string distributor
        boolean is_used
        string used_by
        datetime used_at
        datetime created_at
    }
    conversations {
        int id PK
        int user_id FK
        string title
        string persona_id
        datetime created_at
    }
    messages {
        int id PK
        int conversation_id FK
        string role
        text content
        string audio_url
        datetime created_at
    }
    users ||--o{ conversations : "owns"
    conversations ||--o{ messages : "contains"
```

---

## 快速开始

### 第一步：克隆代码与解压模型

```bash
# 1. 克隆仓库
git clone https://github.com/jiaweisun699999-prog/hu-chenfeng-skill.git
cd hu-chenfeng-skill

# 2. 解压项目自带 of 离线向量模型（Windows 下可直接使用解压软件）
# 解压后目录结构应为：hu-chenfeng-skill/models/fast-bge-small-zh-v1.5/
tar -zxvf fast-bge-small-zh-v1.5.tar.gz -C .
```

### 第二步：创建虚拟环境并安装依赖

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv

# Windows 激活命令：
.venv\Scripts\activate
# Linux/macOS 激活命令：
source .venv/bin/activate

# 2. 安装项目依赖
pip install -r requirements.txt
```

### 第三步：配置环境变量

复制项目根目录下的 `.env.example` 并重命名为 `.env`：

```bash
# Windows 用 copy，Linux 用 cp
copy .env.example .env
```

打开 `.env` 文件并进行如下配置：

```env
# ── 大模型API配置 (支持 Ollama 和 DeepSeek) ──────────────────
# 1. 使用 DeepSeek 云端 API (默认)：
OLLAMA_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=sk-your-real-key-here
LLM_MODEL_NAME=deepseek-chat

# 2. 或者使用 Ollama 本地模型 (如 deepseek-r1:8b)：
# OLLAMA_BASE_URL=http://localhost:11434/v1
# LLM_MODEL_NAME=deepseek-r1:8b

# ── 离线向量库路径配置 (锁定本地 models 目录，拒绝网络拉取) ──
FASTEMBED_CACHE_PATH=models

# ── 管理员后台密钥 ───────────────────────────────────────────
ADMIN_SECRET=your_admin_secret_key_here
```

### 第四步：初始化数据库与生成邀请码

1. **数据库迁移**：运行脚本添加邀请码模块所需要的表及字段：
   ```bash
   python migrate_add_invite.py
   ```
2. **生成邀请码 (管理后台专用)**：
   运行以下命令生成用于新用户注册的邀请码：
   ```bash
   # 输入你的管理员密钥、派发人姓名以及需要生成的邀请码数量
   # 例如：生成 5 个派发人为 "张三" 的一次性充值邀请码
   python -c "import sqlite3; conn=sqlite3.connect('data/app.db'); cur=conn.cursor(); [cur.execute('INSERT INTO invite_codes (code, distributor) VALUES (?, ?)', (f'VIP-{i}-'+str(hash(i))[-6:], '张三')) for i in range(5)]; conn.commit(); conn.close(); print('生成成功！')"
   ```

### 第五步：运行服务

```bash
# 启动 FastAPI + Uvicorn 开发者服务器
python -m uvicorn app.main:app --reload
```

打开浏览器访问 [http://127.0.0.1:8000](http://127.0.0.1:8000) 即可开始进行注册与对话！

---

## 角色注册表与向量索引重构

如果你需要更新特定角色的原始知识库（Markdown 文件），可以直接编辑对应的 `personas/<persona_id>/references/` 下的文件，然后重新运行索引构建：

```bash
# 为指定角色（例如：户晨风）重新构建向量检索索引
python tools/build_index.py personas/hu-chenfeng
```

---

## 许可证

本项目基于 [MIT License](LICENSE) 协议发布，完全开源，可自由修改、学习或用于个人二开项目。

<div align="center">

**语录** 告诉你他说过什么。<br>
**MindMatrix** 帮你用他们的视角审视世界。

<br>

MIT License © [janlay](https://github.com/janlay)

</div>
