"""Phase 7: static pattern rules for Dart, JavaScript/TypeScript, Kotlin and Java.

Every fixture is synthetic code written for these tests; none comes from a
real repository. Each rule has, per language it claims, one change that must
be flagged and one similar change that must not be."""
import ast
import difflib
import subprocess
from pathlib import Path

import pytest

from app import pattern_rules
from app.pattern_rules import RULES, analyze_patterns, is_test_path, language_of, parse_patch
from app.scanner import scan_repository


def patch_of(before: str, after: str) -> str:
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), "a/x", "b/x", lineterm="", n=3)
    return "\n".join(lines)


def findings(path: str, before: str, after: str) -> list[dict]:
    return analyze_patterns(path, before, after, patch_of(before, after))


def rule_ids(path: str, before: str, after: str) -> list[str]:
    return [item["rule_id"].removeprefix("shipsafe.") for item in findings(path, before, after)]


DART_CLIENT = "import 'dart:io';\n\nHttpClient buildClient() {\n  final client = HttpClient();\n  return client;\n}\n"
TS_CLIENT = "import https from 'https'\n\nexport const agent = new https.Agent({ keepAlive: true })\n"
KT_CLIENT = "fun client(): OkHttpClient {\n    return OkHttpClient.Builder()\n        .build()\n}\n"
JAVA_CLIENT = "class Net {\n    HttpsURLConnection open(URL url) throws Exception {\n        HttpsURLConnection c = (HttpsURLConnection) url.openConnection();\n        return c;\n    }\n}\n"

DART_STATUS = "PaymentStatus parseStatus(String? raw) {\n  switch (raw) {\n    case 'paid':\n      return PaymentStatus.success;\n    case 'failed':\n      return PaymentStatus.failed;\n    default:\n      return PaymentStatus.failed;\n  }\n}\n"
TS_STATUS = "export function paymentStatus(raw?: string): Status {\n  return (raw as Status) ?? 'failed'\n}\n"
KT_STATUS = "fun paymentStatus(raw: String?): Status = when (raw) {\n    \"paid\" -> Status.SUCCESS\n    else -> Status.FAILED\n}\n"
JAVA_STATUS = "class PaymentMapper {\n    Status map(String raw) {\n        switch (raw) {\n            case \"paid\": return Status.SUCCESS;\n            default: return Status.FAILED;\n        }\n    }\n}\n"

DART_RETURN = "bool isTrustedReturnUrl(String returnUrl) {\n  final uri = Uri.parse(returnUrl);\n  if (uri.host != 'pay.example.test') {\n    return false;\n  }\n  return uri.scheme == 'https';\n}\n"
TS_RETURN = "export function openReturnUrl(returnUrl: string) {\n  const url = new URL(returnUrl)\n  if (!allowedHosts.includes(url.hostname)) throw new Error('untrusted')\n  window.location.assign(url.toString())\n}\n"

DART_IDEM = "class PaymentApi {\n  PaymentApi(this.idempotencyKey);\n  final String idempotencyKey;\n\n  Future<void> pay(int amount) {\n    return http.post(url, headers: {'Idempotency-Key': idempotencyKey}, body: '$amount');\n  }\n}\n"
TS_IDEM = "export async function pay(amount: number, idempotencyKey: string) {\n  return fetch(url, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: String(amount) })\n}\n"
KT_IDEM = "class PaymentApi(private val idempotencyKey: String) {\n    fun pay(amount: Int) = client.post(url) {\n        header(\"Idempotency-Key\", idempotencyKey)\n    }\n}\n"

DART_BUTTON = "class PayButton extends StatelessWidget {\n  Widget build(BuildContext context) {\n    return ElevatedButton(\n      onPressed: isLoading ? null : onPay,\n      child: const Text('Pay'),\n    );\n  }\n}\n"
TSX_BUTTON = "export function PayButton({ onPay, isSubmitting }: Props) {\n  return <button disabled={isSubmitting} onClick={onPay}>Pay</button>\n}\n"

CASES = [
    # rule, path, before, after (flagged), after (not flagged)
    ("tls-validation-disabled", "lib/net/client.dart", DART_CLIENT,
     DART_CLIENT.replace("  return client;", "  client.badCertificateCallback = (cert, host, port) => true;\n  return client;"),
     DART_CLIENT.replace("  return client;", "  client.connectionTimeout = const Duration(seconds: 10);\n  return client;")),
    ("tls-validation-disabled", "lib/net/client2.dart", DART_CLIENT,
     DART_CLIENT.replace("  return client;", "  client.badCertificateCallback = (cert, host, port) {\n    return true;\n  };\n  return client;"),
     DART_CLIENT.replace("  return client;", "  client.badCertificateCallback = (cert, host, port) => pinned.matches(cert);\n  return client;")),
    ("tls-validation-disabled", "src/net/agent.ts", TS_CLIENT,
     TS_CLIENT.replace("keepAlive: true", "keepAlive: true, rejectUnauthorized: false"),
     TS_CLIENT.replace("keepAlive: true", "keepAlive: true, rejectUnauthorized: true")),
    ("tls-validation-disabled", "src/net/env.js", "const port = 3000\n",
     "const port = 3000\nprocess.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'\n", "const port = 3000\nprocess.env.NODE_ENV = 'production'\n"),
    ("tls-validation-disabled", "app/src/main/kotlin/Net.kt", KT_CLIENT,
     KT_CLIENT.replace("        .build()", "        .hostnameVerifier { _, _ -> true }\n        .build()"),
     KT_CLIENT.replace("        .build()", "        .connectTimeout(10, TimeUnit.SECONDS)\n        .build()")),
    ("tls-validation-disabled", "src/main/java/Net.java", JAVA_CLIENT,
     JAVA_CLIENT.replace("        return c;", "        c.setHostnameVerifier((host, session) -> true);\n        return c;"),
     JAVA_CLIENT.replace("        return c;", "        c.setConnectTimeout(10000);\n        return c;")),

    ("payment-status-fails-open", "lib/payment/status.dart", DART_STATUS,
     DART_STATUS.replace("    default:\n      return PaymentStatus.failed;", "    default: return PaymentStatus.success;"),
     DART_STATUS.replace("    default:\n      return PaymentStatus.failed;", "    default: return PaymentStatus.pending;")),
    ("payment-status-fails-open", "src/payment/status.ts", TS_STATUS,
     TS_STATUS.replace("?? 'failed'", "?? Status.success"), TS_STATUS.replace("?? 'failed'", "?? Status.unknown")),
    ("payment-status-fails-open", "app/src/main/kotlin/PaymentStatus.kt", KT_STATUS,
     KT_STATUS.replace("else -> Status.FAILED", "else -> Status.SUCCESS"), KT_STATUS.replace("else -> Status.FAILED", "else -> Status.PENDING")),
    ("payment-status-fails-open", "src/main/java/PaymentMapper.java", JAVA_STATUS,
     JAVA_STATUS.replace("default: return Status.FAILED;", "default: return Status.SUCCESS;"),
     JAVA_STATUS.replace("default: return Status.FAILED;", "default: return Status.UNKNOWN;")),

    ("return-url-host-check-removed", "lib/payment/return_url.dart", DART_RETURN,
     DART_RETURN.replace("  if (uri.host != 'pay.example.test') {\n    return false;\n  }\n", ""),
     DART_RETURN.replace("  if (uri.host != 'pay.example.test') {\n    return false;\n  }\n", "  if (uri.host != trustedHost) {\n    return false;\n  }\n")),
    ("return-url-host-check-removed", "src/payment/returnUrl.ts", TS_RETURN,
     TS_RETURN.replace("  if (!allowedHosts.includes(url.hostname)) throw new Error('untrusted')\n", ""),
     TS_RETURN.replace("throw new Error('untrusted')", "throw new UntrustedHostError(url.hostname)")),

    ("idempotency-key-regenerated", "lib/payment/api.dart", DART_IDEM,
     DART_IDEM.replace("{'Idempotency-Key': idempotencyKey}", "{'Idempotency-Key': const Uuid().v4()}"),
     DART_IDEM.replace("body: '$amount'", "body: '${amount * 100}'")),
    ("idempotency-key-regenerated", "src/payment/api.ts", TS_IDEM,
     TS_IDEM.replace("'Idempotency-Key': idempotencyKey", "'Idempotency-Key': crypto.randomUUID()"),
     TS_IDEM.replace("body: String(amount)", "body: JSON.stringify({ amount })")),
    ("idempotency-key-regenerated", "app/src/main/kotlin/PaymentApi.kt", KT_IDEM,
     KT_IDEM.replace("header(\"Idempotency-Key\", idempotencyKey)", "header(\"Idempotency-Key\", UUID.randomUUID().toString())"),
     KT_IDEM.replace("client.post(url)", "client.post(paymentUrl)")),

    ("submit-without-busy-guard", "lib/widgets/pay_button.dart", DART_BUTTON,
     DART_BUTTON.replace("onPressed: isLoading ? null : onPay,", "onPressed: onPay,"),
     DART_BUTTON.replace("const Text('Pay')", "const Text('Pay now')")),
    ("submit-without-busy-guard", "lib/widgets/order_button.dart", "class OrderButton extends StatelessWidget {\n}\n",
     "class OrderButton extends StatelessWidget {\n  Widget build(BuildContext context) {\n    return ElevatedButton(\n      onPressed: () async {\n        await api.submitOrder(cart);\n      },\n      child: const Text('Order'),\n    );\n  }\n}\n",
     "class OrderButton extends StatelessWidget {\n  Widget build(BuildContext context) {\n    return ElevatedButton(\n      onPressed: isLoading ? null : () async {\n        await api.submitOrder(cart);\n      },\n      child: const Text('Order'),\n    );\n  }\n}\n"),
    ("submit-without-busy-guard", "src/components/PayButton.tsx", TSX_BUTTON,
     TSX_BUTTON.replace("disabled={isSubmitting} ", ""), TSX_BUTTON.replace(">Pay<", ">Pay now<")),

    ("cleartext-endpoint", "lib/config/api.dart", "const timeout = 30;\n",
     "const timeout = 30;\nconst baseUrl = 'http://api.payments.invalid/v1';\n", "const timeout = 30;\nconst baseUrl = 'https://api.payments.invalid/v1';\n"),
    ("cleartext-endpoint", "src/config.js", "export const timeout = 30\n",
     "export const timeout = 30\nexport const api = \"http://gateway.internal.invalid\"\n", "export const timeout = 30\nexport const api = \"http://localhost:8080\"\n"),

    ("verification-bypass", "lib/auth/guard.dart", "bool canOpen(User user) {\n  return user.isVerified;\n}\n",
     "bool canOpen(User user) {\n  return user.isVerified || true;\n}\n", "bool canOpen(User user) {\n  return user.isVerified || user.isAdmin;\n}\n"),
    ("verification-bypass", "src/main/java/Guard.java", "class Guard {\n    boolean verifySignature = true;\n}\n",
     "class Guard {\n    boolean verifySignature = true;\n    boolean skipSignatureCheck = true;\n}\n",
     "class Guard {\n    boolean verifySignature = true;\n    boolean logSignatureCheck = true;\n}\n"),

    ("empty-catch-in-sensitive-path", "lib/payment/confirm.dart", "Future<void> confirm() async {\n  await api.confirmPayment();\n}\n",
     "Future<void> confirm() async {\n  try {\n    await api.confirmPayment();\n  } catch (_) {}\n}\n",
     "Future<void> confirm() async {\n  try {\n    await api.confirmPayment();\n  } catch (error) { report(error); rethrow; }\n}\n"),
    ("empty-catch-in-sensitive-path", "src/auth/login.ts", "export async function login() {\n  await api.login()\n}\n",
     "export async function login() {\n  try { await api.login() } catch (e) {}\n}\n",
     "export async function login() {\n  try { await api.login() } catch (e) { notify(e); throw e }\n}\n"),
]


@pytest.mark.parametrize("rule,path,before,flagged,_clean", CASES, ids=[f"{case[0]}:{case[1]}" for case in CASES])
def test_the_pattern_is_flagged_with_file_line_rule_id_and_severity(rule, path, before, flagged, _clean):
    found = [item for item in findings(path, before, flagged) if item["rule_id"] == f"shipsafe.{rule}"]
    assert len(found) == 1, rule_ids(path, before, flagged)
    finding = found[0]
    expected = next(item for item in RULES if item.id == f"shipsafe.{rule}")
    assert finding["file"] == path and finding["severity"] == expected.severity and finding["title"] == expected.title
    assert finding["source"] == "pattern-rules" and finding["status"] == "suspected" and finding["language"] == language_of(path)
    assert finding["evidence"] and "not a confirmed defect" in finding["explanation"]
    lines = flagged.splitlines()
    assert isinstance(finding["line"], int) and 1 <= finding["line"] <= len(lines)
    if finding["evidence"] in flagged:
        assert finding["evidence"] in lines[finding["line"] - 1]  # an added line: the number points at it
    else:
        assert finding["evidence"] in before                         # a removed line: the number is where it was removed


@pytest.mark.parametrize("rule,path,before,_flagged,clean", CASES, ids=[f"{case[0]}:{case[1]}" for case in CASES])
def test_a_similar_change_without_the_pattern_is_not_flagged(rule, path, before, _flagged, clean):
    assert rule_ids(path, before, clean) == []


def test_every_rule_has_a_flagged_and_a_clean_fixture_and_the_languages_it_claims_are_covered():
    covered = {case[0] for case in CASES}
    assert covered == {rule.id.removeprefix("shipsafe.") for rule in RULES} and len(RULES) == 8
    tls_languages = {language_of(case[1]) for case in CASES if case[0] == "tls-validation-disabled"}
    assert tls_languages == {"dart", "typescript", "javascript", "kotlin", "java"}
    assert len({rule.id for rule in RULES}) == len(RULES)
    assert {rule.severity for rule in RULES} <= {"critical", "high", "medium", "low"}


# -- what the rules must leave alone ---------------------------------------------

def test_unchanged_lines_comments_tests_python_and_other_files_are_not_flagged():
    bad = "client.badCertificateCallback = (cert, host, port) => true;\n"
    # Already there before the change: not this change's doing.
    assert findings("lib/net/client.dart", DART_CLIENT + bad, DART_CLIENT + bad + "final x = 1;\n") == []
    # Only mentioned in a comment.
    assert findings("lib/net/client.dart", DART_CLIENT, DART_CLIENT + "// never set badCertificateCallback = (c, h, p) => true;\n") == []
    # Test code, Python, and files the rules do not read.
    for path in ("test/net/client_test.dart", "src/net/agent.test.ts", "src/__tests__/agent.ts", "app/src/test/kotlin/NetTest.kt",
                 "app/net.py", "README.md", "config/settings.yaml", "ios/Runner/AppDelegate.swift"):
        assert findings(path, "", bad) == [], path
    assert is_test_path("integration_test/pay_test.dart") and not is_test_path("lib/latest/contest.dart")
    assert language_of("lib/a.DART") == "dart" and language_of("a.py") is None and language_of("Makefile") is None


def test_one_finding_per_rule_per_file_and_an_oversized_file_is_skipped(monkeypatch):
    twice = DART_CLIENT + "a.badCertificateCallback = (c, h, p) => true;\nb.badCertificateCallback = (c, h, p) => true;\n"
    assert rule_ids("lib/net/client.dart", DART_CLIENT, twice) == ["tls-validation-disabled"]
    monkeypatch.setattr(pattern_rules, "MAX_FILE_CHARS", 20)
    assert findings("lib/net/client.dart", DART_CLIENT, twice) == []


def test_parse_patch_gives_new_file_line_numbers():
    before, after = "a\nb\nc\nd\n", "a\nB\nc\nd\ne\n"
    added, removed = parse_patch(patch_of(before, after))
    assert added == ((2, "B"), (5, "e")) and removed == ((2, "b"),)
    assert parse_patch("") == ((), ()) and parse_patch("not a diff\n+orphan") == ((), ())


def test_hostile_text_is_only_matched_never_run(tmp_path):
    marker = tmp_path / "executed"
    hostile = f"import 'dart:io';\nvoid main() {{ File({str(marker)!r}).writeAsStringSync('x'); }}\n" + "(" * 5000 + "\x00\n"
    assert isinstance(findings("lib/evil.dart", "", hostile), list)
    assert not marker.exists()


def test_the_module_cannot_execute_code_start_a_process_or_use_the_network():
    tree = ast.parse(Path(pattern_rules.__file__).read_text(encoding="utf-8"))
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported == {"__future__", "re", "dataclasses", "pathlib", "uuid"}
    assert not called & {"exec", "eval", "compile", "__import__", "open"}


# -- through a real scan of a throwaway Git repository ----------------------------

def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    """A synthetic repository: `main` plus one branch per kind of change."""
    root = tmp_path / "synthetic-app"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")

    def write(files: dict[str, str]):
        for name, text in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def branch(name: str, files: dict[str, str]):
        git(root, "switch", "-q", "-c", name, "main")
        write(files)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", name)

    write({"lib/net/client.dart": DART_CLIENT, "src/net/agent.ts": TS_CLIENT, "app/pricing.py": "def total(a):\n    return a\n",
           "README.md": "# Synthetic app\n"})
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    branch("dart-tls", {"lib/net/client.dart": CASES[0][3]})
    branch("ts-tls", {"src/net/agent.ts": CASES[2][3]})
    branch("dart-clean", {"lib/net/client.dart": CASES[0][4]})
    branch("python-only", {"app/pricing.py": "def total(a):\n    return a * 2\n"})
    branch("docs-only", {"README.md": "# Synthetic app\n\nMore words.\n"})
    return root


@pytest.mark.parametrize("head,path,line", [("dart-tls", "lib/net/client.dart", 5), ("ts-tls", "src/net/agent.ts", 3)])
def test_a_scan_reports_the_finding_counts_it_and_keeps_it_out_of_the_score(repo, head, path, line):
    report = scan_repository(repo, "main", head)
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert (finding["file"], finding["line"], finding["rule_id"], finding["severity"], finding["source"]) == (
        path, line, "shipsafe.tls-validation-disabled", "critical", "pattern-rules")
    summary = report["summary"]
    assert summary["finding_count"] == 1
    assert summary["risk_score"] == 3  # the score of a change with no scored finding: the pattern finding adds nothing
    assert summary["pattern_rules"] == {"engine": "builtin-line-patterns", "rule_count": 8, "files_analysed": 1,
                                        "files_skipped": 0, "finding_count": 1, "in_risk_score": False}
    assert summary["test_status"] == "not_run" and "No repository code or tests were executed" in report["disclaimer"]


def test_a_change_without_a_pattern_gets_no_finding_but_says_the_file_was_read(repo):
    report = scan_repository(repo, "main", "dart-clean")
    assert report["findings"] == [] and report["summary"]["finding_count"] == 0
    assert report["summary"]["pattern_rules"]["files_analysed"] == 1 and report["summary"]["pattern_rules"]["finding_count"] == 0


@pytest.mark.parametrize("head", ["python-only", "docs-only"])
def test_reports_without_a_readable_file_keep_their_earlier_shape(repo, head):
    report = scan_repository(repo, "main", head)
    assert "pattern_rules" not in report["summary"] and report["findings"] == []


def test_files_beyond_the_read_limit_are_counted_as_skipped(repo, monkeypatch):
    from app import scanner
    monkeypatch.setattr(scanner, "MAX_PATTERN_FILES", 0)
    report = scan_repository(repo, "main", "dart-tls")
    assert report["findings"] == []
    assert report["summary"]["pattern_rules"]["files_analysed"] == 0 and report["summary"]["pattern_rules"]["files_skipped"] == 1


def test_the_python_demo_scan_is_unchanged(tmp_path):
    from app.demo_seed import ensure_demo_repo
    demo = tmp_path / "demo"
    ensure_demo_repo(demo)
    report = scan_repository(demo, "main", "feature/release-candidate")
    assert len(report["findings"]) == 3 and "pattern_rules" not in report["summary"]
    assert all("source" not in item and "rule_id" not in item for item in report["findings"])
    assert report["summary"]["risk_score"] == min(99, sum({"critical": 42, "high": 26, "medium": 12, "low": 4}[f["severity"]] for f in report["findings"]) + 3)
