"""Policy-compliant SEC transport client.

Every request to an SEC host in this codebase goes through SecTransport.
It enforces the declared user agent with an administrative contact, an
aggregate cross-process rate cap safely below SEC's ten requests per second,
honors Retry-After and backoff signals, caches responses with conditional
revalidation, verifies advertised content length, and logs one structured
line per request with status, size, hash, cache disposition, and retries.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import time as time_module
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from us_fundamentals.config import SecTransportConfig
from us_fundamentals.errors import (
    ConfigurationError,
    MalformedInputError,
    RateLimitedError,
    TransientNetworkError,
    UpstreamUnavailableError,
)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class CrossProcessRateLimiter:
    """Sliding-window limiter shared across workers via a locked state file.

    All workers on a host point at the same state file; the aggregate request
    rate over any one-second window stays at or below `max_per_second`.
    """

    def __init__(
        self,
        state_path: Path,
        max_per_second: float,
        clock: Callable[[], float] = time_module.monotonic,
        sleeper: Callable[[float], None] = time_module.sleep,
    ) -> None:
        if not (0 < max_per_second < 10):
            raise ConfigurationError(
                f"aggregate SEC rate must be below 10 rps; got {max_per_second}"
            )
        self.state_path = state_path
        self.max_per_second = max_per_second
        self._clock = clock
        self._sleep = sleeper
        state_path.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self) -> float:
        """Block until a request slot is available; return the wait imposed."""
        waited = 0.0
        while True:
            with open(self.state_path, "a+", encoding="utf-8") as state_file:
                fcntl.flock(state_file, fcntl.LOCK_EX)
                state_file.seek(0)
                raw = state_file.read().strip()
                now = self._clock()
                stamps = [s for s in (json.loads(raw) if raw else []) if s > now - 1.0]
                if len(stamps) < self.max_per_second:
                    stamps.append(now)
                    state_file.seek(0)
                    state_file.truncate()
                    state_file.write(json.dumps(stamps))
                    return waited
                delay = max(stamps[0] + 1.0 - now, 0.01)
            self._sleep(delay)
            waited += delay


@dataclass
class FetchResult:
    url: str
    status: int
    content: bytes
    sha256: str
    from_cache: bool
    retries: int
    etag: str | None
    last_modified: str | None


class SecTransport:
    """Cached, identified, throttled, observable HTTP client for SEC hosts."""

    def __init__(
        self,
        config: SecTransportConfig,
        cache_dir: Path,
        logger: logging.LoggerAdapter | logging.Logger | None = None,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time_module.sleep,
    ) -> None:
        if "@" not in config.user_agent:
            raise ConfigurationError(
                "SEC user agent must declare an administrative contact email"
            )
        self.config = config
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger("sec_transport")
        self._sleep = sleeper
        self.rate_limiter = CrossProcessRateLimiter(
            cache_dir / "rate_limiter_state.json",
            config.max_requests_per_second,
            sleeper=sleeper,
        )
        self._client = httpx.Client(
            transport=transport,
            headers={
                "User-Agent": config.user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=config.timeout_seconds,
            follow_redirects=True,
        )
        # Per-process dedup: identical URLs within one transport instance are
        # served from cache without a second network round trip.
        self._fetched_this_run: set[str] = set()

    # -- cache ---------------------------------------------------------------

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode()).hexdigest()
        return (
            self.cache_dir / "objects" / key[:2] / key,
            self.cache_dir / "meta" / key[:2] / (key + ".json"),
        )

    def _read_cache(self, url: str) -> tuple[bytes, dict] | None:
        body_path, meta_path = self._cache_paths(url)
        if not (body_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = body_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != meta.get("sha256"):
            return None  # corrupt cache entry; refetch
        return body, meta

    def _write_cache(self, url: str, response: httpx.Response, body: bytes) -> str:
        body_path, meta_path = self._cache_paths(url)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(body).hexdigest()
        body_path.write_bytes(body)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "sha256": digest,
                    "size": len(body),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "fetched_at": time_module.time(),
                }
            ),
            encoding="utf-8",
        )
        return digest

    # -- fetch ---------------------------------------------------------------

    def get(self, url: str, revalidate: bool = True) -> FetchResult:
        """Fetch a URL through cache, rate cap, retries, and verification."""
        cached = self._read_cache(url)

        # Dedup within a run: a URL already fetched (or validated) this run
        # is served from cache with no request at all.
        if cached is not None and (url in self._fetched_this_run or not revalidate):
            body, meta = cached
            result = FetchResult(
                url=url,
                status=200,
                content=body,
                sha256=meta["sha256"],
                from_cache=True,
                retries=0,
                etag=meta.get("etag"),
                last_modified=meta.get("last_modified"),
            )
            self._log(result, cache_disposition="hit_no_request")
            return result

        headers: dict[str, str] = {}
        if cached is not None:
            _, meta = cached
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]

        retries = 0
        while True:
            self.rate_limiter.acquire()
            try:
                response = self._client.get(url, headers=headers)
            except httpx.TransportError as error:
                retries += 1
                if retries > self.config.max_retries:
                    raise TransientNetworkError(
                        f"transport failure fetching {url}", url=url
                    ) from error
                self._sleep(min(2**retries * 0.25, 30.0))
                continue

            if response.status_code == 304 and cached is not None:
                body, meta = cached
                self._fetched_this_run.add(url)
                result = FetchResult(
                    url=url,
                    status=304,
                    content=body,
                    sha256=meta["sha256"],
                    from_cache=True,
                    retries=retries,
                    etag=meta.get("etag"),
                    last_modified=meta.get("last_modified"),
                )
                self._log(result, cache_disposition="revalidated_304")
                return result

            if response.status_code in RETRYABLE_STATUS:
                retries += 1
                retry_after = _parse_retry_after(response)
                if retries > self.config.max_retries:
                    if response.status_code == 429:
                        raise RateLimitedError(
                            f"rate limited fetching {url} after {retries} tries",
                            retry_after_seconds=retry_after,
                            url=url,
                        )
                    raise UpstreamUnavailableError(
                        f"upstream {response.status_code} fetching {url} "
                        f"after {retries} tries",
                        url=url,
                        status=response.status_code,
                    )
                self._sleep(retry_after or min(2**retries * 0.5, 60.0))
                continue

            if response.status_code != 200:
                raise MalformedInputError(
                    f"unexpected status {response.status_code} for {url}",
                    url=url,
                    status=response.status_code,
                )

            body = response.content
            # Content-Length describes the wire bytes; when the body arrived
            # compressed (SEC gzips most text), httpx has already decompressed
            # it and the sizes legitimately differ. Verify only for identity.
            encoding = response.headers.get("Content-Encoding", "identity")
            declared = (
                response.headers.get("Content-Length")
                if encoding in ("identity", "")
                else None
            )
            if declared is not None and int(declared) != len(body):
                retries += 1
                if retries > self.config.max_retries:
                    raise TransientNetworkError(
                        f"persistent truncated content for {url}: "
                        f"declared {declared}, got {len(body)}",
                        url=url,
                    )
                self._sleep(min(2**retries * 0.25, 30.0))
                continue

            digest = self._write_cache(url, response, body)
            self._fetched_this_run.add(url)
            result = FetchResult(
                url=url,
                status=200,
                content=body,
                sha256=digest,
                from_cache=False,
                retries=retries,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
            self._log(
                result,
                cache_disposition="miss" if cached is None else "revalidation_changed",
            )
            return result

    def download_file(self, url: str, destination: Path) -> Path:
        """Stream a bulk archive to disk, resuming from a partial download.

        Bulk archives are the preferred path for historical initialization;
        per-accession requests should be reserved for objects the archives
        do not carry. Interrupted downloads leave `destination.part` and are
        resumed with a Range request instead of restarting from byte zero.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        retries = 0
        while True:
            offset = partial.stat().st_size if partial.exists() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            self.rate_limiter.acquire()
            try:
                with self._client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 200 and offset:
                        # Server ignored the Range; start over.
                        partial.unlink()
                        offset = 0
                    elif response.status_code in RETRYABLE_STATUS:
                        retries += 1
                        if retries > self.config.max_retries:
                            raise UpstreamUnavailableError(
                                f"upstream {response.status_code} for {url}",
                                url=url,
                            )
                        self._sleep(
                            _parse_retry_after(response) or min(2**retries * 0.5, 60.0)
                        )
                        continue
                    elif response.status_code not in (200, 206):
                        raise MalformedInputError(
                            f"unexpected status {response.status_code} for {url}",
                            url=url,
                            status=response.status_code,
                        )
                    mode = "ab" if response.status_code == 206 else "wb"
                    with open(partial, mode) as sink:
                        for chunk in response.iter_bytes(1 << 20):
                            sink.write(chunk)
            except httpx.TransportError:
                retries += 1
                if retries > self.config.max_retries:
                    raise TransientNetworkError(
                        f"transport failure downloading {url}", url=url
                    ) from None
                self._sleep(min(2**retries * 0.25, 30.0))
                continue

            body_size = partial.stat().st_size
            digest = _sha256_file(partial)
            partial.replace(destination)
            self.logger.info(
                "sec_download",
                extra={
                    "url": url,
                    "status": 200,
                    "size": body_size,
                    "sha256": digest,
                    "cache": "file",
                    "retries": retries,
                    "resumed_from": offset,
                },
            )
            return destination

    def _log(self, result: FetchResult, cache_disposition: str) -> None:
        self.logger.info(
            "sec_fetch",
            extra={
                "url": result.url,
                "status": result.status,
                "size": len(result.content),
                "sha256": result.sha256,
                "cache": cache_disposition,
                "retries": result.retries,
                "conditional": result.etag is not None
                or result.last_modified is not None,
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecTransport:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None
