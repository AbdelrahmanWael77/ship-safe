"""Phase 7: static pattern rules for languages other than Python.

A small built-in engine: each rule is a few regular expressions applied to the
lines a change adds or removes in Dart, JavaScript/TypeScript, Kotlin and Java
files. It reads text only. It never parses with, imports or runs anything from
the repository, starts no process and makes no network request, so it behaves
the same for a local scan and for a Bitbucket pull request scan.

What these rules are, and are not:

* They are line patterns, not a parser. They can miss a problem written in a
  way the pattern does not expect, and can flag code that is in fact fine.
* Every finding is a suspicion for a person to check, with the rule id, file,
  line and the matching line as evidence.
* Findings carry ``source: "pattern-rules"``. They are counted with the static
  findings and are **not** part of the risk score (see ``scanner.py``).

All rules are written for ShipSafe. No third-party rule set is included.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import uuid4

SOURCE = "pattern-rules"
ENGINE = "builtin-line-patterns"
#: A file larger than this is not analysed.
MAX_FILE_CHARS = 400_000

LANGUAGES = {
    ".dart": "dart",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".kt": "kotlin", ".kts": "kotlin",
    ".java": "java",
}
_TEST_PATH = re.compile(r"(^|/)(test|tests|__tests__|androidTest|integration_test|test_driver)/|(_test\.dart|\.(test|spec)\.[jt]sx?|Test\.(kt|java))$")
_COMMENT = re.compile(r"^\s*(//|/\*|\*|#)")


def language_of(path: str) -> str | None:
    """The language the rules read ``path`` as, or None when they do not read it."""
    return LANGUAGES.get(PurePosixPath(path).suffix.lower())


def is_test_path(path: str) -> bool:
    """Test code is not analysed: it holds deliberately unsafe values and stubs."""
    return bool(_TEST_PATH.search(path))


@dataclass(frozen=True)
class Change:
    """One file's change as the rules see it."""
    path: str
    language: str
    before: str
    after: str
    #: ``(line number in the new file, text)`` for every added line.
    added: tuple[tuple[int, str], ...]
    #: `(line number in the new file where the removal happened, text)` for every removed line.
    removed: tuple[tuple[int, str], ...]

    def code_added(self) -> list[tuple[int, str]]:
        return [(number, text) for number, text in self.added if text.strip() and not _COMMENT.match(text)]

    def code_removed(self) -> list[tuple[int, str]]:
        last = max(1, len(self.after.splitlines()))
        return [(min(max(number, 1), last), text) for number, text in self.removed if text.strip() and not _COMMENT.match(text)]


def parse_patch(patch: str) -> tuple[tuple[tuple[int, str], ...], tuple[tuple[int, str], ...]]:
    """Added lines with their new-file line numbers, and removed lines with the new-file
    line at which they were removed, from a unified diff."""
    added, removed, new_line = [], [], None
    for line in patch.splitlines():
        hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if new_line is None or line.startswith("+++") or line.startswith("---") or line.startswith("\\"):
            continue
        if line.startswith("+"):
            added.append((new_line, line[1:]))
            new_line += 1
        elif line.startswith("-"):
            removed.append((new_line, line[1:]))
        else:
            new_line += 1
    return tuple(added), tuple(removed)


# -- shared vocabulary ----------------------------------------------------------
_PAYMENT = re.compile(r"(?i)pay|checkout|transaction|invoice|order|purchase|billing|charge")
_PAYMENT_OR_AUTH = re.compile(r"(?i)pay|checkout|transaction|invoice|purchase|billing|charge|auth|login|token|session")
_SUCCESS = r"(?:success(?:ful)?|succeeded|paid|approved|completed|captured|ok)"
_GENERATOR = (r"(?:Uuid\(\)\.v\d\(|uuid\.v\d\(|uuidv?\d?\(|randomUUID\(|UUID\.randomUUID\(|DateTime\.now\(|Date\.now\(|"
              r"new Date\(|System\.currentTimeMillis\(|System\.nanoTime\(|Random\(|Math\.random\(|nanoid\()")
_BUSY = r"(?:_?is(?:Loading|Submitting|Busy|Processing|Saving|Paying)|_?(?:loading|submitting|processing|inProgress|busy))"
_HANDLER = r"(?:onPressed|onTap|onClick|onSubmit|onSubmitted|setOnClickListener)"
_HOST_CHECK = re.compile(
    r"(?i)(?:\.host\b|\.hostname\b|\.authority\b|\.origin\b|allowed_?hosts|trusted_?hosts|allow_?list|white_?list|allowed_?domains|allowed_?origins)"
    r".*(?:==|!=|contains\(|includes\(|startsWith\(|endsWith\(|indexOf\(|equals\(|\bin\b|has\()"
    r"|(?:contains\(|includes\(|has\().*(?:\.host\b|\.hostname\b|\.authority\b|\.origin\b)")
_RETURN_URL = re.compile(r"(?i)return_?url|redirect|callback_?url|success_?url|cancel_?url|next_?url|deep_?link|continue_?url")


def _first(lines: list[tuple[int, str]], pattern: re.Pattern[str]) -> tuple[int, str] | None:
    return next(((number, text) for number, text in lines if pattern.search(text)), None)


def _with_following(lines: list[tuple[int, str]], start: re.Pattern[str], then: re.Pattern[str], within: int) -> tuple[int, str] | None:
    """A line matching ``start`` whose own text, or one of the next ``within`` added lines, matches ``then``."""
    for index, (number, text) in enumerate(lines):
        if start.search(text) and any(then.search(later) for _, later in lines[index:index + within + 1]):
            return number, text
    return None


# -- rules ----------------------------------------------------------------------
# Each rule returns ``(line, evidence)`` for the first place it applies in the file, or None.

_TLS = {
    "dart": re.compile(r"badCertificateCallback"),
    "javascript": re.compile(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\W{0,4}=\s*['\"]?0|strictSSL\s*:\s*false"),
    "kotlin": re.compile(r"hostnameVerifier\s*[({]\s*\{?\s*_\s*,\s*_\s*->\s*true|setHostnameVerifier\s*\(.*->\s*true|ALLOW_ALL_HOSTNAME_VERIFIER|"
                         r"checkServerTrusted\s*\([^)]*\)\s*(?:=\s*Unit|\{\s*\})|(?i:trustAll(?:Certs|Certificates|Manager)?)\b"),
}
_TLS["typescript"] = _TLS["javascript"]
_TLS["java"] = re.compile(_TLS["kotlin"].pattern + r"|\(\s*\w+\s*,\s*\w+\s*\)\s*->\s*true\s*\)?\s*;.*(?i:verifier)|(?i:verifier).*\(\s*\w+\s*,\s*\w+\s*\)\s*->\s*true")
_TLS_DART_TRUE = re.compile(r"=>\s*true\b|return\s+true\b")


def tls_validation_disabled(change: Change):
    lines = change.code_added()
    if change.language == "dart":
        return _with_following(lines, _TLS["dart"], _TLS_DART_TRUE, within=2)
    return _first(lines, _TLS[change.language])


_FAIL_OPEN = re.compile(
    rf"(?i)\bdefault\s*:.*\b{_SUCCESS}\b"                          # switch default
    rf"|\belse\s*->.*\b{_SUCCESS}\b"                               # Kotlin when-else
    rf"|\?\?\s*[\w.]*\b{_SUCCESS}\b"                               # ?? default
    rf"|\?:\s*[\w.]*\b{_SUCCESS}\b"                                # Kotlin elvis
    rf"|\bcatch\b.*\breturn\s+(?:true|[\w.]*\b{_SUCCESS}\b)"       # catch { return success }
    rf"|\|\|\s*['\"]{_SUCCESS}['\"]"                               # || 'success'
)
_CATCH = re.compile(r"\bcatch\b")
_RETURN_SUCCESS = re.compile(rf"(?i)\breturn\s+(?:true|[\w.]*\b{_SUCCESS}\b)")
_STATUS_WORD = re.compile(r"(?i)status|state|result|paid|success|approved|completed")


def payment_status_fails_open(change: Change):
    if not (_PAYMENT.search(change.path) or _PAYMENT.search(change.after)):
        return None
    lines = change.code_added()
    hit = _first(lines, _FAIL_OPEN)
    if hit is None:
        # catch on one added line, "return <success>" on one of the next two
        for index, (number, text) in enumerate(lines):
            if _CATCH.search(text) and any(_RETURN_SUCCESS.search(later) for _, later in lines[index + 1:index + 3]):
                hit = (number, text)
                break
    if hit and (_STATUS_WORD.search(hit[1]) or _PAYMENT.search(hit[1]) or _PAYMENT.search(change.path)):
        return hit
    return None


def return_url_host_check_removed(change: Change):
    removed = [(number, text) for number, text in change.code_removed() if _HOST_CHECK.search(text)]
    if not removed:
        return None
    about_urls = _RETURN_URL.search(change.path) or _RETURN_URL.search(change.before) or _RETURN_URL.search(change.after)
    still_checked = any(_HOST_CHECK.search(line) and not _COMMENT.match(line) for line in change.after.splitlines())
    if about_urls and not still_checked:
        return removed[0]
    return None


_IDEMPOTENCY = re.compile(r"(?i)idempoten")
_INLINE_KEY = re.compile(rf"(?i)(?:['\"][\w-]*idempoten[\w-]*['\"]\s*[:,]|idempoten\w*\s*:(?!:)|idempoten\w*\s*\().*{_GENERATOR}")
_ASSIGNED_KEY = re.compile(rf"(?i)idempoten\w*\s*=(?!=).*{_GENERATOR}")
_GENERATOR_RE = re.compile(_GENERATOR)


def idempotency_key_regenerated(change: Change):
    lines = change.code_added()
    inline = _first(lines, _INLINE_KEY)      # a fresh key built where the request is sent
    if inline:
        return inline
    # A stored key that was being reused is now assigned a fresh value.
    reused_before = any(_IDEMPOTENCY.search(text) and not _GENERATOR_RE.search(text) for _, text in change.code_removed())
    return _first(lines, _ASSIGNED_KEY) if reused_before else None


_GUARDED_HANDLER = re.compile(rf"(?:{_HANDLER}|disabled|enabled|isEnabled|absorbing|ignoring)\b.*{_BUSY}|{_BUSY}.*\?\s*null\s*:")
_ASYNC_HANDLER = re.compile(rf"{_HANDLER}\s*[:=]\s*\{{?\s*(?:\([^)]*\)\s*)?async\b|{_HANDLER}\s*[:=]\s*\{{?\s*\(?[^)]*\)?\s*=>\s*(?:await\b|_?(?:submit|pay|checkout|confirm|placeOrder))")
_SUBMIT_WORD = re.compile(r"(?i)submit|pay|checkout|confirm|place_?order|purchase|transfer|send")
_BUSY_RE = re.compile(_BUSY)


def submit_without_busy_guard(change: Change):
    guard_removed = next(((number, text) for number, text in change.code_removed() if _GUARDED_HANDLER.search(text)), None)
    guarded_now = any(_GUARDED_HANDLER.search(line) for line in change.after.splitlines())
    if guard_removed and not guarded_now:
        return guard_removed
    if _BUSY_RE.search(change.after):
        return None                           # the file tracks a busy state somewhere
    lines = change.code_added()
    return _with_following(lines, _ASYNC_HANDLER, _SUBMIT_WORD, within=6)


_CLEARTEXT = re.compile(r"""['"`]http://(?!localhost\b|127\.0\.0\.1|10\.0\.2\.2|0\.0\.0\.0|\[::1\]|www\.w3\.org|schemas\.|json-schema\.org|xmlns|ns\.adobe\.com|example\.|[\w.-]*\.(?:test|local|example)\b)[\w.-]+""")


def cleartext_endpoint(change: Change):
    return _first(change.code_added(), _CLEARTEXT)


_BYPASS = re.compile(
    r"(?i)\b(?:skip|bypass|disable|ignore|no)_?\w*(?:verif|validat|auth|check|ssl|cert|signature)\w*\s*[:=]\s*true\b"
    r"|\b(?:verif\w*|validat\w*|check\w*|auth\w*)_?enabled\s*[:=]\s*false\b"
    r"|\bif\s*\(\s*(?:true|1\s*==\s*1)\s*\)"
    r"|\|\|\s*true\b(?!\s*[:=])"
)
_GUARDING = re.compile(r"(?i)verif|validat|auth|check|signature|permission|allowed|paid|status|skip|bypass|if\s*\(")


def verification_bypass(change: Change):
    hit = _first(change.code_added(), _BYPASS)
    return hit if hit and _GUARDING.search(hit[1]) else None


_EMPTY_CATCH = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}|\.catch\(\s*\(?\w*\)?\s*=>\s*\{\s*\}\s*\)|\.catchError\(\s*\(\w*\)\s*\{\s*\}\s*\)")


def empty_catch_in_sensitive_path(change: Change):
    if not (_PAYMENT_OR_AUTH.search(change.path) or _PAYMENT_OR_AUTH.search(change.after)):
        return None
    return _first(change.code_added(), _EMPTY_CATCH)


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    category: str
    title: str
    explanation: str
    recommendation: str
    check: object


RULES: tuple[Rule, ...] = (
    Rule("shipsafe.tls-validation-disabled", "critical", "Security", "TLS certificate or host validation disabled",
         "The change adds code that accepts any certificate or host name. Traffic to the server can then be read or altered by anyone on the network path.",
         "Remove the bypass. If a test server needs it, keep it out of release builds and prove that with a build flag a reviewer can see.",
         tls_validation_disabled),
    Rule("shipsafe.payment-status-fails-open", "high", "Payment integrity", "Payment status falls back to success",
         "An unknown, missing or failed payment status appears to be treated as a successful one (a default, fallback or catch branch yields success).",
         "Make the fallback a failure or a pending state, and test an unknown status, a missing status and an exception.",
         payment_status_fails_open),
    Rule("shipsafe.return-url-host-check-removed", "high", "Security", "Host check on a return or redirect URL removed",
         "A comparison of a URL's host against an expected value was removed and the file no longer checks the host. A crafted return URL could send the user or a payment result to another site.",
         "Restore the host check, or show where it moved, and test a return URL on a foreign host.",
         return_url_host_check_removed),
    Rule("shipsafe.idempotency-key-regenerated", "high", "Payment integrity", "Idempotency key generated anew for each request",
         "The idempotency key is built from a fresh random value or the current time where the request is sent. A retry then carries a different key and can be processed twice.",
         "Create the key once per user action, keep it across retries, and test that a retried request sends the same key.",
         idempotency_key_regenerated),
    Rule("shipsafe.submit-without-busy-guard", "medium", "Reliability", "Submit action without a busy or disabled guard",
         "A submit or pay handler runs asynchronous work and nothing in the file disables it while that work is in progress (or such a guard was removed). A second tap can submit twice.",
         "Disable the control or ignore further taps until the request finishes, and test a rapid double tap.",
         submit_without_busy_guard),
    Rule("shipsafe.cleartext-endpoint", "medium", "Security", "Unencrypted http:// endpoint added",
         "The change adds an http:// address that is not a local or placeholder host. Data sent there is not encrypted.",
         "Use https://, or confirm the address is never used outside local development.",
         cleartext_endpoint),
    Rule("shipsafe.verification-bypass", "medium", "Security", "Check short-circuited or switched off",
         "The change adds a condition that is always true, or sets a flag that skips a verification step.",
         "Confirm this is not reachable in a release build; remove it if it was added for debugging.",
         verification_bypass),
    Rule("shipsafe.empty-catch-in-sensitive-path", "low", "Reliability", "Error silently ignored in payment or sign-in code",
         "An exception is caught and discarded in code that handles payment or authentication, so a failure can look like success to the code that follows.",
         "Handle or report the error, and test the failure path.",
         empty_catch_in_sensitive_path),
)


def analyze_patterns(path: str, before: str, after: str, patch: str) -> list[dict]:
    """Findings of the pattern rules for one changed file. At most one finding per rule per file."""
    language = language_of(path)
    if language is None or is_test_path(path) or len(before) > MAX_FILE_CHARS or len(after) > MAX_FILE_CHARS:
        return []
    added, removed = parse_patch(patch)
    change = Change(path=path, language=language, before=before, after=after, added=added, removed=removed)
    findings = []
    for rule in RULES:
        hit = rule.check(change)
        if hit is None:
            continue
        line, evidence = hit
        findings.append({
            "id": str(uuid4())[:8], "category": rule.category, "severity": rule.severity, "title": rule.title,
            "file": path, "line": line, "status": "suspected", "evidence": evidence.strip()[:400],
            "explanation": rule.explanation + " This is a line-pattern suspicion, not a confirmed defect.",
            "recommendation": rule.recommendation,
            "source": SOURCE, "rule_id": rule.id, "language": language,
        })
    return findings
