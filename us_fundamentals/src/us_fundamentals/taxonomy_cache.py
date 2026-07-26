"""Offline taxonomy package cache (UF-013).

Builds a pinned local cache of every published standard-taxonomy package in
`config/taxonomy_vintages.json`: each zip is downloaded through the shared
SEC transport, hashed, extracted, and mapped into an offline URI catalog.
Modern packages contribute their authoritative META-INF/catalog.xml
rewrites; pre-package-format zips (us-gaap 2011-2015) are mapped by their
published directory convention. Parsing through `load_offline` resolves
taxonomy URIs exclusively from this catalog and fails closed: an attempted
network resolution is a terminal error naming every unresolved URI.

Filing extension schemas are NOT cached here; they live in accession
storage (UF-012).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from us_fundamentals.errors import ContractViolationError, IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VINTAGE_LIST_PATH = PROJECT_ROOT / "config" / "taxonomy_vintages.json"
PINNED_MANIFEST_PATH = PROJECT_ROOT / "config" / "taxonomy_cache_manifest.json"

MANIFEST_SCHEMA_VERSION = 2

_CATALOG_NS = "urn:oasis:names:tc:entity:xmlns:xml:catalog"


@dataclass(frozen=True)
class CachedPackage:
    family: str
    vintage: int
    url: str
    file_name: str
    sha256: str
    size_bytes: int
    catalog_sha256: str | None  # META-INF/catalog.xml when present
    rewrites: dict[str, str]  # URI prefix -> path relative to extraction root
    entry_point: str | None  # one representative canonical entry URL


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _both_schemes(prefix: str) -> list[str]:
    bare = re.sub(r"^https?://", "", prefix)
    return [f"http://{bare}", f"https://{bare}"]


def _catalog_rewrites(
    zip_path: Path, family: str, vintage: int
) -> tuple[str | None, dict[str, str], str | None]:
    """(catalog_sha256, {uri_prefix: zip-relative dir}, entry_point_url)."""
    catalog_sha: str | None = None
    rewrites: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        top_dirs = sorted({n.split("/", 1)[0] for n in names if "/" in n})
        catalog_names = [n for n in names if n.endswith("META-INF/catalog.xml")]
        if catalog_names:
            catalog_sha = hashlib.sha256(archive.read(catalog_names[0])).hexdigest()
            root = ElementTree.fromstring(archive.read(catalog_names[0]))
            meta_dir = Path(catalog_names[0]).parent
            for element in root.iter(f"{{{_CATALOG_NS}}}rewriteURI"):
                start = element.get("uriStartString")
                prefix = element.get("rewritePrefix")
                if not start or prefix is None:
                    continue
                # Normalize the zip-relative path lexically ('..' segments).
                target = (meta_dir / prefix).as_posix()
                parts: list[str] = []
                for piece in target.split("/"):
                    if piece == "..":
                        if parts:
                            parts.pop()
                    elif piece not in (".", ""):
                        parts.append(piece)
                normalized = "/".join(parts)
                for scheme_prefix in _both_schemes(start):
                    rewrites[scheme_prefix] = normalized
        else:
            # Pre-package-format zip: map the published directory convention
            # onto the single top-level directory.
            host = "xbrl.fasb.org" if family in ("us-gaap", "srt") else "xbrl.sec.gov"
            top = top_dirs[0] if top_dirs else ""
            for scheme_prefix in _both_schemes(f"{host}/{family}/{vintage}/"):
                rewrites[scheme_prefix] = top

        entry_point = _pick_entry_point(names, rewrites, family, vintage)
    return catalog_sha, rewrites, entry_point


def _pick_entry_point(
    names: list[str], rewrites: dict[str, str], family: str, vintage: int
) -> str | None:
    """Choose a representative schema and give its canonical URL."""
    candidates = [
        n for n in names if n.endswith(".xsd") and Path(n).name.startswith(f"{family}-")
    ]
    preferred = [
        n
        for n in candidates
        if Path(n).name in (f"{family}-{vintage}.xsd", f"{family}-{vintage}-01-31.xsd")
    ]
    ordered = sorted(preferred, key=len) + sorted(
        set(candidates) - set(preferred), key=len
    )
    for candidate in ordered:
        for prefix, local_dir in rewrites.items():
            if not prefix.startswith("https://"):
                continue
            base = local_dir.rstrip("/")
            if base and candidate.startswith(base + "/"):
                return prefix + candidate[len(base) + 1 :]
            if not base:
                return prefix + candidate
    return None


def build_cache(transport: Any, cache_dir: Path) -> dict[str, Any]:
    """Download, hash, extract, and catalog every listed package."""
    vintages = json.loads(VINTAGE_LIST_PATH.read_text(encoding="utf-8"))
    packages_dir = cache_dir / "packages"
    extracted_dir = cache_dir / "extracted"
    packages_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    cached: list[CachedPackage] = []
    for package in vintages["packages"]:
        file_name = package["url"].rsplit("/", 1)[-1]
        zip_path = packages_dir / file_name
        if not zip_path.exists():
            transport.download_file(package["url"], zip_path)
        stem = zip_path.stem
        target = extracted_dir / stem
        if not target.exists():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(target)
        catalog_sha, rewrites, entry_point = _catalog_rewrites(
            zip_path, package["family"], package["vintage"]
        )
        cached.append(
            CachedPackage(
                family=package["family"],
                vintage=package["vintage"],
                url=package["url"],
                file_name=file_name,
                sha256=_sha256_file(zip_path),
                size_bytes=zip_path.stat().st_size,
                catalog_sha256=catalog_sha,
                rewrites={
                    prefix: f"{stem}/{path}" if path else stem
                    for prefix, path in rewrites.items()
                },
                entry_point=entry_point,
            )
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "vintage_list_version": vintages["list_version"],
        "packages": [asdict(p) for p in cached],
    }
    (cache_dir / "cache_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def load_catalog(cache_dir: Path) -> dict[str, Path]:
    """Flatten the cache manifest into {uri_prefix: absolute local dir}."""
    manifest = json.loads(
        (cache_dir / "cache_manifest.json").read_text(encoding="utf-8")
    )
    catalog: dict[str, Path] = {}
    for package in manifest["packages"]:
        for prefix, rel in package["rewrites"].items():
            catalog[prefix] = cache_dir / "extracted" / rel
    for prefix, rel in manifest.get("core_schemas", {}).get("rewrites", {}).items():
        catalog[prefix] = cache_dir / "extracted" / rel
    return catalog


def discover_core_schemas(
    transport: Any, cache_dir: Path, max_rounds: int = 12
) -> dict[str, Any]:
    """Mirror the spec-level schemas the packages themselves import.

    Vintage packages assume the XBRL 2.1 / Dimensions / DTR / LRR / W3C base
    schemas are resolvable. Repeatedly attempt an offline load of every
    package entry point, download each unresolved URI into a per-host core
    mirror through the shared transport, and stop at a fixed point. The
    resulting file list is pinned in the manifest like any package.
    """
    manifest_path = cache_dir / "cache_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    core_root = cache_dir / "extracted" / "_core"
    core_root.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {
        f["url"]: f for f in manifest.get("core_schemas", {}).get("files", [])
    }

    entry_points = [p["entry_point"] for p in manifest["packages"] if p["entry_point"]]
    import tempfile

    for _ in range(max_rounds):
        unresolved: set[str] = set()
        for entry in entry_points:
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    load_offline(entry, cache_dir, Path(tmp))
                except ContractViolationError as error:
                    uris = error.context.get("unresolved_uris")
                    if isinstance(uris, list):
                        unresolved.update(uris)
        new = [u for u in sorted(unresolved) if u not in files]
        if not new:
            break
        for url in new:
            host_path = re.sub(r"^https?://", "", url)
            destination = core_root / host_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            result = transport.get(url)
            destination.write_bytes(result.content)
            files[url] = {
                "url": url,
                "sha256": result.sha256,
                "size_bytes": len(result.content),
            }
        manifest["core_schemas"] = {
            "rewrites": {
                "http://": "_core",
                "https://": "_core",
            },
            "files": sorted(files.values(), key=lambda f: f["url"]),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    return manifest


def resolve_offline(url: str, catalog: dict[str, Path]) -> Path | None:
    """Map a canonical taxonomy URL to its cached file, or None."""
    best: tuple[int, Path] | None = None
    for prefix, local_dir in catalog.items():
        if url.startswith(prefix) and (best is None or len(prefix) > best[0]):
            best = (len(prefix), local_dir / url[len(prefix) :].lstrip("/"))
    if best is None:
        return None
    return best[1] if best[1].exists() else None


def verify_cache(
    cache_dir: Path, pinned_manifest: Path = PINNED_MANIFEST_PATH
) -> list[str]:
    """Compare on-disk packages against the pinned manifest."""
    manifest = json.loads(pinned_manifest.read_text(encoding="utf-8"))
    problems: list[str] = []
    for package in manifest["packages"]:
        path = cache_dir / "packages" / package["file_name"]
        if not path.exists():
            problems.append(f"missing: {package['file_name']}")
        elif _sha256_file(path) != package["sha256"]:
            problems.append(f"hash mismatch: {package['file_name']}")
    return problems


def load_offline(target: str, cache_dir: Path, scratch_dir: Path) -> dict[str, Any]:
    """Parse a target with Arelle resolving URIs only from the cache.

    Fails closed: any URI the catalog cannot resolve aborts the parse with
    a terminal error naming the unresolved URIs. The Arelle web cache is
    pointed at an empty scratch directory so a previously warmed cache
    cannot mask a hole in the packages.
    """
    from arelle import Cntlr

    catalog = load_catalog(cache_dir)
    cntlr = Cntlr.Cntlr(logFileName="logToBuffer")
    cntlr.webCache.cacheDir = str(Path(scratch_dir) / "arelle_cache")
    cntlr.webCache.workOffline = True

    unresolved: list[str] = []
    original_getfilename = cntlr.webCache.getfilename

    def guarded(url: object, *args: Any, **kwargs: Any) -> Any:
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            mapped = resolve_offline(url, catalog)
            if mapped is not None:
                return str(mapped)
            unresolved.append(url)
            return None
        return original_getfilename(url, *args, **kwargs)

    cntlr.webCache.getfilename = guarded

    try:
        model = cntlr.modelManager.load(target)
        concepts = len(getattr(model, "qnameConcepts", {}) or {})
        facts = len(getattr(model, "facts", []) or [])
        errors = list(getattr(model, "errors", []) or [])
        model.close()
    except Exception as internal:  # Arelle can crash while logging a broken DTS
        concepts, facts = 0, 0
        errors = [f"arelle_internal:{type(internal).__name__}"]

    if unresolved:
        raise ContractViolationError(
            "offline taxonomy resolution attempted network access; "
            f"unresolved URIs: {sorted(set(unresolved))[:10]}",
            unresolved_uris=sorted(set(unresolved)),
        )
    return {"concepts": concepts, "facts": facts, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--cache-dir", type=Path, required=True)
    build.add_argument(
        "--pin",
        action="store_true",
        help="copy the manifest to config/ as the pinned version",
    )
    verify = sub.add_parser("verify")
    verify.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "build":
        from us_fundamentals.config import load_config
        from us_fundamentals.sec_transport import SecTransport

        config = load_config()
        with SecTransport(config.sec, args.cache_dir / "_http") as transport:
            build_cache(transport, args.cache_dir)
            manifest = discover_core_schemas(transport, args.cache_dir)
        if args.pin:
            PINNED_MANIFEST_PATH.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
        print(f"cached {len(manifest['packages'])} packages")
        return 0

    problems = verify_cache(args.cache_dir)
    if problems:
        print(json.dumps({"status": "failed", "problems": problems}, indent=2))
        raise IntegrityError(f"{len(problems)} package(s) fail verification")
    print(json.dumps({"status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
