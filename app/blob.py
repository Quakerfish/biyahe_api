"""
Direct Vercel Blob REST API client - no SDK dependency.

The official `vercel` PyPI package's AsyncBlobClient pulls in a telemetry
submodule with a broken internal import (vercel.internal.telemetry ->
vercel.oidc.decode_oidc_payload, which doesn't exist in the installed
version) that crashes on import in Vercel's own Python runtime. Rather than
depend on a third-party package with an internal bug like that, this calls
Vercel Blob's documented REST API directly with httpx - it's just one
authenticated PUT request, so the SDK was never pulling much weight anyway.

Docs: https://vercel.com/docs/vercel-blob (see "Accessing without the SDK")
"""

import httpx

from app.config import settings

_BLOB_API_BASE = "https://blob.vercel-storage.com"
_BLOB_API_VERSION = "7"


async def upload_blob(pathname: str, file_bytes: bytes, content_type: str) -> str:
    """Uploads a file to Vercel Blob (public access) and returns its public URL."""
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{_BLOB_API_BASE}/{pathname}",
            headers={
                "authorization": f"Bearer {settings.BLOB_READ_WRITE_TOKEN}",
                "x-api-version": _BLOB_API_VERSION,
                "x-content-type": content_type,
                # Required - the official SDK always sends this (its put()
                # call takes `access` as a mandatory option), and omitting
                # it is what was causing the 400 Bad Request here.
                "x-vercel-blob-access": "public",
                # We already make pathnames unique ourselves (timestamp + a
                # random hex suffix in profile.py), so skip Vercel's own
                # auto-suffixing - keeps the returned URL predictable.
                "x-add-random-suffix": "0",
            },
            content=file_bytes,
        )
        if response.is_error:
            # Surface Vercel's actual error body (e.g. "missing x-content-type"
            # or similar) in the exception, instead of just the generic
            # "400 Bad Request" httpx.raise_for_status() gives on its own -
            # that's the difference between guessing at the cause and
            # knowing it from the next log entry.
            raise httpx.HTTPStatusError(
                f"Vercel Blob upload failed ({response.status_code}): {response.text}",
                request=response.request,
                response=response,
            )
        return response.json()["url"]