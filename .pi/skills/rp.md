---
name: rp
description: 标准化启动话本RP流程（新卡开局 / 老卡续玩）
---

在当前目录下启动话本RP流程。

## 重要：路径引号规则

所有 bash 命令中的卡片文件夹路径**必须用双引号包裹**，因为文件夹名可能含空格和括号：
- 正确：`python skills/import_prepare.py "角色卡/1 (2)" .`
- 错误：`python skills/import_prepare.py 角色卡/1 (2) .`（括号会被 bash 解析为子 shell）

## 重要：bash 工具不要设置 timeout

长轮询 curl 命令（`--max-time 310`）会阻塞约 5 分钟。调用 bash 工具时**不要设置 timeout 参数**，让命令自然完成。

## 第一步：扫描当前目录

查找素材文件（PNG角色卡、JSON世界书、TXT小说）：
- Glob 搜索 `角色卡/*/` 下的 `*.png`, `*.json`, `*.txt`
- 读取 `current-card.txt` 确定当前卡
- 检查当前卡的 `chat_log.json` 和 `memory/` 是否存在

## 第二步：根据扫描结果执行

### 情况 A — 有素材，无 chat_log.json（新卡开局）

按 CLAUDE.md「自动启动流程」步骤完整执行：

1. 执行导入管线（自动清理残留进程+写入 card_path+state.js+response.txt）：
   `python skills/import_prepare.py "角色卡/<卡名>" .`
2. 启动桥接服务器：`python skills/start_server.py .`
3. 读取 `skills/styles/import_context.txt` 获取汇总上下文
4. 检查 `skills/styles/response.txt` — 若已预填则直接交付，否则自行生成开局写入
5. 执行：`python skills/handler.py "角色卡/<卡名>" --opening`
6. 进入输入监听循环（见下方）
7. 告知用户：「前端已就绪，打开 http://localhost:8765」

### 情况 B — 有 chat_log.json + memory/（老卡续玩）

1. 启动桥接服务器：`python skills/start_server.py .`
2. 读取 chat_log.json 最近 3 轮 + memory/project.md 重建上下文
3. 告知用户当前剧情进度
4. 进入输入监听循环

### 情况 C — 无任何素材文件

告知用户：
> 角色卡/ 目录下没有找到角色卡文件夹。
> 请放入包含 PNG 角色卡、JSON 世界书或 TXT 小说的文件夹后重新执行 `/rp`。

## 输入监听循环

Pi 中使用 bash 长轮询替代 Claude Code 的 ScheduleWakeup。
**调用 bash 工具时不要设置 timeout 参数**，curl 的 `--max-time 310` 会自行控制超时：

```bash
while true; do
  result=$(curl -s --max-time 310 http://localhost:8765/api/wait_pending)
  if echo "$result" | python -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('pending') else 1)" 2>/dev/null; then
    break
  fi
done
```

检测到输入后：
1. 执行回合预处理：`python skills/round_prepare.py "角色卡/<卡名>" .`
2. 读取 `skills/styles/round_context.txt`
3. AI 生成叙事 → 写入 `skills/styles/response.txt`
4. 执行回合后处理：`python skills/round_deliver.py "角色卡/<卡名>" .`
5. 若返回 `action: retry` → 重新生成（最多 3 次）
6. 若返回 `action: done` → 回到监听循环等待下一轮

## 多卡切换

用户说「切换到XX」「换个卡」时：
1. 调用 `/api/cards` 列出可用卡
2. 调用 `/api/play` 切换
3. 重新执行导入管线
