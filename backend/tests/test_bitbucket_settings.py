"""Phase 2 task 2: Bitbucket settings and credential loading.

No test here sends a request. The token below is a made-up test value, not a
credential.
"""
from __future__ import annotations

import json
import logging
import pickle
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from app.config import BitbucketSettings, Secret, load_settings
from app.errors import ConfigError
from app.main import create_app
from app.providers import BitbucketCloudProvider

TOKEN = "fake-test-token-0123456789"
FULL = {
    "SHIPSAFE_BITBUCKET_WORKSPACE": "acme",
    "SHIPSAFE_BITBUCKET_REPOSITORIES": "ledger, billing-api ,ledger",
    "SHIPSAFE_BITBUCKET_TOKEN": TOKEN,
}
NAMES = (*FULL, "SHIPSAFE_BITBUCKET_EMAIL")


def env(tmp_path, **changes):
    values = {**FULL, **changes, "SHIPSAFE_DEMO_DIR": str(tmp_path / "demo")}
    return {name: value for name, value in values.items() if value is not None}


@pytest.fixture()
def bitbucket_env(monkeypatch):
    def apply(**changes):
        for name in NAMES:
            monkeypatch.delenv(name, raising=False)
        for name, value in {**FULL, **changes}.items():
            if value is not None:
                monkeypatch.setenv(name, value)
    return apply


# -- load_settings -----------------------------------------------------------

def test_bitbucket_is_off_when_no_variable_is_set():
    assert load_settings(env={}).bitbucket is None


def test_empty_and_blank_bitbucket_variables_count_as_unset():
    assert load_settings(env={name: "  " for name in NAMES}).bitbucket is None


def test_full_configuration_is_loaded_and_normalised(tmp_path):
    bitbucket = load_settings(env=env(tmp_path)).bitbucket
    assert bitbucket == BitbucketSettings(
        workspace="acme", repositories=("ledger", "billing-api"), token=Secret(TOKEN), email=None,
    )
    assert bitbucket.token.reveal() == TOKEN


def test_optional_email_selects_basic_auth_settings(tmp_path):
    bitbucket = load_settings(env=env(tmp_path, SHIPSAFE_BITBUCKET_EMAIL=" dev@example.com ")).bitbucket
    assert bitbucket.email == "dev@example.com"


@pytest.mark.parametrize("missing", ["SHIPSAFE_BITBUCKET_WORKSPACE", "SHIPSAFE_BITBUCKET_REPOSITORIES", "SHIPSAFE_BITBUCKET_TOKEN"])
@pytest.mark.parametrize("blank", [None, "", "   "])
def test_partial_configuration_is_refused_and_names_what_is_missing(tmp_path, missing, blank):
    with pytest.raises(ConfigError) as error:
        load_settings(env=env(tmp_path, **{missing: blank}))
    assert missing in str(error.value)
    assert TOKEN not in str(error.value)


def test_email_alone_is_a_partial_configuration():
    with pytest.raises(ConfigError):
        load_settings(env={"SHIPSAFE_BITBUCKET_EMAIL": "dev@example.com"})


def test_repository_list_of_only_separators_is_refused(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(env=env(tmp_path, SHIPSAFE_BITBUCKET_REPOSITORIES=" , ,"))


@pytest.mark.parametrize("token", ["two words", "line\nbreak", "café-token"])
def test_token_that_cannot_be_a_header_is_refused_without_being_echoed(tmp_path, token):
    with pytest.raises(ConfigError) as error:
        load_settings(env=env(tmp_path, SHIPSAFE_BITBUCKET_TOKEN=token))
    assert token not in str(error.value)


@pytest.mark.parametrize("email", ["not-an-address", "a b@example.com", "a:b@example.com"])
def test_unusable_email_is_refused(tmp_path, email):
    with pytest.raises(ConfigError):
        load_settings(env=env(tmp_path, SHIPSAFE_BITBUCKET_EMAIL=email))


# -- the token stays secret --------------------------------------------------

def test_token_is_absent_from_every_text_form_of_the_settings(tmp_path):
    settings = load_settings(env=env(tmp_path))
    for text in (repr(settings), str(settings), repr(settings.bitbucket), repr(vars(settings.bitbucket)),
                 f"{settings.bitbucket.token}", "%s %r" % (settings.bitbucket.token, settings.bitbucket.token)):
        assert TOKEN not in text
    assert "acme" in repr(settings)  # the non-secret parts stay readable


def test_secret_cannot_be_copied_out_or_serialised(tmp_path):
    settings = load_settings(env=env(tmp_path))
    with pytest.raises(TypeError):
        asdict(settings)  # the usual first step of dumping settings to JSON
    with pytest.raises(TypeError):
        json.dumps(vars(settings.bitbucket))
    with pytest.raises(TypeError):
        pickle.dumps(settings.bitbucket.token)


# -- application startup -----------------------------------------------------

def test_app_starts_without_bitbucket_and_builds_no_provider(tmp_path, bitbucket_env):
    bitbucket_env(**{name: None for name in FULL})
    app = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db")
    assert app.state.bitbucket is None
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.post("/api/scans", json={}).status_code == 201  # local scanning is unchanged


def test_app_builds_the_provider_from_settings_without_any_request(tmp_path, bitbucket_env, monkeypatch):
    def no_network(*_args, **_kwargs):
        raise AssertionError("startup must not contact Bitbucket")
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", no_network)
    bitbucket_env(SHIPSAFE_BITBUCKET_WORKSPACE="Acme")
    app = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db")
    provider = app.state.bitbucket
    assert isinstance(provider, BitbucketCloudProvider)
    assert (provider.workspace, provider.repositories) == ("acme", ("ledger", "billing-api"))
    assert provider._client.headers["Authorization"] == f"Bearer {TOKEN}"
    assert provider._client.auth is None
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").status_code == 200


def test_app_uses_basic_auth_when_an_email_is_configured(tmp_path, bitbucket_env):
    bitbucket_env(SHIPSAFE_BITBUCKET_EMAIL="dev@example.com")
    provider = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db").state.bitbucket
    assert "Authorization" not in provider._client.headers
    assert provider._client.auth is not None


@pytest.mark.parametrize("changes", [
    {"SHIPSAFE_BITBUCKET_TOKEN": None},                    # workspace without a token
    {"SHIPSAFE_BITBUCKET_WORKSPACE": None},
    {"SHIPSAFE_BITBUCKET_REPOSITORIES": None},
    {"SHIPSAFE_BITBUCKET_WORKSPACE": "not a slug"},        # rejected by the provider
    {"SHIPSAFE_BITBUCKET_REPOSITORIES": "ledger,../etc"},
])
def test_app_refuses_to_start_on_partial_or_invalid_bitbucket_configuration(tmp_path, bitbucket_env, changes):
    bitbucket_env(**changes)
    with pytest.raises(ConfigError) as error:
        create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db")
    assert TOKEN not in str(error.value)


def test_token_never_reaches_logs_output_or_any_api_response(tmp_path, bitbucket_env, caplog, capsys):
    bitbucket_env(SHIPSAFE_BITBUCKET_EMAIL="dev@example.com")
    caplog.set_level(logging.DEBUG)
    app = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db")
    bodies = []
    with TestClient(app, base_url="http://127.0.0.1") as client:
        scan_id = client.post("/api/scans", json={}).json()["id"]
        get_paths = sorted(
            path.replace("{scan_id}", scan_id)
            for path, methods in client.get("/openapi.json").json()["paths"].items() if "get" in methods
        )
        assert len(get_paths) >= 9  # every GET route of the API, discovered rather than listed
        for path in ["/openapi.json", "/docs", *get_paths, "/api/scans/unknown", "/api/unknown"]:
            response = client.get(path)
            bodies.append(response.content + repr(response.headers).encode())
        bodies.append(client.post("/api/scans", json={"repository_path": "/nowhere"}).content)
        bodies.append(client.post(f"/api/scans/{scan_id}/ai/reviews", content=b"{").content)
    output = capsys.readouterr()
    assert TOKEN.encode() not in b"".join(bodies)
    assert TOKEN not in caplog.text
    assert TOKEN not in output.out + output.err
