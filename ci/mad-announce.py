#!/usr/bin/env python3
"""post a rich message about a new mad release to the telegram channel."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = 'https://raw.githubusercontent.com/telegramdesktop/tdesktop/{tag}/changelog.txt'
VERSION = re.compile(r'^(\d+(?:\.\d+)*)(?:\s+beta)?\s+\(')
LIMIT = 3800
ORDER = [
    'интерфейс', 'чаты', 'сообщения', 'отправка', 'уведомления', 'меню',
    'приватность', 'профили и идентификаторы', 'боты', 'отладка', 'сервер',
    'обновления', 'бейджи mad', 'общее', 'другое',
]


def escape(text):
    text = re.sub(r'([\\`*_\[\]()~=|$!#+\-])', r'\\\1', text)
    return text.replace('<', '&#60;')


def version_key(text):
    return tuple(int(part) for part in text.lstrip('v').split('.'))


def upstream_changes(was, now):
    if not was or not now or was == now:
        return []
    try:
        with urllib.request.urlopen(CHANGELOG.format(tag=now), timeout=30) as response:
            text = response.read().decode('utf-8')
        low, high = version_key(was), version_key(now)
    except (OSError, ValueError):
        return []
    sections = []
    for line in text.splitlines():
        heading = VERSION.match(line)
        if heading:
            take = low < version_key(heading.group(1)) <= high
            sections.append([] if take else None)
            continue
        line = line.strip()
        if sections and sections[-1] is not None and line.startswith('- ') and 'build option' not in line:
            sections[-1].append(line[2:].strip())
    return [item for section in reversed(sections) if section for item in section]


def patch_count():
    return sum(1 for _ in (ROOT / 'patches').rglob('*.patch'))


def with_patches(count):
    last, last_two = count % 10, count % 100
    word = 'патчем' if last == 1 and last_two != 11 else 'патчами'
    return f'{count} {word}'


def first_sentence(text):
    match = re.match(r'(.+?[.!?])(\s|$)', text)
    return match.group(1) if match else text


def body(data, upstream, was, moved, short):
    grouped = {}
    for item in data['items']:
        if item['number'] == 0 and moved:
            continue
        text = first_sentence(item['text']) if short else item['text']
        grouped.setdefault(item['category'], []).append(f'- {escape(text)}')
    lines = []
    if moved:
        lines += [
            '',
            f'**telegram desktop {escape(upstream.lstrip("v"))}**',
            '',
            f'новое в telegram desktop с {escape(was.lstrip("v"))}:',
            '',
            *[f'- {escape(item)}' for item in moved],
        ]
    for title in ORDER + sorted(set(grouped) - set(ORDER)):
        if title in grouped:
            lines += ['', f'**{escape(title)}**', '', *grouped[title]]
    if not grouped and not moved:
        lines += ['', 'исправления и обновление сборки.']
    return lines


def message(args):
    data = json.loads(Path(args.changelog).read_text(encoding='utf-8'))
    upstream = (ROOT / 'UPSTREAM').read_text(encoding='utf-8').strip()
    previous = re.match(r'(v[0-9.]+)-mad\.', args.previous or '')
    was = previous.group(1) if previous and previous.group(1) != upstream else ''
    moved = upstream_changes(was, upstream)
    tdesktop = 'https://github.com/telegramdesktop/tdesktop/releases/tag/'
    head = [
        f'## mad {data["version"]} · {escape(upstream.lstrip("v"))}',
        '',
        f'telegram desktop [{escape(upstream)}]({tdesktop}{upstream}) с {with_patches(patch_count())}.',
    ]
    if args.macos:
        platforms = 'сборки для windows и macos в релизе. запущенный mad на windows обновится сам в течение 3 часов.'
    else:
        platforms = 'сборка для windows в релизе. запущенный mad обновится сам в течение 3 часов.'
    tail = [
        '',
        platforms,
        '',
        '<tg-button-row>'
        f'<tg-button type="url" url="{data["url"]}">скачать</tg-button>'
        f'<tg-button type="url" url="{args.url}/blob/main/docs/features.md">все патчи</tg-button>'
        '</tg-button-row>',
        '',
        '<footer>#desktop</footer>',
    ]
    for short in (False, True):
        text = '\n'.join(head + body(data, upstream, was, moved, short) + tail)
        if len(text) <= LIMIT:
            return text
    lines = body(data, upstream, was, moved, True)
    skipped = 0
    while lines and len('\n'.join(head + lines + tail)) > LIMIT - 80:
        if lines.pop().startswith('- '):
            skipped += 1
    more = ['', f'и ещё {skipped} — в описании релиза.'] if skipped else []
    return '\n'.join(head + lines + more + tail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--changelog', required=True, help='mad-changelog.json written by mad-changelog.py')
    parser.add_argument('--previous', default='', help='previous release tag, empty for the first one')
    parser.add_argument('--url', required=True, help='github url of the mad repo')
    parser.add_argument('--macos', action='store_true', help='the release has a macos build')
    parser.add_argument('--dry-run', action='store_true', help='print the request instead of sending it')
    args = parser.parse_args()

    payload = {
        'chat_id': os.environ.get('CHANNEL', ''),
        'rich_message': {'markdown': message(args)},
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    request = urllib.request.Request(
        f'https://api.telegram.org/bot{os.environ["BOT_TOKEN"]}/sendRichMessage',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        result = json.load(error)
    if not result.get('ok'):
        print(f'::warning::the announcement failed: {result.get("description")}')
        sys.exit(1)
    print(f'announced mad {json.loads(Path(args.changelog).read_text(encoding="utf-8"))["version"]} as message {result["result"]["message_id"]}')


if __name__ == '__main__':
    main()
