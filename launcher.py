#!/usr/bin/env python3
"""
launcher.py — AIRP-Pi 一键启动器。

流程：
  1. 读取 config.json（无则启动配置模式）
  2. 检查/安装 npm 依赖
  3. 启动桥接服务器
  4. 打开浏览器
  5. 启动 Pi Agent（自动发送 /rp）
"""

import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
SKILLS_DIR = ROOT / "skills"
CARDS_DIR = ROOT / "角色卡"
SERVER_PORT = 8765


def load_config() -> dict | None:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if data.get("api_key"):
                return data
        except Exception:
            pass
    return None


def wait_for_server(timeout=15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "2", f"http://localhost:{SERVER_PORT}/api/pending"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                json.loads(result.stdout)
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start_server():
    """启动桥接服务器（后台）。"""
    server_py = str(SKILLS_DIR / "server.py")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, server_py],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(SKILLS_DIR),
        creationflags=flags,
    )


def ensure_npm_deps():
    """检查并安装 npm 依赖。"""
    root_modules = ROOT / "node_modules"
    skills_modules = SKILLS_DIR / "node_modules"

    if not root_modules.exists():
        print("[launcher] 安装根目录依赖...")
        subprocess.run(["npm", "install", "--silent"], cwd=str(ROOT), shell=True)

    if not skills_modules.exists():
        print("[launcher] 安装 skills 依赖...")
        subprocess.run(["npm", "install", "--silent"], cwd=str(SKILLS_DIR), shell=True)


def ensure_models_json():
    """部署 Pi models.json 到用户目录（注册 DeepSeek 供应商）。"""
    home = Path.home()
    pi_agent_dir = home / ".pi" / "agent"
    target = pi_agent_dir / "models.json"
    source = ROOT / "models.json"

    if not source.exists():
        return

    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if "deepseek" in existing.get("providers", {}):
                return
            # 合并：添加 deepseek provider
            new_data = json.loads(source.read_text(encoding="utf-8"))
            existing.setdefault("providers", {})["deepseek"] = new_data["providers"]["deepseek"]
            target.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
            print("[launcher] models.json 已更新（添加 DeepSeek 供应商）")
        except Exception:
            pass
    else:
        pi_agent_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(str(source), str(target))
        print("[launcher] models.json 已部署到 ~/.pi/agent/")


def find_pi_binary() -> str:
    """找到本地安装的 Pi 二进制路径。"""
    if sys.platform == "win32":
        local_pi = ROOT / "node_modules" / ".bin" / "pi.cmd"
    else:
        local_pi = ROOT / "node_modules" / ".bin" / "pi"

    if local_pi.exists():
        return str(local_pi)

    # Fallback: 全局安装
    try:
        result = subprocess.run(
            ["where" if sys.platform == "win32" else "which", "pi"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass

    return ""


def launch_pi(config: dict):
    """启动 Pi Agent，传入 /rp 作为初始消息进入 RP 技能循环。"""
    pi_bin = find_pi_binary()
    if not pi_bin:
        print("[launcher] 错误：找不到 Pi Agent。请运行 npm install")
        sys.exit(1)

    provider = config.get("provider", "deepseek")
    model = config.get("model", "deepseek-v4-pro")
    api_key = config.get("api_key", "")

    env = os.environ.copy()
    key_env_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    env_var = key_env_map.get(provider, f"{provider.upper()}_API_KEY")
    env[env_var] = api_key

    # Pass /rp as a positional argument so Pi enters interactive mode
    # and immediately executes the RP skill. Do NOT pipe stdin — Pi must
    # detect a TTY to stay in interactive mode (piped stdin → print mode → exit).
    cmd = [pi_bin, "--provider", provider, "--model", model, "/rp"]
    print(f"[launcher] 启动 Pi: {provider}/{model}")
    print(f"[launcher] 前端地址: http://localhost:{SERVER_PORT}")
    print()

    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(ROOT),
    )

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[launcher] 正在关闭...")
        proc.terminate()


def main():
    print("=" * 40)
    print("  AIRP-Pi RP Engine")
    print("=" * 40)
    print()

    # 1. 检查配置
    config = load_config()
    if not config:
        print("[launcher] 未找到 API Key 配置，启动设置模式...")
        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        start_server()
        if wait_for_server():
            webbrowser.open(f"http://localhost:{SERVER_PORT}/setup.html")
            print("[launcher] 请在浏览器中完成配置，保存后此窗口将自动继续...")
            # 轮询等待配置完成
            while not load_config():
                time.sleep(2)
            config = load_config()
            print("[launcher] 配置已保存！")
        else:
            print("[launcher] 服务器启动失败，请检查 Python 环境")
            sys.exit(1)
    else:
        print(f"[launcher] 配置已加载: {config.get('provider')}/{config.get('model')}")

    # 2. 检查依赖
    ensure_npm_deps()
    ensure_models_json()

    # 3. 确保角色卡目录存在
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    # 4. 启动服务器（如果还没运行）
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "2", f"http://localhost:{SERVER_PORT}/api/pending"],
            capture_output=True, text=True, timeout=3
        )
        server_running = result.returncode == 0 and result.stdout.strip()
    except Exception:
        server_running = False

    if not server_running:
        start_server()
        if not wait_for_server():
            print("[launcher] 服务器启动失败")
            sys.exit(1)

    # 5. 打开浏览器
    if config.get("auto_open_browser", True):
        webbrowser.open(f"http://localhost:{SERVER_PORT}")

    # 6. 启动 Pi
    launch_pi(config)


if __name__ == "__main__":
    main()
