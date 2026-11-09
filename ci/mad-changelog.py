import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\| \[(\d+)\]\(\.\./(patches/[^)]+)\) \| (.+) \| ([^|]+) \|$")
SETTINGS_PAGE = re.compile(r"settings → mad → ([a-z ]+)")


def rows(text):
    result = []
    for line in text.splitlines():
        match = ROW.match(line.strip())
        if match:
            number, path, what, where = match.groups()
            result.append({"number": int(number), "path": path, "text": what.strip(), "where": where.strip()})
    return result


def previous_table(tag):
    if not tag:
        return ""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{tag}:docs/releases.md"],
        capture_output=True, text=True, encoding="utf-8")
    return result.stdout if result.returncode == 0 else ""


def category(where):
    match = SETTINGS_PAGE.search(where)
    if match:
        return match.group(1).strip()
    return "always on" if where.startswith("always on") else "other"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--previous", default="")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    number = re.fullmatch(r"v[0-9.]+-mad\.([1-9][0-9]*)", args.tag)
    if not number:
        raise SystemExit("tag must look like v7.4.1-mad.9")
    version = int(number.group(1))
    current = rows((ROOT / "docs/releases.md").read_text(encoding="utf-8"))
    known = {row["text"] for row in rows(previous_table(args.previous))}
    fresh = [row for row in current if row["text"] not in known]
    upstream = (ROOT / "UPSTREAM").read_text(encoding="utf-8").strip()
    previous_upstream = re.match(r"(v[0-9.]+)-mad\.", args.previous or "")
    moved = previous_upstream and previous_upstream.group(1) != upstream
    url = f"{args.repo}/releases/tag/{args.tag}"
    items = [{
        "number": row["number"],
        "text": row["text"],
        "where": row["where"],
        "category": category(row["where"]),
        "url": f"{args.repo}/blob/{args.tag}/{row['path']}",
    } for row in fresh]
    if moved:
        items.insert(0, {
            "number": 0,
            "text": f"moved to telegram desktop {upstream.lstrip('v')}",
            "where": "always on",
            "category": "always on",
            "url": "",
        })
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "mad-changelog.json").write_text(json.dumps({
        "version": version,
        "tag": args.tag,
        "title": f"mad {version}",
        "url": url,
        "items": items,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"## что нового в mad {version}", ""]
    if items:
        lines += [f"- {item['text']}" + ("" if item["where"] == "always on" else f" ({item['where']})") for item in items]
    else:
        lines.append("- исправления и обновление сборки")
    footer = (ROOT / "ci/release-notes.md").read_text(encoding="utf-8")
    footer = footer.replace("{tag}", args.tag).replace("{upstream}", upstream)
    (args.output / "release-notes.md").write_text("\n".join(lines) + "\n\n" + footer, encoding="utf-8")
    print(f"{len(items)} change(s) since {args.previous or 'the start'}")


if __name__ == "__main__":
    main()
