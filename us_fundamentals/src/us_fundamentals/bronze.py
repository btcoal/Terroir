"""Immutable, content-addressed Bronze storage with accession manifests.

ADR-0001/ADR-0008: objects are addressed by SHA-256 and never mutated. An
accession manifest is the authoritative map from a filing to its parser-input
closure; a filing can be restored from manifest + objects alone, offline.
Reacquiring identical bytes is a no-op; different bytes for a recorded entry
is a terminal integrity event that never overwrites the prior object.

The store interface is deliberately restricted to operations an
S3-compatible object store also provides.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from us_fundamentals.errors import IntegrityError, MalformedInputError

MANIFEST_SCHEMA_VERSION = 1

ROLES = frozenset(
    {
        "filing_index",
        "primary_document",
        "instance",
        "extension_schema",
        "linkbase",
        "label",
        "reference",
        "filing_header",
        "external",
    }
)

STORAGE_CLASSES = frozenset({"stored", "optional_cold", "reference_only"})


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ObjectStore:
    """Content-addressed immutable object store on a filesystem."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / "sha256" / digest[:2] / digest

    def put_bytes(self, content: bytes) -> str:
        """Store content; returns its digest. Identical content is a no-op."""
        digest = sha256_bytes(content)
        path = self._path(digest)
        if path.exists():
            return digest  # idempotent by construction
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(path)  # atomic publication
        return digest

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()

    def get(self, digest: str) -> bytes:
        path = self._path(digest)
        if not path.exists():
            raise MalformedInputError(f"object {digest} not in store")
        content = path.read_bytes()
        if sha256_bytes(content) != digest:
            raise IntegrityError(
                f"stored object {digest} fails hash verification", digest=digest
            )
        return content

    def verify(self, digest: str) -> bool:
        try:
            self.get(digest)
            return True
        except (IntegrityError, MalformedInputError):
            return False


@dataclass(frozen=True)
class ManifestEntry:
    file_name: str
    role: str
    storage_class: str
    source_url: str
    size_bytes: int | None
    sha256: str | None
    content_type: str | None
    retrieved_at: str | None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise MalformedInputError(f"unknown object role {self.role!r}")
        if self.storage_class not in STORAGE_CLASSES:
            raise MalformedInputError(f"unknown storage class {self.storage_class!r}")
        if self.storage_class != "reference_only" and not (
            self.sha256 and self.size_bytes is not None
        ):
            raise MalformedInputError(
                f"{self.file_name}: stored objects require sha256 and size"
            )


@dataclass
class AccessionManifest:
    accession: str
    cik: int
    entries: dict[str, ManifestEntry] = field(default_factory=dict)
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "accession": self.accession,
                "cik": self.cik,
                "objects": [
                    asdict(e)
                    for e in sorted(self.entries.values(), key=lambda e: e.file_name)
                ],
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, payload: str) -> AccessionManifest:
        data = json.loads(payload)
        manifest = cls(
            accession=data["accession"],
            cik=data["cik"],
            schema_version=data["schema_version"],
        )
        for obj in data["objects"]:
            manifest.entries[obj["file_name"]] = ManifestEntry(**obj)
        return manifest


class BronzeStore:
    """Accession-oriented facade over the content-addressed object store."""

    def __init__(self, root: Path) -> None:
        self.objects = ObjectStore(root / "objects")
        self.manifest_dir = root / "manifests"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, accession: str) -> Path:
        return self.manifest_dir / f"{accession}.json"

    def load_manifest(self, accession: str) -> AccessionManifest | None:
        path = self._manifest_path(accession)
        if not path.exists():
            return None
        return AccessionManifest.from_json(path.read_text(encoding="utf-8"))

    def _write_manifest(self, manifest: AccessionManifest) -> None:
        path = self._manifest_path(manifest.accession)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(manifest.to_json(), encoding="utf-8")
        tmp.replace(path)

    def add_object(
        self,
        accession: str,
        cik: int,
        file_name: str,
        role: str,
        source_url: str,
        content: bytes,
        content_type: str | None = None,
        storage_class: str = "stored",
    ) -> ManifestEntry:
        """Store one closure object and record it in the manifest.

        Identical re-acquisition is idempotent. Different bytes for an
        already-recorded file name raise IntegrityError and leave both the
        prior object and the manifest untouched.
        """
        manifest = self.load_manifest(accession) or AccessionManifest(
            accession=accession, cik=cik
        )
        digest = sha256_bytes(content)
        existing = manifest.entries.get(file_name)
        if existing is not None:
            if existing.sha256 == digest:
                return existing  # idempotent no-op
            raise IntegrityError(
                f"{accession}/{file_name}: reacquired bytes hash {digest[:12]}… "
                f"but manifest records {str(existing.sha256)[:12]}…; refusing "
                "to overwrite",
                accession=accession,
                file_name=file_name,
                prior_sha256=existing.sha256,
                observed_sha256=digest,
            )
        self.objects.put_bytes(content)
        entry = ManifestEntry(
            file_name=file_name,
            role=role,
            storage_class=storage_class,
            source_url=source_url,
            size_bytes=len(content),
            sha256=digest,
            content_type=content_type,
            retrieved_at=datetime.now(tz=UTC).isoformat(),
        )
        manifest.entries[file_name] = entry
        self._write_manifest(manifest)
        return entry

    def add_reference(
        self,
        accession: str,
        cik: int,
        file_name: str,
        role: str,
        source_url: str,
    ) -> ManifestEntry:
        """Record a reference-only closure member without storing bytes."""
        manifest = self.load_manifest(accession) or AccessionManifest(
            accession=accession, cik=cik
        )
        entry = ManifestEntry(
            file_name=file_name,
            role=role,
            storage_class="reference_only",
            source_url=source_url,
            size_bytes=None,
            sha256=None,
            content_type=None,
            retrieved_at=None,
        )
        manifest.entries[file_name] = entry
        self._write_manifest(manifest)
        return entry

    def restore(self, accession: str, destination: Path) -> list[str]:
        """Materialize an accession's stored closure from manifest + objects.

        Uses only local state; never the network. Every restored file is
        hash-verified. Returns the restored file names.
        """
        manifest = self.load_manifest(accession)
        if manifest is None:
            raise MalformedInputError(f"no manifest for {accession}")
        destination.mkdir(parents=True, exist_ok=True)
        restored: list[str] = []
        for entry in manifest.entries.values():
            if entry.storage_class == "reference_only":
                continue
            assert entry.sha256 is not None  # enforced by ManifestEntry
            content = self.objects.get(entry.sha256)  # verifies hash
            (destination / entry.file_name).write_bytes(content)
            restored.append(entry.file_name)
        return sorted(restored)

    def verify_accession(self, accession: str) -> dict[str, bool]:
        """Hash-verify every stored object of an accession."""
        manifest = self.load_manifest(accession)
        if manifest is None:
            raise MalformedInputError(f"no manifest for {accession}")
        return {
            e.file_name: self.objects.verify(e.sha256)
            for e in manifest.entries.values()
            if e.storage_class != "reference_only" and e.sha256 is not None
        }
