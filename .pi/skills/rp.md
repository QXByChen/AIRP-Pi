---
name: rp
description: 标准化启动话本RP流程（新卡开局 / 老卡续玩）
---

在当前目录下启动话本RP流程。

## 第一步：扫描当前目录

查找素材文件（PNG角色卡、JSON世界书、TXT小说）：
- Glob 搜索 `角色卡/*/` 下的 `*.png`, `*.json`, `*.txt`
- 读取 `current-card.txt` 确定当前卡
- 检查当前卡的 `chat_log.json` 和 `memory/` 是否存在

## 第二步：根据扫描结果执行

### 情况 A — 有素材，无 chat_log.json（新卡开局）

按 CLAUDE.md「自动启动流程」步骤完整执行：

0. 清理残留 Python 进程，确认端口 8765 空闲
1. 启动桥接服务器：`python skills/start_server.py .`
2. 写入卡片路径到 `skills/styles/.card_path`
3. 执行导入管线：`python skills/import_prepare.py "角色卡/<卡名>" .`
4. 读取 `skills/styles/import_context.txt` 获取汇总上下文
5. 生成/交付开局（若 response.txt 已预填则直接交付）
6. 执行：`python skills/handler.py "角色卡/<卡名>" --opening`
7. 进入输入监听循环（见下方）
8. 告知用户：「前端已就绪，打开 http://localhost:8765」

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

Pi 中使用 bash 长轮询替代 Claude Code 的 ScheduleWakeup：

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
