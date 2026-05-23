#!/usr/bin/env python3
"""
check_bagu.py — 主动式反八股检查工具。

AI 生成 response.txt 后主动调用此脚本，获取精确违规位置和替换建议。
比 round_deliver.py 的安全网更全面（覆盖 bagu_rules.json 全部规则）。

用法:
  python check_bagu.py <ROOT>
输出:
  JSON — 若无违规: {"clean": true, "stats": {...}}
       — 若有违规: {"clean": false, "violations": [...], "stats": {...}}
"""

import json
import re
import sys
import time
from pathlib import Path


def load_rules(rules_path):
    """Load and pre-compile rules from bagu_rules.json."""
    with open(rules_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    compiled = []
    for cat in data.get("categories", []):
        cat_id = cat["id"]
        cat_name = cat["name"]
        severity = cat.get("severity", "medium")
        skip_in_dialogue = cat.get("skip_in_dialogue", False)

        for rule in cat.get("rules", []):
            pattern = rule["pattern"]
            rule_type = rule.get("type", "literal")

            if rule_type == "literal":
                regex = re.compile(re.escape(pattern))
            else:
                regex = re.compile(pattern)

            compiled.append({
                "regex": regex,
                "pattern_str": pattern,
                "type": rule_type,
                "category": cat_name,
                "category_id": cat_id,
                "severity": severity,
                "skip_in_dialogue": skip_in_dialogue,
                "replacement": rule.get("replacement"),
                "hint": rule.get("hint", ""),
            })

    return compiled


def extract_content(response_text):
    """Extract text inside <content>...</content> tags."""
    match = re.search(r"<content>(.*?)</content>", response_text, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def split_paragraphs(content_html):
    """Split content into paragraphs, return list of (paragraph_num, text)."""
    paragraphs = re.findall(r"<p>(.*?)</p>", content_html, re.DOTALL)
    if not paragraphs:
        paragraphs = [content_html]
    return [(i + 1, p) for i, p in enumerate(paragraphs)]


def strip_html(text):
    """Remove HTML tags."""
    return re.sub(r"<[^>]+>", "", text)


def extract_dialogue_spans(text):
    """Find character ranges that are inside dialogue quotes."""
    spans = []
    for m in re.finditer(r'[「「"](.*?)[」」"]', text):
        spans.append((m.start(), m.end()))
    return spans


def is_in_dialogue(pos, dialogue_spans):
    """Check if a character position falls inside dialogue."""
    for start, end in dialogue_spans:
        if start <= pos < end:
            return True
    return False


def check_rules(paragraphs, compiled_rules):
    """Run all rules against paragraphs. Returns list of violations."""
    violations = []
    vid = 0

    for para_num, para_html in paragraphs:
        para_text = strip_html(para_html)
        dialogue_spans = extract_dialogue_spans(para_text)

        for rule in compiled_rules:
            for match in rule["regex"].finditer(para_text):
                if rule["skip_in_dialogue"] and is_in_dialogue(match.start(), dialogue_spans):
                    continue

                vid += 1
                matched_text = match.group(0)
                start = max(0, match.start() - 10)
                end = min(len(para_text), match.end() + 10)
                context = "..." + para_text[start:end] + "..."

                violations.append({
                    "id": vid,
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "matched": matched_text,
                    "context": context,
                    "paragraph": para_num,
                    "replacement": rule["replacement"],
                    "hint": rule["hint"],
                })

    return violations


def check_structural(paragraphs):
    """Check structural issues: repeated openings, sensory repetition."""
    issues = []

    texts = [(num, strip_html(html)) for num, html in paragraphs]

    # Check repeated paragraph openings (same first character as subject)
    prev_opening = None
    repeat_count = 0
    for para_num, text in texts:
        text = text.strip()
        if not text:
            continue
        first_char = text[0] if text else ""
        if first_char == prev_opening and first_char in "她他它我你":
            repeat_count += 1
            if repeat_count >= 2:
                issues.append({
                    "type": "repeated_opening",
                    "detail": f"连续{repeat_count + 1}段以'{first_char}'开头（段落{para_num - repeat_count}到{para_num}）",
                    "hint": "变换开头方式：环境/动作/对话/感官/时间切入",
                })
        else:
            repeat_count = 0
        prev_opening = first_char

    # Check verb repetition (same verb 4+ times)
    all_text = "".join(t for _, t in texts)
    common_verbs = re.findall(r'[一-鿿]{1}(?:着|了|过)', all_text)
    from collections import Counter
    verb_counts = Counter(common_verbs)
    for verb, count in verb_counts.items():
        if count >= 4 and verb not in ("的了", "着了"):
            issues.append({
                "type": "verb_repetition",
                "detail": f"动词'{verb}'出现{count}次",
                "hint": f"减少'{verb}'的使用，换用同义词",
            })

    return issues


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: check_bagu.py <ROOT>"}, ensure_ascii=False))
        sys.exit(1)

    root = Path(sys.argv[1])
    styles_dir = root / "skills" / "styles"
    response_path = styles_dir / "response.txt"
    rules_path = styles_dir / "bagu_rules.json"

    if not response_path.exists():
        print(json.dumps({"error": "response.txt not found"}, ensure_ascii=False))
        sys.exit(1)

    if not rules_path.exists():
        print(json.dumps({"error": "bagu_rules.json not found"}, ensure_ascii=False))
        sys.exit(1)

    start_time = time.time()

    response_text = response_path.read_text(encoding="utf-8")
    content_html = extract_content(response_text)

    if not content_html.strip():
        print(json.dumps({"clean": True, "stats": {"rules_checked": 0, "content_chars": 0}}, ensure_ascii=False))
        sys.exit(0)

    compiled_rules = load_rules(rules_path)
    paragraphs = split_paragraphs(content_html)

    violations = check_rules(paragraphs, compiled_rules)
    structural_issues = check_structural(paragraphs)

    elapsed_ms = int((time.time() - start_time) * 1000)
    content_chars = len(strip_html(content_html))

    if not violations and not structural_issues:
        print(json.dumps({
            "clean": True,
            "stats": {
                "rules_checked": len(compiled_rules),
                "content_chars": content_chars,
                "check_time_ms": elapsed_ms,
            }
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "clean": False,
            "violation_count": len(violations),
            "violations": violations,
            "structural_issues": structural_issues,
            "stats": {
                "rules_checked": len(compiled_rules),
                "content_chars": content_chars,
                "check_time_ms": elapsed_ms,
            }
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
