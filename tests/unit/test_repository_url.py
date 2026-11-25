import pytest

from testatlas.domain.repository import parse_github_repository_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/saucelabs/sample-app-web", "saucelabs/sample-app-web"),
        ("https://github.com/Owner/repo_name.git/", "Owner/repo_name"),
        ("https://GITHUB.com/owner/repo", "owner/repo"),
    ],
)
def test_parse_valid_repository_urls(url: str, expected: str) -> None:
    repository = parse_github_repository_url(url)

    assert repository.full_name == expected
    assert repository.canonical_url == f"https://github.com/{expected.removesuffix('.git')}"


@pytest.mark.parametrize(
    "url",
    [
        "",
        " https://github.com/owner/repo",
        "https://github.com/owner/repo ",
        "http://github.com/owner/repo",
        "https://github.com.evil.test/owner/repo",
        "https://evil.test/owner/repo",
        "https://user:password@github.com/owner/repo",
        "https://github.com:8443/owner/repo",
        "https://github.com:/owner/repo",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner%2Frepo/name",
        "https://github.com/../repo",
        "https://github.com/owner/../repo",
        "https://github.com//owner/repo",
        "https://github.com/owner/repo\n",
    ],
)
def test_reject_unsafe_or_unsupported_repository_urls(url: str) -> None:
    with pytest.raises(ValueError):
        parse_github_repository_url(url)
