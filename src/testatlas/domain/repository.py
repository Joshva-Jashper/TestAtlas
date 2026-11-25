from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


@dataclass(frozen=True, slots=True)
class GitHubRepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


def parse_github_repository_url(value: str) -> GitHubRepositoryRef:
    """Accept only a plain HTTPS GitHub repository URL; do not accept arbitrary clone URLs."""
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError("Enter a GitHub repository URL without surrounding whitespace.")

    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("The repository URL is malformed.") from exc

    if parsed.scheme.lower() != "https":
        raise ValueError("Repository links must use HTTPS.")
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com repository links are supported.")
    if parsed.query or parsed.fragment:
        raise ValueError("Repository URLs must not include query strings or fragments.")

    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
    if not path.startswith("/") or path.count("/") != 2:
        raise ValueError("Use a repository link in the form https://github.com/owner/repo.")
    parts = path[1:].split("/")

    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    if not _SEGMENT_PATTERN.fullmatch(owner) or not _SEGMENT_PATTERN.fullmatch(name):
        raise ValueError("The owner or repository name contains unsupported characters.")
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("The owner and repository name must be valid GitHub path segments.")

    return GitHubRepositoryRef(owner=owner, name=name)
