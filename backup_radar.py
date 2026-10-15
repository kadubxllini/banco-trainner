"""Private, consistent daily backups. Never touches imported historical backups."""
import os
import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def snapshot(source, target):
    with closing(sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)) as original:
        with closing(sqlite3.connect(target)) as backup:
            original.backup(backup)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup inválido.')


def run():
    os.umask(0o077)
    root = Path(os.environ['RADAR_BACKUP_DIR'])
    root.mkdir(parents=True, exist_ok=True)
    data = Path(os.environ['RADAR_DATA_DIR'])
    auth = Path(os.environ['RADAR_INSTANCE_PATH'])
    uploads = Path(os.environ['RADAR_UPLOAD_DIR'])
    name = 'radar-auto-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.tar.gz'
    partial = root / (name + '.partial')
    try:
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            staging = Path(temporary)
            snapshot(data / 'dados.db', staging / 'dados.db')
            snapshot(auth / 'access.db', staging / 'access.db')
            shutil.copy2(auth / 'session.key', staging / 'session.key')
            with tarfile.open(partial, 'w:gz') as archive:
                for file in staging.iterdir():
                    archive.add(file, arcname=file.name)
                if uploads.exists():
                    archive.add(uploads, arcname='uploads', recursive=True)
        partial.replace(root / name)
    finally:
        partial.unlink(missing_ok=True)
    for old in sorted(root.glob('radar-auto-*.tar.gz'), reverse=True)[7:]:
        old.unlink()
    print('Backup RADAR validado e salvo; retenção de sete snapshots automáticos.')


if __name__ == '__main__':
    run()
