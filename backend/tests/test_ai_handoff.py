"""Contract tests for the manual Claude Code workflow. No Claude account is required."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ai_handoff import SCHEMA_VERSION, MAX_IMPORT_BYTES


@pytest.fixture()
def scanned_client(tmp_path):
    repo = tmp_path / "demo"
    app = create_app(demo_root=repo, db_file=tmp_path / "data" / "scans.db", allowed_root=repo)
    with TestClient(app) as client:
        response = client.post('/api/scans', json={"base_ref": "main", "head_ref": "feature/release-candidate"})
        assert response.status_code == 201, response.text
        yield client, response.json()


def handoff(client, scan_id):
    response = client.get(f'/api/scans/{scan_id}/ai/handoff')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/zip'
    assert 'attachment' in response.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert names == {'review-input.json', 'REVIEW_INSTRUCTIONS.md', 'response-template.json'}
        source = json.loads(archive.read('review-input.json'))
        template = json.loads(archive.read('response-template.json'))
        instructions = archive.read('REVIEW_INSTRUCTIONS.md').decode()
    return source, template, instructions


def valid_review(report, source):
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_id": report['id'],
        "context_digest": source['context_digest'],
        "summary": "Some changes appear to increase release risk; manual review is strongly recommended.",
        "recommendation": "manual_review",
        "findings": [{
            "title": "Ownership guard appears removed",
            "severity": "critical",
            "category": "Security",
            "file": report['files'][0]['path'],
            "line": None,
            "evidence": "A permission-related guard is absent from the changed code.",
            "rationale": "The diff appears to remove an ownership check, but runtime behavior was not tested.",
            "recommendation": "Test cross-account data access before approving the release.",
            "confidence": "medium",
            "related_static_finding_ids": [],
        }],
        "test_ideas": [{
            "title": "Reject another user's read",
            "scenario": "Log in as a second synthetic user and attempt to read the first user's invoice.",
            "expected_behavior": "The API rejects the read and does not reveal the invoice.",
            "file": report['files'][0]['path'],
        }],
        "limitations": ["The handoff includes truncated diffs and has no runtime test evidence."],
    }


def test_bundle_includes_real_evidence_and_binds_to_scan(scanned_client):
    client, report = scanned_client
    source, template, instructions = handoff(client, report['id'])
    assert source['schema_version'] == SCHEMA_VERSION
    assert source['review_context']['scan_id'] == report['id']
    assert source['review_context']['base_sha'] == report['base_sha']
    assert source['review_context']['files'][0]['diff'] == report['files'][0]['diff']
    assert len(source['review_context']['static_findings']) == 3
    assert len(source['context_digest']) == 64
    assert template['context_digest'] == source['context_digest']
    assert 'No tests were executed' in instructions or 'Do not claim code execution' in instructions
    assert 'API key' not in json.dumps(source)


def test_import_roundtrip_persists_separately_and_does_not_change_scan(scanned_client):
    client, report = scanned_client
    source, _, _ = handoff(client, report['id'])
    body = valid_review(report, source)
    url = f"/api/scans/{report['id']}/ai/reviews"
    posted = client.post(url, json=body)
    assert posted.status_code == 201, posted.text
    saved = posted.json()
    assert saved['verification_status'] == 'not_independently_verified'
    assert saved['source'] == 'user_imported_json_unverified_provenance'
    assert saved['tests_executed'] is False
    assert saved['findings'][0]['title'] == body['findings'][0]['title']
    assert client.get(url).json()[0]['id'] == saved['id']
    assert client.get(url + '/latest').json()['id'] == saved['id']
    assert client.get(f"/api/scans/{report['id']}").json() == report
    assert client.get(f"/api/scans/{report['id']}/export").json() == report
    assert client.get('/api/scans').json()[0]['summary']['test_status'] == 'not_run'


def test_multiple_imports_have_history_and_latest(scanned_client):
    client, report = scanned_client
    source, _, _ = handoff(client, report['id'])
    path = f"/api/scans/{report['id']}/ai/reviews"
    first = client.post(path, json=valid_review(report, source)).json()
    second_review = valid_review(report, source)
    second_review['summary'] = "Second review: checking the same evidence and suggesting more targeted investigation."
    second = client.post(path, json=second_review).json()
    records = client.get(path).json()
    assert len(records) == 2
    assert records[0]['id'] == second['id']
    assert records[1]['id'] == first['id']


@pytest.mark.parametrize('tamper,status', [
    ('scan_id', 409),
    ('context_digest', 409),
    ('bad_file', 409),
    ('bad_static_id', 409),
    ('extra_field', 422),
    ('fabricated_test_results', 422),
    ('missing_summary', 422),
])
def test_invalid_or_mismatched_import_is_rejected(scanned_client, tamper, status):
    client, report = scanned_client
    source, _, _ = handoff(client, report['id'])
    body = valid_review(report, source)
    if tamper == 'scan_id':
        body['scan_id'] = '12345678-1111-2222-3333-444444444444'
    elif tamper == 'context_digest':
        body['context_digest'] = '0' * 64
    elif tamper == 'bad_file':
        body['findings'][0]['file'] = '../../private.py'
    elif tamper == 'bad_static_id':
        body['findings'][0]['related_static_finding_ids'] = ['made-up-id']
    elif tamper == 'extra_field':
        body['unrecognized_field'] = True
    elif tamper == 'fabricated_test_results':
        body['tests_executed'] = True
    elif tamper == 'missing_summary':
        body.pop('summary')
    result = client.post(f"/api/scans/{report['id']}/ai/reviews", json=body)
    assert result.status_code == status, result.text
    assert client.get(f"/api/scans/{report['id']}/ai/reviews").json() == []


def test_overlarge_import_rejected(scanned_client):
    client, report = scanned_client
    url = f"/api/scans/{report['id']}/ai/reviews"
    assert client.post(url, content=b' ' * (MAX_IMPORT_BYTES + 1), headers={'Content-Type': 'application/json'}).status_code == 413


def test_unknown_scan_has_no_handoff_or_reviews(scanned_client):
    client, _ = scanned_client
    unknown = '12345678-1111-2222-3333-444444444444'
    assert client.get(f'/api/scans/{unknown}/ai/handoff').status_code == 404
    assert client.get(f'/api/scans/{unknown}/ai/reviews').status_code == 404
    assert client.post(f'/api/scans/{unknown}/ai/reviews', json={}).status_code == 404


def test_no_review_returns_null(scanned_client):
    client, report = scanned_client
    assert client.get(f"/api/scans/{report['id']}/ai/reviews/latest").json() is None
