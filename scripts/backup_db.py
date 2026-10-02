#!/usr/bin/env python3
"""Create, verify, and restore secure SQLite snapshots of the Mawid database."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = os.environ.get("MAWID_DB", "mawid.db")
REQUIRED_TABLES = {"users", "consents", "transactions", "plans"}
SNAPSHOT_NAME = re.compile(r"^mawid-\d{8}T\d{12}Z\.sqlite3$")


def _readonly_connection(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise ValueError(f"SQLite database does not exist: {database}")
    return sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)


def verify_database(database: Path) -> None:
    """Reject corrupt, incomplete, or referentially inconsistent snapshots."""
    with closing(_readonly_connection(database)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise ValueError(f"SQLite integrity check failed for {database}: {result}")

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(f"SQLite foreign-key check failed for {database}: {violations}")

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError(
                f"Database is missing required Mawid tables: {', '.join(sorted(missing))}"
            )


def _copy_database(source: Path, destination: Path) -> None:
    """Take a transactionally consistent SQLite snapshot using the backup API."""
    with closing(_readonly_connection(source)) as source_connection:
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            destination_connection.close()
    os.chmod(destination, 0o600)
    verify_database(destination)


def _ensure_private_directory(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved = directory.resolve()
    if not resolved.is_dir():
        raise ValueError(f"Backup destination is not a directory: {resolved}")
    if os.name == "posix" and resolved.stat().st_mode & 0o077:
        raise ValueError(
            f"Backup directory must be private (mode 0700 or stricter): {resolved}"
        )
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return resolved
    raise ValueError(
        "Backup directory must be outside the project/deployment directory; "
        "use a private, durable backup location."
    )


def _validate_private_backup(backup: Path) -> Path:
    if backup.is_symlink() or not backup.is_file():
        raise ValueError(f"Backup must be a regular file, not a symlink: {backup}")
    if os.name == "posix" and backup.stat().st_mode & 0o077:
        raise ValueError(f"Backup file must be private (mode 0600 or stricter): {backup}")
    return backup.resolve()


def _prune_expired(directory: Path, retention_days: int, now: datetime) -> int:
    cutoff = now.timestamp() - retention_days * 24 * 60 * 60
    removed = 0
    for candidate in directory.iterdir():
        if (
            SNAPSHOT_NAME.fullmatch(candidate.name)
            and not candidate.is_symlink()
            and candidate.is_file()
            and candidate.stat().st_mtime < cutoff
        ):
            candidate.unlink()
            removed += 1
    return removed


def create_backup(database: Path, backup_directory: Path, retention_days: int = 30) -> Path:
    if retention_days < 1:
        raise ValueError("Retention must be at least one day.")

    source = database.resolve()
    verify_database(source)
    directory = _ensure_private_directory(backup_directory)
    if directory == source.parent:
        raise ValueError("Backups must not be stored beside the live database.")

    now = datetime.now(timezone.utc)
    name = f"mawid-{now.strftime('%Y%m%dT%H%M%S%fZ')}.sqlite3"
    backup = directory / name
    fd, temporary_name = tempfile.mkstemp(prefix=".mawid-backup-", suffix=".tmp", dir=directory)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        _copy_database(source, temporary)
        os.replace(temporary, backup)
        os.chmod(backup, 0o600)
    finally:
        temporary.unlink(missing_ok=True)

    _prune_expired(directory, retention_days, now)
    return backup


def restore_backup(
    backup: Path,
    database: Path,
    *,
    confirm_overwrite: bool = False,
) -> Path:
    source = _validate_private_backup(backup)
    verify_database(source)
    destination = database.expanduser().absolute()
    if source == destination:
        raise ValueError("The backup and restore destination must be different files.")
    if not destination.parent.is_dir():
        raise ValueError(f"Restore destination directory does not exist: {destination.parent}")
    if destination.is_symlink():
        raise ValueError(f"Restore destination must not be a symlink: {destination}")
    if destination.exists() and not confirm_overwrite:
        raise ValueError(
            f"Restore would replace {destination}; pass --confirm-overwrite to continue."
        )
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{destination}{suffix}")
        if os.path.lexists(sidecar):
            raise ValueError(
                f"SQLite sidecar exists: {sidecar}. Stop the app and preserve or move "
                "the sidecar before restoring."
            )

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.restore-", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        _copy_database(source, temporary)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def positive_days(value: str) -> int:
    days = int(value)
    if days < 1:
        raise argparse.ArgumentTypeError("must be at least one day")
    return days


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup", help="create and verify a database snapshot")
    backup_parser.add_argument("--database", type=Path, default=Path(DEFAULT_DATABASE))
    backup_parser.add_argument("--backup-dir", type=Path, required=True)
    backup_parser.add_argument("--retention-days", type=positive_days, default=30)

    restore_parser = commands.add_parser("restore", help="restore a verified snapshot")
    restore_parser.add_argument("backup", type=Path)
    restore_parser.add_argument("--database", type=Path, default=Path(DEFAULT_DATABASE))
    restore_parser.add_argument(
        "--confirm-overwrite",
        action="store_true",
        help="required to replace an existing database",
    )

    verify_parser = commands.add_parser("verify", help="check database integrity and schema")
    verify_parser.add_argument("--database", type=Path, default=Path(DEFAULT_DATABASE))
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        if arguments.command == "backup":
            result = create_backup(
                arguments.database, arguments.backup_dir, arguments.retention_days
            )
            print(f"Verified backup created: {result}")
        elif arguments.command == "restore":
            result = restore_backup(
                arguments.backup,
                arguments.database,
                confirm_overwrite=arguments.confirm_overwrite,
            )
            print(f"Verified database restored: {result}")
        else:
            verify_database(arguments.database)
            print(f"Database verified: {arguments.database}")
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())