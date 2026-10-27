import argparse
import ast
import json
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--tdesktop", type=Path, default=Path(__file__).resolve().parents[2] / "tdesktop")
args = parser.parse_args()
root = args.tdesktop / "Telegram"
catalog = json.loads((root / "Resources/langs/mad_ru.json").read_text(encoding="utf-8"))
literal = r'(?:u?"(?:\\.|[^"\\])*"\s*)+_q'
patterns = [r'\bTr\(\s*(' + literal + ')', r'\.(?:name|description)\s*=\s*((?:u?"(?:\\.|[^"\\])*"\s*)+)(?:_q)?']
patterns.append(r"\bTrCount\([^,\n]+,\s*(" + literal + r"),\s*(" + literal + r")")
required = set()
for path in (root / "SourceFiles").rglob("*.cpp"):
    if "tele" not in path.parts and path.name != "settings_tele.cpp":
        continue
    text = path.read_text(encoding="utf-8")
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            for group in match.groups():
                required.add("".join(json.loads(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', group)))
for path in (root / "Resources/tele_html").glob("*.js"):
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"\bmadTr\(\s*('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")", text):
        required.add(ast.literal_eval(match[1]))
missing = sorted(required - catalog.keys())
bad = []
for key, translations in catalog.items():
    values = translations if isinstance(translations, list) else [translations]
    if isinstance(translations, list) and len(translations) != 3:
        bad.append(key)
    for value in values:
        if re.search(r"\bmad\b", key, re.I) and not re.search(r"\bmad\b", value, re.I):
            bad.append(key)
        if not value or sorted(re.findall(r'%\d+|%n', key)) != sorted(re.findall(r'%\d+|%n', value)):
            bad.append(key)
print(json.dumps({"required": len(required), "catalog": len(catalog), "missing": missing, "invalid": bad}, ensure_ascii=False, indent=2))
raise SystemExit(bool(missing or bad))
