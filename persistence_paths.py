"""Portable persisted identities and containment checks for derived sidecars."""
from pathlib import Path
import re


_IDENTITY = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)
}


def validate_identity(value: object, field: str) -> str:
    """Return an unchanged portable ID, or reject it with its field name.

    Generated IDs are hexadecimal, but readable IDs are also supported. Neither
    restoration nor export may coerce, sanitize, or regenerate an identity.
    """
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise ValueError(f"{field}: expected a nonempty ID using ASCII letters, digits, '_' or '-'")
    if value.casefold() in _RESERVED:
        raise ValueError(f"{field}: reserved Windows device name")
    return value


def sidecar_paths(root: Path, directory: str, identities: tuple[str, ...], filename: str) -> tuple[Path, Path]:
    """Resolve and check sidecar paths before any filesystem mutation.

    The caller supplies the fixed directory/filename and already validated IDs.
    Existing directory, destination and temporary-file links must remain inside
    the appropriate sidecar tree, itself contained by the configured save root.
    The configured root may itself be a symlink. This guards existing redirects,
    not concurrent changes to filesystem links by another process.
    """
    root = Path(root).resolve()
    base = root / directory
    target = base.joinpath(*identities, filename)
    temporary = target.with_suffix(target.suffix + ".tmp")
    resolved_base = base.resolve()
    if resolved_base == root or not resolved_base.is_relative_to(root):
        raise ValueError(f"{directory}: sidecar directory escapes save root")
    for path in (target.parent, target, temporary):
        resolved = path.resolve()
        if resolved == resolved_base or not resolved.is_relative_to(resolved_base):
            raise ValueError(f"{directory}: sidecar path escapes its directory")
    return target, temporary
