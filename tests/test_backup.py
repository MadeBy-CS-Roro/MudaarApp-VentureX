"""Exercise the operator-facing SQLite backup and restore commands."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import SCHEMA


ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "backup_db.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BACKUP_SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _seed_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO users(id, user_hash, display_name) VALUES (1, ?, ?)",
            ("synthetic-user-hash", "Backup Test"),
        )
        connection.execute(
            """INSERT INTO consents(id, user_id, bank_id, scopes, status, created_at, expires_at)
               VALUES (?, 1, ?, ?, ?, ?, ?)""",
            (
                "synthetic-consent",
                "synthetic-bank",
                '["transactions.read"]',
                "active",
                "2026-10-01T00:00:00Z",
                "2026-10-31T00:00:00Z",
            ),
        )
        connection.execute(
            """INSERT INTO transactions(
                   id, user_id, date, amount, direction, merchant, description, category
               ) VALUES (1, 1, ?, ?, ?, ?, ?, ?)""",
            ("2026-10-01", 42.75, "debit", "Test Merchant", "Synthetic record", "essential:test"),
        )
        connection.execute(
            """INSERT INTO plans(
                   id, user_id, name, merchant, kind, amount, day, active_until,
                   total_count, confirmed, action
               ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("synthetic-plan", "Test Plan", "Test Merchant", "loan", 125.0, 5, 11, 12, 1, "{}"),
        )


def test_backup_restore_preserves_users_consents_and_financial_records(tmp_path):
    database = tmp_path / "mawid.sqlite3"
    backup_directory = tmp_path / "private-backups"
    _seed_database(database)

    result = _run(
        "backup",
        "--database",
        str(database),
        "--backup-dir",
        str(backup_directory),
    )
    assert result.returncode == 0, result.stderr
    backups = list(backup_directory.glob("mawid-*.sqlite3"))
    assert len(backups) == 1
    backup = backups[0]
    if os.name == "posix":
        assert backup.stat().st_mode & 0o777 == 0o600
        assert backup_directory.stat().st_mode & 0o077 == 0

    # Simulate data loss in the live database before restoring the saved snapshot.
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DELETE FROM transactions")
        connection.execute("DELETE FROM plans")
        connection.execute("DELETE FROM consents")
        connection.execute("DELETE FROM users")

    accidental_overwrite = _run("restore", str(backup), "--database", str(database))
    assert accidental_overwrite.returncode != 0
    assert "--confirm-overwrite" in accidental_overwrite.stderr

    database_alias = tmp_path / "mawid-alias.sqlite3"
    database_alias.symlink_to(database)
    symlink_restore = _run(
        "restore",
        str(backup),
        "--database",
        str(database_alias),
        "--confirm-overwrite",
    )
    assert symlink_restore.returncode != 0
    assert "must not be a symlink" in symlink_restore.stderr

    restored = _run(
        "restore",
        str(backup),
        "--database",
        str(database),
        "--confirm-overwrite",
    )
    assert restored.returncode == 0, restored.stderr

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT id, user_hash, display_name FROM users"
        ).fetchall() == [(1, "synthetic-user-hash", "Backup Test")]
        assert connection.execute(
            "SELECT id, user_id, bank_id, scopes, status FROM consents"
        ).fetchall() == [
            (
                "synthetic-consent",
                1,
                "synthetic-bank",
                '["transactions.read"]',
                "active",
            )
        ]
        assert connection.execute(
            "SELECT id, user_id, date, amount, direction, merchant, category FROM transactions"
        ).fetchall() == [
            (1, 1, "2026-10-01", 42.75, "debit", "Test Merchant", "essential:test")
        ]
        assert connection.execute(
            "SELECT id, user_id, name, amount, kind, active_until, total_count, confirmed FROM plans"
        ).fetchall() == [
            ("synthetic-plan", 1, "Test Plan", 125.0, "loan", 11, 12, 1)
        ]


def test_backup_prunes_expired_snapshots_but_keeps_unrelated_files(tmp_path):
    database = tmp_path / "mawid.sqlite3"
    backup_directory = tmp_path / "private-backups"
    backup_directory.mkdir(mode=0o700)
    _seed_database(database)

    expired_backup = backup_directory / "mawid-20200101T000000000000Z.sqlite3"
    expired_backup.write_bytes(b"expired synthetic snapshot")
    os.utime(expired_backup, (time.time() - 31 * 24 * 60 * 60,) * 2)
    unrelated = backup_directory / "keep.txt"
    unrelated.write_text("not a database snapshot")

    result = _run(
        "backup",
        "--database",
        str(database),
        "--backup-dir",
        str(backup_directory),
        "--retention-days",
        "30",
    )

    assert result.returncode == 0, result.stderr
    assert not expired_backup.exists()
    assert unrelated.read_text() == "not a database snapshot"
    assert len(list(backup_directory.glob("mawid-*.sqlite3"))) == 1