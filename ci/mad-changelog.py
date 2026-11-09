import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\| \[(\d+)\]\(\.\./(patches/[^)]+)\) \| (.+) \| ([^|]+) \|$")
SETTINGS_PAGE = re.compile(r"settings → mad → ([a-z ]+)")
PAGES = {
    "interface": "интерфейс",
    "privacy": "приватность",
    "server": "сервер",
    "updates": "обновления",
    "mad badges": "бейджи mad",
}
CATEGORIES = {"always on": "общее", "other": "другое"}


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
    if result.returncode:
        raise SystemExit(f"cannot read docs/releases.md at {tag}")
    return result.stdout


def fresh_rows(previous):
    current = rows((ROOT / "docs/releases.md").read_text(encoding="utf-8"))
    known = {row["text"] for row in rows(previous_table(previous))}
    return [row for row in current if row["text"] not in known]


def russian():
    return json.loads((ROOT / "docs/releases.ru.json").read_text(encoding="utf-8"))


def page(where):
    match = SETTINGS_PAGE.search(where)
    return match.group(1).strip() if match else ""


def category(where):
    name = page(where)
    if name:
        return PAGES.get(name, name)
    return CATEGORIES["always on" if where.startswith("always on") else "other"]


def place(where):
    name = page(where)
    return f"настройки → mad → {PAGES.get(name, name)}" if name else ""


def check(previous):
    texts = russian()
    missing = [row["number"] for row in fresh_rows(previous) if str(row["number"]) not in texts]
    if missing:
        raise SystemExit("add russian release text to docs/releases.ru.json for rows: " + ", ".join(map(str, missing)))
    print(f"russian release text is ready since {previous or 'the start'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--previous", default="")
    parser.add_argument("--repo")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check(args.previous)
        return
    if not (args.tag and args.repo and args.output):
        raise SystemExit("--tag, --repo and --output are required")
    number = re.fullmatch(r"v[0-9.]+-mad\.([1-9][0-9]*)", args.tag)
    if not number:
        raise SystemExit("tag must look like v7.4.1-mad.9")
    version = int(number.group(1))
    texts = russian()
    upstream = (ROOT / "UPSTREAM").read_text(encoding="utf-8").strip()
    previous_upstream = re.match(r"(v[0-9.]+)-mad\.", args.previous or "")
    moved = previous_upstream and previous_upstream.group(1) != upstream
    url = f"{args.repo}/releases/tag/{args.tag}"
    items = [{
        "number": row["number"],
        "text": texts.get(str(row["number"]), row["text"]),
        "where": place(row["where"]),
        "category": category(row["where"]),
        "url": f"{args.repo}/blob/{args.tag}/{row['path']}",
    } for row in fresh_rows(args.previous)]
    items = [item for item in items if item["text"]]
    if moved:
        items.insert(0, {
            "number": 0,
            "text": f"переехали на telegram desktop {upstream.lstrip('v')}",
            "where": "",
            "category": CATEGORIES["always on"],
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
        lines += [f"- {item['text']}" + (f" ({item['where']})" if item["where"] else "") for item in items]
    else:
        lines.append("- исправления и обновление сборки")
    footer = (ROOT / "ci/release-notes.md").read_text(encoding="utf-8")
    footer = footer.replace("{tag}", args.tag).replace("{upstream}", upstream)
    (args.output / "release-notes.md").write_text("\n".join(lines) + "\n\n" + footer, encoding="utf-8")
    print(f"{len(items)} change(s) since {args.previous or 'the start'}")


if __name__ == "__main__":
    main()
