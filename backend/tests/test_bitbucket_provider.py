"""Bitbucket Cloud provider against mocked HTTP (``httpx.MockTransport``).

Nothing here talks to the network. Payload shapes follow Bitbucket's published
OpenAPI description; a live read-only smoke test is a separate, human-run step.
"""
import httpx
import pytest

from app.errors import (
    ConfigError, ProviderAuthError, ProviderError, ProviderUnavailable, RefNotFound,
    RepositoryAccessDenied, RepositoryNotFound, ScanError,
)
from app.providers import ChangeProvider, PullRequestProvider, RepositoryProvider, RepositoryRef
from app.providers import bitbucket
from app.providers.bitbucket import BitbucketCloudProvider, split_patches
from app.scanner import scan_changes

API = "https://api.bitbucket.org/2.0"
REPO = "/repositories/acme/ledger"
BASE, HEAD = "a" * 40, "b" * 40
TOKEN = "s3cr3t-token-value"

DIFF = (
    "diff --git a/app/auth.py b/app/auth.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/app/auth.py\n"
    "+++ b/app/auth.py\n"
    "@@ -1,3 +1,2 @@\n"
    " def check(user):\n"
    "-    verify(user)\n"
    "     return True\n"
    "diff --git a/docs/new file.md b/docs/new file.md\n"
    "new file mode 100644\n"
    "index 0000000..3333333\n"
    "--- /dev/null\n"
    "+++ b/docs/new file.md\t\n"
    "@@ -0,0 +1 @@\n"
    "+hello\n"
    "diff --git a/old.txt b/old.txt\n"
    "deleted file mode 100644\n"
    "index 4444444..0000000\n"
    "--- a/old.txt\n"
    "+++ /dev/null\n"
    "@@ -1 +0,0 @@\n"
    "-bye\n"
    'diff --git "a/caf\\303\\251.py" "b/caf\\303\\251.py"\n'
    "index 5555555..6666666 100644\n"
    '--- "a/caf\\303\\251.py"\n'
    '+++ "b/caf\\303\\251.py"\n'
    "@@ -1 +1 @@\n"
    "-x = 1\n"
    "+x = 2\n"
    "diff --git a/run me.sh b/run me.sh\n"
    "old mode 100644\n"
    "new mode 100755\n"
)
STATS = [
    {"status": "modified", "lines_added": 0, "lines_removed": 1, "old": {"path": "app/auth.py"}, "new": {"path": "app/auth.py"}},
    {"status": "added", "lines_added": 1, "lines_removed": 0, "old": None, "new": {"path": "docs/new file.md"}},
    {"status": "removed", "lines_added": 0, "lines_removed": 1, "old": {"path": "old.txt"}, "new": None},
    {"status": "modified", "lines_added": 1, "lines_removed": 1, "old": {"path": "café.py"}, "new": {"path": "café.py"}},
    {"status": "modified", "lines_added": 0, "lines_removed": 0, "old": {"path": "run me.sh"}, "new": {"path": "run me.sh"}},
]


def js(data, status=200, **headers):
    return httpx.Response(status, json=data, headers=headers)


class FakeBitbucket:
    """Routes by URL path (without ``/2.0``). A route is a response, a list of
    responses served in order (the last one repeats), or a callable."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests = []
        self.sleeps = []

    def __call__(self, request):
        self.requests.append(request)
        route = self.routes.get(request.url.path.removeprefix("/2.0"))
        if route is None:
            return js({"type": "error"}, 404)
        if isinstance(route, list):
            route = route.pop(0) if len(route) > 1 else route[0]
        return route(request) if callable(route) else route

    def provider(self, repositories=("ledger",), **kwargs):
        kwargs.setdefault("token", TOKEN)
        return BitbucketCloudProvider(
            "acme", repositories, transport=httpx.MockTransport(self), sleep=self.sleeps.append, **kwargs,
        )

    def paths(self):
        return [request.url.path.removeprefix("/2.0") for request in self.requests]


LEDGER = RepositoryRef("bitbucket-cloud", "acme/ledger", "Ledger", "https://bitbucket.org/acme/ledger", "main")


def compare_routes(stats=STATS, diff=DIFF, **extra):
    return {
        f"{REPO}/commit/{BASE}": js({"hash": BASE}),
        f"{REPO}/commit/{HEAD}": js({"hash": HEAD}),
        f"{REPO}/diffstat/{HEAD}..{BASE}": js({"values": stats, "size": len(stats)}),
        f"{REPO}/diff/{HEAD}..{BASE}": httpx.Response(200, text=diff),
        **extra,
    }


# -- construction, discovery, allowlist ---------------------------------------

def test_provider_satisfies_all_three_contracts():
    provider = FakeBitbucket().provider()
    assert isinstance(provider, RepositoryProvider)
    assert isinstance(provider, PullRequestProvider)
    assert isinstance(provider, ChangeProvider)


@pytest.mark.parametrize("workspace,repositories,token", [
    ("../etc", ["ledger"], TOKEN), ("acme", ["ok", "bad/slug"], TOKEN), ("acme", ["ledger"], " "),
])
def test_invalid_configuration_is_refused(workspace, repositories, token):
    with pytest.raises(ConfigError) as error:
        BitbucketCloudProvider(workspace, repositories, token=token)
    assert TOKEN not in str(error.value)


def test_discovery_follows_pagination_and_returns_only_approved_repositories():
    fake = FakeBitbucket({"/repositories/acme": [
        js({"values": [{"slug": "secret-repo", "name": "Secret"}, {"slug": "web", "name": "Web"}],
            "next": f"{API}/repositories/acme?page=2"}),
        js({"values": [{"slug": "Ledger", "name": "Ledger", "mainbranch": {"name": "main"},
                        "links": {"html": {"href": "https://evil.example/x"}}}]}),
    ]})
    repositories = fake.provider(["ledger", "web", "missing"]).list_repositories()
    assert [r.id for r in repositories] == ["acme/ledger", "acme/web"]
    assert repositories[0] == LEDGER  # location is built locally, not copied from the payload
    assert [r.url.query for r in fake.requests] == [b"pagelen=100", b"page=2"]


def test_an_empty_repository_list_discovers_nothing_without_calling_bitbucket():
    fake = FakeBitbucket()
    assert fake.provider([]).list_repositories() == []
    assert fake.requests == []


def test_repository_outside_the_approved_list_is_denied_before_any_request():
    fake = FakeBitbucket()
    provider = fake.provider()
    for repository_id in ("acme/other", "rival/ledger"):
        with pytest.raises(RepositoryAccessDenied):
            provider.get_repository(repository_id)
    for repository_id in ("ledger", "acme/a/b", "acme/..", "acme/le dger", ""):
        with pytest.raises(RepositoryNotFound):
            provider.get_repository(repository_id)
    forged = RepositoryRef("bitbucket-cloud", "acme/other", "x", "x")
    for call in (
        lambda: provider.list_pull_requests(forged), lambda: provider.resolve_commit(forged, "main"),
        lambda: provider.get_changes(forged, BASE, HEAD), lambda: provider.list_files(forged, HEAD),
        lambda: provider.read_file(forged, HEAD, "a.py"),
    ):
        with pytest.raises(RepositoryAccessDenied):
            call()
    assert fake.requests == []


def test_get_repository_reads_an_approved_repository_and_maps_404():
    fake = FakeBitbucket({REPO: js({"slug": "ledger", "name": "Ledger", "mainbranch": {"name": "main"}})})
    assert fake.provider().get_repository("ACME/Ledger") == LEDGER
    with pytest.raises(RepositoryNotFound):
        FakeBitbucket().provider().get_repository("acme/ledger")


# -- credentials and transport safety -----------------------------------------

def test_access_token_is_sent_as_bearer_and_never_in_the_url():
    fake = FakeBitbucket({REPO: js({"slug": "ledger"})})
    fake.provider().get_repository("acme/ledger")
    request = fake.requests[0]
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(request.url)


def test_api_token_with_email_is_sent_as_basic_auth():
    fake = FakeBitbucket({REPO: js({"slug": "ledger"})})
    fake.provider(email="dev@example.com").get_repository("acme/ledger")
    assert fake.requests[0].headers["authorization"].startswith("Basic ")


def test_pagination_link_to_another_host_is_not_followed():
    fake = FakeBitbucket({"/repositories/acme": js({"values": [], "next": "https://evil.example/2.0/steal"})})
    with pytest.raises(ProviderError, match="outside its API"):
        fake.provider().list_repositories()
    assert [r.url.host for r in fake.requests] == ["api.bitbucket.org"]


def test_redirects_are_not_followed():
    fake = FakeBitbucket({REPO: httpx.Response(302, headers={"Location": "https://evil.example/"})})
    with pytest.raises(ProviderError):
        fake.provider().get_repository("acme/ledger")
    assert len(fake.requests) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_credentials_raise_an_auth_error_without_the_secret(status):
    fake = FakeBitbucket({REPO: js({"error": {"message": f"token {TOKEN} invalid"}}, status)})
    with pytest.raises(ProviderAuthError) as error:
        fake.provider().get_repository("acme/ledger")
    assert TOKEN not in str(error.value) and str(status) in str(error.value)
    assert len(fake.requests) == 1  # never retried


def test_rate_limit_is_retried_using_retry_after_then_succeeds():
    fake = FakeBitbucket({REPO: [js({}, 429, **{"Retry-After": "3"}), js({}, 503), js({"slug": "ledger"})]})
    assert fake.provider().get_repository("acme/ledger").id == "acme/ledger"
    assert fake.sleeps == [3.0, 2.0]


def test_persistent_rate_limit_gives_up_after_bounded_retries():
    fake = FakeBitbucket({REPO: js({}, 429, **{"Retry-After": "9999"})})
    with pytest.raises(ProviderUnavailable, match="rate limit"):
        fake.provider().get_repository("acme/ledger")
    assert len(fake.requests) == 3 and fake.sleeps == [10.0, 10.0]  # wait is capped


def test_timeouts_and_connection_failures_are_retried_then_reported():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    fake = FakeBitbucket({REPO: timeout})
    with pytest.raises(ProviderUnavailable, match="did not respond"):
        fake.provider().get_repository("acme/ledger")
    assert len(fake.requests) == 3
    with pytest.raises(ProviderUnavailable, match="ConnectError"):
        FakeBitbucket({REPO: refused}).provider(max_retries=0).get_repository("acme/ledger")


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>login</html>"), js([1, 2]), js({"values": "nope"}), js({"values": [1]}),
    httpx.Response(500, text="boom"),
])
def test_malformed_or_failed_listing_is_a_provider_error(response):
    with pytest.raises(ProviderError):
        FakeBitbucket({"/repositories/acme": response}).provider().list_repositories()


# -- pull requests -------------------------------------------------------------

def pull_request(number=7, **overrides):
    payload = {
        "id": number, "title": "Tighten auth", "state": "OPEN", "updated_on": "2026-11-10T09:00:00+00:00",
        "author": {"display_name": "Sam Dev"},
        "source": {"branch": {"name": "feature/auth"}, "commit": {"hash": "bbbbbbbbbbbb"}},
        "destination": {"branch": {"name": "main"}, "commit": {"hash": "aaaaaaaaaaaa"}},
        "links": {"html": {"href": "https://evil.example/phish"}},
    }
    return payload | overrides


def test_pull_request_list_maps_fields_and_filters_by_state():
    fake = FakeBitbucket({f"{REPO}/pullrequests": js({"values": [pull_request(), pull_request(8, state="SUPERSEDED")]})})
    first, second = fake.provider().list_pull_requests(LEDGER, "open")
    assert fake.requests[0].url.params["state"] == "OPEN"
    assert (first.id, first.title, first.state, first.author) == ("7", "Tighten auth", "open", "Sam Dev")
    assert (first.source_ref, first.target_ref) == ("feature/auth", "main")
    assert first.url == "https://bitbucket.org/acme/ledger/pull-requests/7"  # not the payload's link
    assert first.source_sha is None and first.target_sha is None  # list payload has short hashes only
    assert second.state == "declined"
    with pytest.raises(ScanError):
        fake.provider().list_pull_requests(LEDGER, "everything")


def test_get_pull_request_binds_both_sides_to_full_commit_shas():
    fake = FakeBitbucket({
        f"{REPO}/pullrequests/7": js(pull_request()),
        f"{REPO}/commit/bbbbbbbbbbbb": js({"hash": HEAD}),
        f"{REPO}/commit/aaaaaaaaaaaa": js({"hash": BASE}),
    })
    found = fake.provider().get_pull_request(LEDGER, "7")
    assert (found.source_sha, found.target_sha) == (HEAD, BASE)


def test_pull_request_from_an_unreadable_fork_leaves_the_head_sha_unset():
    fake = FakeBitbucket({
        f"{REPO}/pullrequests/7": js(pull_request()), f"{REPO}/commit/aaaaaaaaaaaa": js({"hash": BASE}),
    })
    found = fake.provider().get_pull_request(LEDGER, "7")
    assert found.source_sha is None and found.target_sha == BASE


def test_pull_request_id_is_validated_and_missing_or_malformed_ones_are_errors():
    fake = FakeBitbucket({f"{REPO}/pullrequests/9": js({"id": "9", "title": "x"})})
    provider = fake.provider()
    for bad in ("7/../../x", "-1", "abc", ""):
        with pytest.raises(ScanError):
            provider.get_pull_request(LEDGER, bad)
    assert fake.requests == []
    with pytest.raises(ProviderError, match="not found"):
        provider.get_pull_request(LEDGER, "404")
    with pytest.raises(ProviderError, match="unexpected"):
        provider.get_pull_request(LEDGER, "9")


# -- commits and changes -------------------------------------------------------

def test_resolve_commit_looks_up_branches_then_tags_then_hashes():
    def refs(kind, known):
        def route(request):
            name = request.url.params["q"].removeprefix('name = "').removesuffix('"')
            return js({"values": [{"name": name, "target": {"hash": known[name]}}] if name in known else []})
        return route

    fake = FakeBitbucket({
        f"{REPO}/refs/branches": refs("branches", {"feature/auth": HEAD}),
        f"{REPO}/refs/tags": refs("tags", {"v1.0": BASE}),
        f"{REPO}/commit/abc1234": js({"hash": "abc1234" + "0" * 33}),
        f"{REPO}/commit/{BASE}": js({"hash": BASE}),
    })
    provider = fake.provider()
    assert provider.resolve_commit(LEDGER, "feature/auth") == HEAD
    assert "feature/auth" not in "".join(fake.paths())  # the slash never enters the URL path
    assert provider.resolve_commit(LEDGER, "v1.0") == BASE
    assert provider.resolve_commit(LEDGER, "abc1234") == "abc1234" + "0" * 33
    assert provider.resolve_commit(LEDGER, BASE) == BASE
    for missing in ("nope", "deadbeef"):
        with pytest.raises(RefNotFound):
            provider.resolve_commit(LEDGER, missing)
    for invalid in ("--x", "a..b", 'x" OR name ~ "', ""):
        with pytest.raises(ScanError):
            provider.resolve_commit(LEDGER, invalid)


def test_changes_use_bitbucket_spec_order_and_a_two_dot_diff():
    fake = FakeBitbucket(compare_routes())
    changes = fake.provider().get_changes(LEDGER, BASE, HEAD)
    assert (changes.base_sha, changes.head_sha, changes.truncated, changes.omitted) == (BASE, HEAD, False, 0)
    assert [(f.status, f.path, f.additions, f.deletions) for f in changes.files] == [
        ("M", "app/auth.py", 0, 1), ("A", "docs/new file.md", 1, 0), ("D", "old.txt", 0, 1),
        ("M", "café.py", 1, 1), ("M", "run me.sh", 0, 0),
    ]
    patches = {f.path: f.patch for f in changes.files}
    assert "-    verify(user)" in patches["app/auth.py"] and "hello" not in patches["app/auth.py"]
    assert patches["docs/new file.md"].endswith("+hello\n")
    assert "+x = 2" in patches["café.py"]
    assert patches["run me.sh"].startswith("diff --git a/run me.sh") and "new mode" in patches["run me.sh"]
    for request in fake.requests[-2:]:
        assert request.url.path.endswith(f"{HEAD}..{BASE}")  # new..old, the reverse of git diff
        assert request.url.params["topic"] == "false" and request.url.params["renames"] == "false"


def test_no_changes_skips_the_diff_download():
    fake = FakeBitbucket(compare_routes(stats=[]))
    assert fake.provider().get_changes(LEDGER, BASE, HEAD).files == ()
    assert not any("/diff/" in path for path in fake.paths())


def test_a_rename_is_reported_as_a_delete_plus_an_add():
    stats = [{"status": "renamed", "lines_added": 2, "lines_removed": 1, "old": {"path": "a.py"}, "new": {"path": "b.py"}}]
    changes = FakeBitbucket(compare_routes(stats=stats, diff="")).provider().get_changes(LEDGER, BASE, HEAD)
    assert [(f.status, f.path) for f in changes.files] == [("D", "a.py"), ("A", "b.py")]


def test_more_files_than_the_cap_are_counted_as_omitted():
    routes = compare_routes()
    routes[f"{REPO}/diffstat/{HEAD}..{BASE}"] = js({"values": STATS, "size": 412, "next": f"{API}{REPO}/diffstat/x?page=2"})
    changes = FakeBitbucket(routes).provider().get_changes(LEDGER, BASE, HEAD, max_files=3)
    assert len(changes.files) == 3 and changes.truncated and changes.omitted == 409


def test_an_oversized_diff_drops_the_files_it_did_not_fully_cover(monkeypatch):
    monkeypatch.setattr(bitbucket, "MAX_DIFF_BYTES", DIFF.index("+hello"))  # cut inside the second file
    changes = FakeBitbucket(compare_routes()).provider().get_changes(LEDGER, BASE, HEAD)
    assert [f.path for f in changes.files] == ["app/auth.py"]
    assert changes.truncated and changes.omitted == 4
    assert changes.files[0].patch.endswith("     return True\n")  # the kept patch is complete


def test_bitbucket_diff_timeout_and_unknown_commits_are_reported():
    routes = compare_routes()
    routes[f"{REPO}/diff/{HEAD}..{BASE}"] = httpx.Response(555)
    with pytest.raises(ProviderError, match="too large"):
        FakeBitbucket(routes).provider().get_changes(LEDGER, BASE, HEAD)
    with pytest.raises(RefNotFound):
        FakeBitbucket().provider().get_changes(LEDGER, BASE, HEAD)


def test_split_patches_handles_empty_and_unparseable_input():
    assert split_patches("") == {}
    assert split_patches("not a diff\n") == {}
    assert list(split_patches(DIFF, cut=True)) == ["app/auth.py", "docs/new file.md", "old.txt", "café.py"]


# -- tree and file access ------------------------------------------------------

def test_list_files_pages_through_the_tree_and_returns_files_only():
    fake = FakeBitbucket({f"{REPO}/src/{HEAD}/": [
        js({"values": [{"type": "commit_directory", "path": "app"}, {"type": "commit_file", "path": "app/auth.py"}],
            "next": f"{API}{REPO}/src/{HEAD}/?page=2"}),
        js({"values": [{"type": "commit_file", "path": "README.md"}, {"type": "commit_file", "path": 5}]}),
    ]})
    assert fake.provider().list_files(LEDGER, HEAD) == ["app/auth.py", "README.md"]
    with pytest.raises(ScanError):
        fake.provider().list_files(LEDGER, "main")
    with pytest.raises(RefNotFound):
        FakeBitbucket().provider().list_files(LEDGER, BASE)


def test_read_file_returns_text_and_treats_absent_or_unsafe_paths_as_empty(monkeypatch):
    fake = FakeBitbucket({
        f"{REPO}/src/{HEAD}/app/auth.py": httpx.Response(200, content=b"x = '\xff'\n"),
        f"{REPO}/src/{HEAD}/big.bin": httpx.Response(200, content=b"z" * 64),
        f"{REPO}/src/{HEAD}/model.lfs": httpx.Response(301, headers={"Location": "https://media.example/x"}),
        f"{REPO}/src/{HEAD}/a b?.py": httpx.Response(200, text="ok"),
    })
    provider = fake.provider()
    assert provider.read_file(LEDGER, HEAD, "app/auth.py") == "x = '�'\n"
    assert provider.read_file(LEDGER, HEAD, "a b?.py") == "ok"  # quoted into the path, not the query
    assert provider.read_file(LEDGER, HEAD, "missing.py") == ""
    assert provider.read_file(LEDGER, HEAD, "model.lfs") == ""  # LFS redirect is not followed
    monkeypatch.setattr(bitbucket, "MAX_FILE_BYTES", 16)
    assert provider.read_file(LEDGER, HEAD, "big.bin") == ""
    before = len(fake.requests)
    for unsafe in ("../../other/src/x", "/etc/passwd", "a//b", "a/./b", "a\x00b", ""):
        assert provider.read_file(LEDGER, HEAD, unsafe) == ""
    assert provider.read_file(LEDGER, "main", "app/auth.py") == ""
    assert len(fake.requests) == before  # none of those reached Bitbucket


def test_read_file_does_not_hide_an_authentication_failure():
    fake = FakeBitbucket({f"{REPO}/src/{HEAD}/app/auth.py": js({}, 401)})
    with pytest.raises(ProviderAuthError):
        fake.provider().read_file(LEDGER, HEAD, "app/auth.py")


# -- scan orchestration --------------------------------------------------------

def test_scan_orchestration_runs_against_bitbucket_and_only_issues_get_requests():
    before = "def check(user):\n    verify(user)\n    return True\n"
    after = "def check(user):\n    return True\n"
    fake = FakeBitbucket(compare_routes(
        stats=STATS[:1], diff=DIFF[:DIFF.index("diff --git a/docs")],
        **{
            f"{REPO}/src/{BASE}/app/auth.py": httpx.Response(200, text=before),
            f"{REPO}/src/{HEAD}/app/auth.py": httpx.Response(200, text=after),
            f"{REPO}/src/{HEAD}/": js({"values": [{"type": "commit_file", "path": "app/auth.py"}]}),
        },
    ))
    report = scan_changes(fake.provider(), LEDGER, BASE, HEAD)
    assert (report["base_sha"], report["head_sha"]) == (BASE[:12], HEAD[:12])
    assert report["summary"]["files_changed"] == 1 and report["summary"]["truncated"] is False
    assert report["files"][0]["path"] == "app/auth.py"
    assert {request.method for request in fake.requests} == {"GET"}
    assert {request.url.host for request in fake.requests} == {"api.bitbucket.org"}
    assert all(TOKEN not in str(request.url) for request in fake.requests)


# -- pull request list: truncation -------------------------------------------

def test_pull_request_list_reports_truncation_only_when_items_were_left_out(monkeypatch):
    monkeypatch.setattr(bitbucket, "MAX_PULL_REQUESTS", 2)
    path = f"{REPO}/pullrequests"

    def listed(payload):
        return FakeBitbucket({path: js(payload)}).provider().list_pull_requests_page(LEDGER)

    below, cut = listed({"values": [pull_request(1)], "size": 1})
    assert ([pr.id for pr in below], cut) == (["1"], False)
    exact, cut = listed({"values": [pull_request(1), pull_request(2)], "size": 2})
    assert ([pr.id for pr in exact], cut) == (["1", "2"], False)        # exactly at the limit: complete
    over, cut = listed({"values": [pull_request(1), pull_request(2), pull_request(3)], "size": 3})
    assert ([pr.id for pr in over], cut) == (["1", "2"], True)          # one more than the limit
    # Bitbucket omits "size" on some listings; a further page is then the only sign.
    more, cut = listed({"values": [pull_request(1), pull_request(2)], "next": f"{API}{path}?page=2"})
    assert ([pr.id for pr in more], cut) == (["1", "2"], True)


def test_pull_request_list_is_unchanged_and_agrees_with_the_paged_form(monkeypatch):
    monkeypatch.setattr(bitbucket, "MAX_PULL_REQUESTS", 2)
    fake = FakeBitbucket({f"{REPO}/pullrequests": js({"values": [pull_request(1), pull_request(2), pull_request(3)]})})
    plain = fake.provider().list_pull_requests(LEDGER)
    assert isinstance(plain, list) and plain == fake.provider().list_pull_requests_page(LEDGER)[0]


def test_default_pull_request_limit_is_200():
    assert bitbucket.MAX_PULL_REQUESTS == 200
