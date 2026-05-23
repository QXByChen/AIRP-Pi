"""
AIRP Bug Report Generator — collects diagnostic info for troubleshooting.
Usage: python bug_report.py  (CLI, works even when server is down)
Also callable as a module from server.py for the /api/bug_report endpoint.
"""
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILLS = Path(__file__).parent
STYLES = SKILLS / "styles"
LOG_DIR = STYLES / ".logs"
LOG_FILE = LOG_DIR / "airp.log"
SETTINGS_FILE = STYLES / "settings.json"
STATE_FILE = STYLES / "state.js"
CARD_PATH_FILE = STYLES / ".card_path"


def _sanitize_path(text):
    """Replace Windows username in paths with <USER>."""
    return re.sub(
        r"[A-Z]:\\Users\\[^\\]+",
        lambda m: m.group(0)[:3] + "Users\\<USER>",
        text,
    )


def _get_node_version():
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "not found"
    except Exception:
        return "not found"


def _check_port(port):
    """Check if a local port is responding."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://localhost:{port}/", timeout=3)
        return True
    except Exception:
        return False


def _read_recent_logs(max_lines=200):
    """Read the last N lines from the log file."""
    if not LOG_FILE.exists():
        return "(no log file found)"
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        recent = lines[-max_lines:] if len(lines) > max_lines else lines
        return "\n".join(recent)
    except Exception as e:
        return f"(error reading logs: {e})"


def _extract_errors(log_text):
    """Extract unique ERROR/WARNING lines from logs."""
    errors = set()
    for line in log_text.splitlines():
        if " ERROR " in line or " WARNING " in line:
            msg = re.sub(r"^\[.*?\]\s*", "", line)
            errors.add(msg)
    return sorted(errors)[:20]


def _read_settings():
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return "(unable to read)"


def _read_state():
    """Extract key fields from state.js."""
    if not STATE_FILE.exists():
        return "(state.js not found)"
    try:
        text = STATE_FILE.read_text(encoding="utf-8")
        fields = {}
        for key in ("generatedCount", "world", "stage", "time", "location"):
            match = re.search(rf'"{key}"\s*:\s*"?([^",\n]+)"?', text)
            if match:
                fields[key] = match.group(1).strip()
        return fields if fields else "(no fields extracted)"
    except Exception as e:
        return f"(error: {e})"


def _get_card_info():
    """Get current card folder path."""
    if not CARD_PATH_FILE.exists():
        return "(no card loaded)"
    try:
        path = CARD_PATH_FILE.read_text(encoding="utf-8").strip()
        return _sanitize_path(path) if path else "(empty)"
    except Exception:
        return "(error reading)"


def generate_report():
    """Generate a full diagnostic report. Returns dict."""
    log_text = _read_recent_logs()

    report = {
        "generated_at": datetime.now().isoformat(),
        "system": {
            "os": platform.platform(),
            "python": sys.version,
            "node": _get_node_version(),
            "cwd": _sanitize_path(str(Path.cwd())),
        },
        "services": {
            "server_8765": _check_port(8765),
            "mvu_server_8766": _check_port(8766),
        },
        "card": _get_card_info(),
        "settings": _read_settings(),
        "state": _read_state(),
        "error_summary": _extract_errors(log_text),
        "recent_logs": _sanitize_path(log_text),
    }
    return report


def format_report_text(report):
    """Format report dict as human-readable text for GitHub issue."""
    lines = []
    lines.append("=" * 50)
    lines.append("AIRP 诊断报告")
    lines.append(f"生成时间: {report['generated_at']}")
    lines.append("=" * 50)

    lines.append("\n## 系统信息")
    sys_info = report["system"]
    lines.append(f"  OS: {sys_info['os']}")
    lines.append(f"  Python: {sys_info['python']}")
    lines.append(f"  Node: {sys_info['node']}")
    lines.append(f"  工作目录: {sys_info['cwd']}")

    lines.append("\n## 服务状态")
    svc = report["services"]
    lines.append(f"  Bridge Server (8765): {'运行中' if svc['server_8765'] else '未响应'}")
    lines.append(f"  MVU Server (8766): {'运行中' if svc['mvu_server_8766'] else '未响应'}")

    lines.append(f"\n## 当前角色卡: {report['card']}")

    lines.append("\n## 设置")
    settings = report["settings"]
    if isinstance(settings, dict):
        for k, v in settings.items():
            lines.append(f"  {k}: {v}")
    else:
        lines.append(f"  {settings}")

    lines.append("\n## 状态")
    state = report["state"]
    if isinstance(state, dict):
        for k, v in state.items():
            lines.append(f"  {k}: {v}")
    else:
        lines.append(f"  {state}")

    lines.append("\n## 错误摘要")
    errors = report["error_summary"]
    if errors:
        for e in errors:
            lines.append(f"  - {e}")
    else:
        lines.append("  (无错误记录)")

    lines.append("\n## 最近日志 (最后200行)")
    lines.append(report["recent_logs"])

    return "\n".join(lines)


def save_report(report):
    """Save report to .logs directory, return file path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"bug_report_{ts}.txt"
    text = format_report_text(report)
    path.write_text(text, encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    report = generate_report()
    saved = save_report(report)
    print(json.dumps({"ok": True, "path": _sanitize_path(saved)}, ensure_ascii=False))
    print(f"\n诊断报告已保存: {saved}")
    print(format_report_text(report))
