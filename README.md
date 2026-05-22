# AIRP-Pi

基于 [Pi Coding Agent](https://github.com/badlogic/pi-mono) 的沉浸式 RP（角色扮演）引擎。

AI 不只是生成文本——它**就是**引擎本身：管理状态、驱动叙事、维护记忆、执行质检，全程自动化。

## 特性

- **三大管线架构**：导入管线 → AI 创作 → 交付管线，每轮自动编排
- **多卡管理**：支持多角色卡切换，浏览器拖拽导入 PNG/JSON
- **MVU 变量系统**：JSONPatch 驱动的游戏状态追踪（情感、关系、属性）
- **世界书匹配**：关键词 + 变量条件触发，动态注入上下文
- **字数门禁**：80% 阈值自动重试，确保输出质量
- **跨会话记忆**：自动摘要 + 分层记忆（project / reference / feedback）
- **剧情规划**：五幕结构 + 价值逆转 + 信息螺旋释放
- **NovelAI 生图**：`[img: tags]` 标签自动触发生图
- **Web 前端**：实时显示叙事内容、状态面板、选项芯片
- **一键启动**：双击运行，浏览器自动打开，无需 CLI 操作

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 20+
- API Key（DeepSeek / Anthropic / OpenAI / OpenRouter 任选）

### 安装

```bash
git clone https://github.com/你的用户名/AIRP-Pi.git
cd AIRP-Pi
```

Windows 用户双击 `setup.bat`，或手动执行：

```bash
npm install
cd skills && npm install && cd ..
```

### 启动

双击 `start-rp.bat`，或：

```bash
python launcher.py
```

首次启动会自动打开浏览器设置页面，填入 API Key 后保存即可。

### 导入角色卡

两种方式：
1. **拖拽导入**：将 PNG 角色卡文件直接拖入浏览器页面
2. **手动放置**：将角色卡文件夹放入 `角色卡/` 目录

支持的格式：
- SillyTavern V2 PNG（嵌入 metadata）
- Character JSON
- 世界书 JSON
- 小说 TXT（作为参考素材）

## 架构

```
AIRP-Pi/
├── launcher.py          # 一键启动编排器
├── package.json         # Pi Agent 本地依赖
├── config.json          # 运行时配置（API Key，自动生成）
├── CLAUDE.md            # AI 引擎核心规则（Pi 自动加载）
├── STORY.md             # 叙事理论框架
├── .pi/
│   ├── settings.json    # Pi 配置（模型、权限）
│   └── skills/
│       └── rp.md        # /rp 技能定义
├── skills/
│   ├── server.py        # 桥接服务器（HTTP API + 前端）
│   ├── handler.py       # 回合交付（解析标签 → 更新状态）
│   ├── import_prepare.py    # 导入管线
│   ├── round_prepare.py     # 回合预处理（收集上下文）
│   ├── round_deliver.py     # 回合后处理（质检 + 交付）
│   ├── import_card.py       # 角色卡解析器
│   ├── card_store.py        # 多卡管理
│   ├── match_worldbook.py   # 世界书匹配引擎
│   ├── mvu_engine.py        # MVU 变量引擎
│   ├── mvu_server.js        # MVU Node 服务（Zod 验证）
│   ├── write_memory.py      # 记忆更新
│   ├── token_stats.py       # Token 统计
│   └── styles/              # 前端资源
│       ├── index.html       # 主界面
│       ├── setup.html       # 首次配置页
│       └── profiles/        # 文风配置
├── scripts/
│   ├── novelai-generate.py  # NovelAI 生图
│   └── extract-img.py       # 图片标签提取
├── 角色卡/                   # 角色卡存储目录
├── setup.bat                # 环境安装
└── start-rp.bat             # 一键启动
```

## 工作流程

```
用户输入（浏览器）
    ↓
server.py 写入 input.txt + .pending
    ↓
Pi Agent 检测到输入（长轮询）
    ↓
round_prepare.py → 收集上下文 → round_context.txt
    ↓
AI 生成叙事（读取 round_context.txt）
    ↓
round_deliver.py → 字数门禁 → handler.py 交付 → 记忆更新
    ↓
前端实时显示
```

## 配置

### 模型切换

首次在浏览器设置页配置，保存到 `config.json`。支持：

| Provider | 推荐模型 |
|----------|----------|
| DeepSeek | deepseek-v4-pro / deepseek-v4-flash |
| Anthropic | claude-sonnet-4-6-20250514 |
| OpenAI | gpt-4o |
| OpenRouter | deepseek/deepseek-r1 |

### 文风配置

在 `skills/styles/profiles/` 下创建 `.md` 文件即可添加自定义文风。前端设置面板可切换。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/status | 系统状态 |
| GET | /api/config | 读取配置（Key 脱敏） |
| POST | /api/config | 保存配置 |
| POST | /api/submit | 提交用户输入 |
| POST | /api/import-card | 上传角色卡文件 |
| GET | /api/cards | 列出所有角色卡 |
| POST | /api/play | 切换当前角色卡 |
| GET | /api/wait_pending | 长轮询等待输入（300s） |
| GET | /api/pending | 检查是否有待处理输入 |
| GET | /api/done | 标记输入已处理 |

## 技术栈

- **AI 运行时**：Pi Coding Agent（本地 npm 依赖）
- **后端**：Python 3.10+（纯标准库，无额外 pip 依赖）
- **变量引擎**：Node.js + Zod（JSON Schema 验证）
- **前端**：原生 HTML/JS + jQuery + Toastr
- **通信**：HTTP 长轮询（无 WebSocket 依赖）

## License

MIT
