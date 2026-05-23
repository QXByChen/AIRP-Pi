#!/usr/bin/env python3
"""
round_prepare.py — 回合预处理管线。

收集 AI 生成叙事所需的全部上下文，输出到单一的 round_context.txt。
替代 CLAUDE.md「每轮处理」步骤 1-5.1 中所有机械性操作。

缓存策略：静态内容放文件开头（前缀缓存命中），动态内容放文件末尾。

用法:
  python round_prepare.py <card_folder> <ROOT>
"""

import json
import os
import re
import sys
from pathlib import Path

# In-process imports replace subprocess calls (was: subprocess.run to these scripts).
import match_worldbook
import mvu_check
from handler import apply_injections


def read_file(path):
    """Safely read a text file, return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def read_json(path):
    """Safely read a JSON file, return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_initvar_paths(initvar):
    """Recursively list all paths in initvar with current values."""
    lines = []

    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{prefix}/{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{prefix}/{i}")
        else:
            lines.append(f"  {prefix} = {json.dumps(obj, ensure_ascii=False)}")

    walk(initvar)
    return "\n".join(lines)


def grep_reference_md(card_folder, section_title):
    """Read reference.md and return lines under ## section_title (up to 200 lines).
    Pure Python — no shell grep dependency (Windows compatible)."""
    ref_path = Path(card_folder) / "memory" / "reference.md"
    if not ref_path.exists():
        return ""
    try:
        text = ref_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    marker = f"## {section_title}"
    lines = text.split("\n")
    output = []
    found = False
    for line in lines:
        if found and line.startswith("## ") and not line.startswith(marker):
            break
        if found:
            output.append(line)
            if len(output) >= 200:
                break
        if line.strip() == marker.strip():
            found = True
    return "\n".join(output)


def _keyword_score(keyword, text):
    """Score a keyword against text — mirrors match_worldbook.py logic.

    Returns integer score, 0 if no meaningful match.
    """
    if not keyword or not text:
        return 0
    if keyword in text:
        return 10
    if text in keyword:
        return 6
    # CJK character overlap (2+ shared chars)
    kw_chars = set(keyword)
    txt_chars = set(text)
    overlap = len(kw_chars & txt_chars)
    if overlap >= 2:
        return 3 + min(overlap, 5)
    return 0


def _input_matches(wb_index, user_text, card_folder):
    """Scan user input against worldbook index keywords, return top-3 with full entry text."""
    scored = []
    for entry in wb_index:
        keyword = entry.get("keyword", "")
        score = _keyword_score(keyword, user_text)
        if score > 0:
            scored.append({**entry, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)

    lines = []
    if not scored:
        lines.append("  (no matches)")
        return lines

    for i, m in enumerate(scored[:3]):
        lines.append(f"\n  --- Input Match {i+1}: {m['keyword']} (score={m['score']}) ---")
        lines.append(f"  Title: {m['title']}")
        lines.append(f"  One-liner: {m['one_liner'][:100]}")
        full = grep_reference_md(card_folder, m["section"].lstrip("#").strip())
        if full:
            lines.append("  Full entry:")
            for fl in full.split("\n")[:100]:
                lines.append(f"    {fl}")
    return lines


def main():
    if len(sys.argv) < 3:
        print("Usage: python round_prepare.py <card_folder> <ROOT>", file=sys.stderr)
        sys.exit(1)

    card_folder = sys.argv[1]
    root = sys.argv[2]
    styles_dir = Path(root) / "skills" / "styles"

    # ── Token delta capture (retroactively fixes previous turn) ──
    pending_tokens = {}
    try:
        import token_stats
        ts_path = token_stats.locate_transcript()
        cp = token_stats.load_checkpoint(card_folder) if ts_path else {}
        t_offset = cp.get("last_byte_offset", 0)

        if cp.get("previous_checkpoint"):
            token_stats.compute_startup_cost(card_folder)
            cp = token_stats.load_checkpoint(card_folder)
            t_offset = cp.get("last_byte_offset", 0)

        usage = token_stats.read_usage_since(ts_path, t_offset) if ts_path else []
        pending_delta = token_stats.compute_delta(usage)

        if pending_delta.get("request_count", 0) > 0:
            pd_in = pending_delta["input_tokens"]
            pd_out = pending_delta["output_tokens"]
            pending_tokens = {
                "round_in": pd_in,
                "round_out": pd_out,
                "round_total": pd_in + pd_out,
                "cache_read": pending_delta["cache_read"],
                "cache_hit": pending_delta["cache_hit_pct"],
            }

            # Retroactively fix the previous AI turn's token data in chat_log
            cl_path = Path(card_folder) / "chat_log.json"
            cl = read_json(cl_path) or []
            if cl:
                prev_turn = cl[-1]
                cum = cp.get("cumulative", {})
                prev_turn["tokens"] = {
                    "in": pd_in,
                    "out": pd_out,
                    "total": pd_in + pd_out,
                    "cache_read": pending_delta["cache_read"],
                    "cache_hit": pending_delta["cache_hit_pct"],
                    "cumulative_in": cum.get("input_tokens", 0) + pd_in,
                    "cumulative_out": cum.get("output_tokens", 0) + pd_out,
                    "cumulative_total": cum.get("input_tokens", 0) + cum.get("output_tokens", 0) + pd_in + pd_out,
                }
                with open(cl_path, "w", encoding="utf-8") as f:
                    json.dump(cl, f, ensure_ascii=False, indent=2)

            # Advance checkpoint to current transcript position
            token_stats.save_checkpoint(card_folder, delta=pending_delta, label="round")
    except Exception:
        pass

    # ── Gather data first ──
    input_path = styles_dir / "input.txt"
    user_input = read_file(input_path) or "(无输入)"
    user_text = user_input.strip()

    settings_path = styles_dir / "settings.json"
    settings = read_json(settings_path) or {}

    project_md = Path(card_folder) / "memory" / "project.md"
    recent_memory = ""
    if project_md.exists():
        raw = read_file(project_md)
        if raw:
            entries = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", raw)
            recent = entries[-3:] if len(entries) > 3 else entries
            recent_memory = "".join(recent).strip()[:3000]

    wb_index_path = Path(card_folder) / "memory" / ".worldbook_index.json"
    wb_index = read_json(wb_index_path) or []

    card_structure_path = Path(card_folder) / "memory" / ".card_structure.json"
    card_structure = read_json(card_structure_path)

    # Worldbook variable matching
    match_result = None
    try:
        match_result = match_worldbook.match_worldbook(card_folder)
    except Exception:
        pass

    # Injections (apply_injections prints to stdout for CLI use; suppress here)
    injections = []
    try:
        import io as _io, contextlib as _ctxlib
        with _ctxlib.redirect_stdout(_io.StringIO()):
            injections = apply_injections(card_folder)
        if injections is None:
            injections = []
    except Exception:
        pass

    # Variable paths
    mvu_data = None
    try:
        mvu_data = mvu_check.generate_checklist(card_folder)
    except Exception:
        pass

    initvar_path = Path(card_folder) / ".initvar.json"
    initvar = read_json(initvar_path)

    chat_log_path = Path(card_folder) / "chat_log.json"
    chat_log = read_json(chat_log_path) or []

    # Imagegen worldbook loading
    imgwb_constants = []
    imgwb_matches = []
    try:
        from imagegen.worldbook import ImagegenWorldbook
        imggen_settings = read_json(styles_dir / "imagegen_settings.json") or {}
        imgwb = ImagegenWorldbook(
            books_dir=styles_dir / "imagegen_worldbooks",
            settings=imggen_settings,
        )
        card_name = settings.get("charName", "") or Path(card_folder).name
        imgwb_constants = imgwb.get_constant_entries(card_name)
        match_text = user_text
        if chat_log:
            for entry in chat_log[-3:]:
                match_text += " " + entry.get("ai", "")[:500]
                match_text += " " + entry.get("user", "")[:200]
        imgwb_matches = imgwb.match_selective_entries(card_name, match_text)
    except Exception:
        pass

    # ═══════════════════════════════════════════════
    # BUILD OUTPUT — static prefix first (cached),
    # dynamic suffix last (uncached per round).
    # ═══════════════════════════════════════════════

    static_parts = []
    dynamic_parts = []

    # ── STATIC PREFIX (rarely changes, good for prompt cache) ──

    static_parts.append(f"=== WORLD_INDEX ({len(wb_index)} entries) ===")
    if wb_index:
        for entry in wb_index:
            static_parts.append(
                f"  [{entry.get('keyword','?')}] {entry.get('one_liner','')[:80]}"
            )

    if card_structure:
        static_parts.append(f"\n=== CARD_STRUCTURE ===")
        static_parts.append(f"  has_stages: {card_structure.get('has_stages', False)}")
        static_parts.append(f"  has_events: {card_structure.get('has_events', False)}")
        chars = card_structure.get("characters", {})
        if chars:
            static_parts.append(f"  characters: {', '.join(chars.keys())}")
    else:
        static_parts.append("\n=== CARD_STRUCTURE ===\n  (none)")

    static_parts.append("\n=== SETTINGS ===")
    for key in ["style", "nsfw", "person", "wordCount", "antiImpersonation", "bgNpc", "charName"]:
        val = settings.get(key, "未设置")
        static_parts.append(f"  {key}: {val}")

    # Initvar paths are static (never change after card import)
    if initvar:
        static_parts.append("\n=== INITVAR_PATHS (baseline structure) ===")
        static_parts.append(list_initvar_paths(initvar))

    # Imagegen worldbook constant entries (rules, templates, methodology)
    if imgwb_constants:
        static_parts.append(f"\n=== IMAGEGEN_WORLDBOOK ({len(imgwb_constants)} rules) ===")
        for entry in imgwb_constants:
            comment = entry.get("comment", "untitled")
            content = entry.get("content", "")
            static_parts.append(f"\n  --- {comment} ---")
            static_parts.append(f"  {content}")

    # ── DYNAMIC SUFFIX (changes every round) ──

    dynamic_parts.append("=== USER_INPUT ===")
    dynamic_parts.append(user_text)

    # Pending token delta from previous round's generation
    if pending_tokens:
        dynamic_parts.append("\n=== PENDING_TOKENS ===")
        for k, v in pending_tokens.items():
            dynamic_parts.append(f"  {k}: {v}")

    # Worldbook variable matches
    dynamic_parts.append("\n=== WORLD_MATCHES ===")
    if match_result:
        for i, m in enumerate(match_result[:3]):
            dynamic_parts.append(f"\n  --- Match {i+1}: {m['keyword']} (score={m['score']}, {m['reason']}) ---")
            dynamic_parts.append(f"  Title: {m['title']}")
            dynamic_parts.append(f"  One-liner: {m['one_liner'][:100]}")
            full = grep_reference_md(card_folder, m["section"].lstrip("#").strip())
            if full:
                dynamic_parts.append("  Full entry:")
                for line in full.split("\n")[:100]:
                    dynamic_parts.append(f"    {line}")
    else:
        dynamic_parts.append("  (no matches)")

    # NEW: User input keyword scan (bridges ST-like input-driven worldbook triggering)
    dynamic_parts.append("\n=== INPUT_MATCHES ===")
    dynamic_parts.extend(_input_matches(wb_index, user_text, card_folder))

    # Imagegen worldbook selective matches (characters, scenes, actions)
    dynamic_parts.append("\n=== IMAGEGEN_MATCHES ===")
    if imgwb_matches:
        for m in imgwb_matches[:6]:
            entry = m["entry"]
            comment = entry.get("comment", "?")
            content = entry.get("content", "")
            keys = ", ".join(m["matched_keys"])
            dynamic_parts.append(f"\n  --- {comment} (matched: {keys}) ---")
            dynamic_parts.append(f"  {content}")
    else:
        dynamic_parts.append("  (no imagegen matches)")

    # Injections
    dynamic_parts.append("\n=== INJECTIONS ===")
    if injections:
        for inj in injections:
            dynamic_parts.append(f"\n  Keyword: {inj}")
            section_title = inj if inj.startswith("## ") else f"## {inj}"
            full = grep_reference_md(card_folder, section_title.lstrip("#").strip())
            if full:
                for line in full.split("\n")[:80]:
                    dynamic_parts.append(f"    {line}")
    else:
        dynamic_parts.append("  (no injections)")

    # Variable paths
    dynamic_parts.append("\n=== VARIABLE_PATHS ===")
    if mvu_data:
        dynamic_parts.append(f"  Sections: {', '.join(mvu_data.get('sections', []))}")
        dynamic_parts.append(f"  Total paths: {mvu_data.get('total_paths', '?')}")
        dynamic_parts.append(f"  Touched last turn: {', '.join(mvu_data.get('touched_last_turn', []))}")
        dynamic_parts.append(f"  Untouched last turn: {', '.join(mvu_data.get('untouched_last_turn', []))}")
        checklist = mvu_data.get("checklist", "")
        if checklist:
            dynamic_parts.append("\n  Path details:")
            for line in checklist.split("\n"):
                dynamic_parts.append(f"  {line}")
        dynamic_parts.append(f"\n  Reminder: {mvu_data.get('reminder', '')}")
    else:
        dynamic_parts.append("  (mvu_check unavailable)")

    # Recent memory
    if recent_memory:
        dynamic_parts.append("\n=== RECENT_MEMORY ===")
        dynamic_parts.append(recent_memory)

    # Recent chat
    if chat_log:
        dynamic_parts.append("\n=== RECENT_CHAT (last 3 turns) ===")
        for entry in chat_log[-3:]:
            idx = entry.get("index", "?")
            user_txt = entry.get("user", "")[:200]
            summary = entry.get("summary", "")[:200]
            ai_txt = re.sub(r"<[^>]+>", "", entry.get("ai", ""))[:300]
            dynamic_parts.append(f"\n  Turn {idx}:")
            dynamic_parts.append(f"    User: {user_txt}")
            dynamic_parts.append(f"    AI: {ai_txt}")
            if summary:
                dynamic_parts.append(f"    Summary: {summary}")
    else:
        dynamic_parts.append("\n=== RECENT_CHAT ===\n  (no history — first turn)")

    # ── Write Output ──
    output_path = styles_dir / "round_context.txt"
    output_text = "\n".join(static_parts + dynamic_parts)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_text)

    print(json.dumps({
        "ok": True,
        "output": str(output_path),
        "size": len(output_text),
        "matches": len(match_result or []),
        "injections": len(injections),
        "is_first_turn": len(chat_log) <= 1
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
