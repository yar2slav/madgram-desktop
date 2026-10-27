from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

os.umask(0o077)
directory = Path('/var/backups/mad-sync')
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
temporary = directory / f'history-{stamp}.partial'
target = temporary.with_suffix('.sqlite')
try:
    with sqlite3.connect('file:/var/lib/mad-sync/history.sqlite?mode=ro', uri=True) as source:
        with sqlite3.connect(temporary) as output:
            source.backup(output)
            if output.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('backup integrity check failed')
    temporary.replace(target)
    for old in sorted(directory.glob('history-*.sqlite'), reverse=True)[7:]:
        old.unlink()
finally:
    temporary.unlink(missing_ok=True)
