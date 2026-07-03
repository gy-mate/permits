"""Full-cluster Postgres backup: ``pg_dumpall`` → tar → zstd → S3.

This used to be a standalone CronJob running the dump shell pipeline directly against
the database. It now lives in the backend so it can be triggered via the
``POST /permits/backup`` endpoint, with a thin CronJob that merely calls that endpoint
(mirroring how ``/permits/fetch`` is scheduled).

The Postgres connection parameters are taken from ``DB_CONNECTION_STRING`` (so the dump uses the
same credentials as the app); the S3 destination and AWS credentials come from the
environment (``PERMITS_BACKUP_S3_URI`` and the standard ``AWS_*`` variables).
"""

import asyncio
import datetime as dt
import io
import logging
import os
import tarfile
from compression import zstd
from urllib.parse import unquote, urlsplit

import boto3

from permits.config import get_settings

logger = logging.getLogger("permits.backup")

ZSTD_LEVEL = 19
DUMP_FILENAME = "permits.sql"


def pg_env() -> dict[str, str]:
    """libpq environment (PGHOST/PGPORT/PGUSER/PGPASSWORD) parsed from ``DB_CONNECTION_STRING``.

    ``pg_dumpall`` reads these standard variables, so the dump connects with the same
    host and credentials as the application without any extra configuration.
    """

    url = urlsplit(get_settings().database_url)
    env: dict[str, str] = {}

    if url.hostname:
        env["PGHOST"] = url.hostname
    if url.port:
        env["PGPORT"] = str(url.port)
    if url.username:
        env["PGUSER"] = unquote(url.username)
    if url.password:
        env["PGPASSWORD"] = unquote(url.password)
    
    return env


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split an ``s3://bucket/optional/prefix`` URI into ``(bucket, key_prefix)``.

    The returned prefix is empty or ends with ``/`` so a filename can be appended.
    """

    parts = urlsplit(uri)
    prefix = parts.path.lstrip("/")

    if prefix and not prefix.endswith("/"):
        prefix += "/"
    
    return parts.netloc, prefix


def tar_zst(name: str, data: bytes) -> bytes:
    """Wrap ``data`` as ``name`` in a tar archive, zstd-compressed.

    Tar (rather than a bare ``.sql.zst``) lets a restore stream the dump straight out
    of S3: ``zstd -d … -c | tar -xO permits.sql | psql``.
    """

    archive = io.BytesIO()

    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    
    return zstd.compress(archive.getvalue(), ZSTD_LEVEL)


async def dump_and_compress() -> bytes:
    """Run ``pg_dumpall`` and return its output as a zstd-compressed tar archive."""

    process = await asyncio.create_subprocess_exec(
        "pg_dumpall",
        "--no-password",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **pg_env()},
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()[:500]
        raise RuntimeError(f"pg_dumpall failed (exit {process.returncode}): {detail}")

    return await asyncio.to_thread(tar_zst, DUMP_FILENAME, stdout)


def upload_to_s3(bucket: str, key: str, body: bytes) -> None:
    """Upload ``body`` to ``s3://bucket/key`` (AWS credentials come from the env)."""
    
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body)


async def run() -> str:
    """Back the whole database up to S3; return the ``s3://`` URI of the upload."""

    bucket, prefix = parse_s3_uri(get_settings().backup_s3_uri)
    if not bucket:
        raise RuntimeError("PERMITS_BACKUP_S3_URI is not configured")

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{prefix}permits-{timestamp}.tar.zst"

    compressed = await dump_and_compress()
    await asyncio.to_thread(upload_to_s3, bucket, key, compressed)

    location = f"s3://{bucket}/{key}"
    logger.info("Database backup uploaded to %s (%d bytes)", location, len(compressed))
    return location
