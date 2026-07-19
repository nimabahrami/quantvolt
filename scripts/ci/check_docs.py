"""Documentation quality gates for the *public* QuantVolt docs (stdlib-only, no quantvolt import).

Public docs are the surfaces a prospective user reads before ever opening `.kiro/` -- the
marketing site, the README, and the `docs/*.md` reference guides. Three mechanical checks keep
that surface from leaking internal spec plumbing or backsliding into vague marketing prose:

  (a) **Internal references**: number-anchored regexes (``Task 5``, ``Req 12``, ``Requirement 3``,
      ``Property 42``, ``Properties 1``, ``coding-style.md``, ``base spec``, ``this spec``,
      ``Phase 2``, ``.kiro/``) catch the common ways an internal task/requirement/property
      citation or steering-doc path leaks into a page a user is meant to read standalone. The
      patterns are anchored on a digit (or an exact phrase) specifically so ordinary English
      words like "task" or "property" in a normal sentence do not trip the gate.

  (b) **Banned phrases**: a fixed, case-insensitive list of marketing filler and unfinished-work
      markers (``seamlessly``, ``production-grade``, ``TODO``, ``FIXME``, ...) that a claims-first
      technical doc should not contain. ``bit-identical`` is allowed *only* when a same-run
      qualifier (``same`` plus one of ``version``/``architecture``/``build``) appears within the
      following 200 characters -- i.e. "bit-identical across the same build" is fine, a bare
      unqualified "bit-identical" claim is not.

  (c) **Double punctuation**: stray ``..`` (not ``...``), ``,,``, ``!!``, ``??`` outside fenced or
      inline Markdown code -- copy-editing slips, not correctness bugs, but cheap to catch
      mechanically. Code-block awareness is best-effort: exact for Markdown files (fenced ``` ```
      blocks and inline `` `code` `` spans are masked before scanning), a plain full-text scan for
      JS/HTML, where template literals make exact masking impractical.

A reviewed false positive (a legitimate use of a banned word, e.g. quoting a user's own
"seamlessly" in a testimonial) can be silenced with a one-substring-per-line entry in
``scripts/ci/docs_lint_allow.txt`` -- see that file's header for the exact contract.

This script does **not** fix anything; it only reports. It also does not gate on zero violations
today -- the public docs are mid-cleanup by other agents at the time this gate was added, so a
non-zero count is expected until that cleanup lands and is verified separately.

Usage::

    python scripts/ci/check_docs.py             # lint the real repo docs
    python scripts/ci/check_docs.py --self-test  # exercise the checker against a synthetic
                                                  # fixture; does not touch the repo's own docs

Exit status 0 means zero (unsuppressed) violations; 1 means at least one violation was printed.
``--self-test`` exits 0 only if the checker's own behaviour matches the fixture's expectations.
"""

from __future__ import annotations

import argparse
import bisect
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWLIST_PATH = Path(__file__).resolve().parent / "docs_lint_allow.txt"

# Public-facing docs only. Internal specs (.kiro/**), CI scripts, and test fixtures are out of
# scope by design -- they are allowed (expected, even) to cite Task/Req/Property numbers.
PUBLIC_DOCS: tuple[str, ...] = (
    "site/content.js",
    "site/complete-guides.js",
    "site/api-data.js",
    "site/index.html",
    "README.md",
    "docs/api.md",
    "docs/european-markets.md",
    "docs/risk-and-assets.md",
    "docs/validation.md",
    "docs/claims.md",
    # Shipped example scripts are user-facing documentation too: they are linked from the
    # rendered guides and their docstrings/comments must meet the same bar.
    "site/examples/shared_setup.py",
    "site/examples/verify_foundations.py",
    "site/examples/verify_native_monte_carlo.py",
    "site/examples/verify_ppa.py",
    "site/examples/verify_pricing.py",
    "site/examples/verify_quickstart.py",
    "site/examples/verify_research.py",
    "site/examples/verify_tutorial_ppa.py",
    "site/examples/verify_tutorial_spark.py",
    "site/examples/verify_tutorial_storage.py",
    "site/examples/verify_validation.py",
)

_MARKDOWN_SUFFIXES = (".md",)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    category: str
    matched: str
    context: str  # the full source line, for human-readable reporting
    window: str  # a narrow (~80-char) span around the match, for allowlist matching only


# --- (a) Internal references ---------------------------------------------------------------

# Each pattern is anchored on a digit or an exact multi-word phrase so ordinary prose ("this
# property of forward curves", "a robust task scheduler") does not trip the gate.
_INTERNAL_REF_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Task N", re.compile(r"\bTask [0-9]")),
    ("Req N", re.compile(r"\bReq\.? ?[0-9]")),
    ("Requirement N", re.compile(r"\bRequirement [0-9]")),
    ("Property N", re.compile(r"\bProperty [0-9]")),
    ("Properties N", re.compile(r"\bProperties [0-9]")),
    ("coding-style.md", re.compile(r"coding-style\.md")),
    ("base spec", re.compile(r"\bbase spec\b")),
    ("this spec", re.compile(r"\bthis spec\b")),
    ("Phase N", re.compile(r"\bPhase [0-9]")),
    (".kiro/", re.compile(r"\.kiro/")),
)


def _find_internal_refs(text: str) -> list[tuple[re.Match[str], str]]:
    hits: list[tuple[re.Match[str], str]] = []
    for label, pattern in _INTERNAL_REF_PATTERNS:
        for match in pattern.finditer(text):
            hits.append((match, label))
    return hits


# --- (b) Banned phrases ---------------------------------------------------------------------

# Plain case-insensitive substrings. Multi-word phrases are unambiguous enough on their own that
# a word-boundary match would add complexity without reducing false positives meaningfully.
_SIMPLE_BANNED_PHRASES: tuple[str, ...] = (
    "same economics",
    "production-grade",
    "institutional-grade",
    "seamlessly",
    "battle-tested",
    "hard things correctly",
    "in modern energy markets",
    "this powerful",
    "robust and flexible",
    "a deliberate attempt to",
    "the real lesson",
    "where the difficulty actually lives",
    "it is important to understand",
    "small computational core",
)

# "in today's complex" -- apostrophe spelling varies (straight vs. curly quote) between hand-typed
# and copy-pasted prose, so both are matched explicitly rather than normalising the whole file.
_TODAYS_COMPLEX_RE = re.compile(r"in today['\u2019]s complex", re.IGNORECASE)

# TODO/FIXME: word-boundary, not substring, so "TODOS" (a different word) does not false-positive.
_WORD_BANNED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TODO", re.compile(r"\bTODO\b", re.IGNORECASE)),
    ("FIXME", re.compile(r"\bFIXME\b", re.IGNORECASE)),
)

# "bit-identical" is allowed only when qualified, within the next 200 characters, by "same" plus
# one of these same-run qualifiers -- "bit-identical across the same build" is a scoped, checkable
# claim; a bare "bit-identical" is not. Implemented pragmatically as a substring window, not a
# full parse: false negatives (a qualifier phrased unusually) are more acceptable here than a
# fragile regex that stops enforcing the intent entirely.
_BIT_IDENTICAL_RE = re.compile(r"bit-identical", re.IGNORECASE)
_BIT_IDENTICAL_WINDOW = 200
_BIT_IDENTICAL_QUALIFIERS = ("version", "architecture", "build")


def _bit_identical_is_qualified(text: str, match_end: int) -> bool:
    window = text[match_end : match_end + _BIT_IDENTICAL_WINDOW].lower()
    if "same" not in window:
        return False
    return any(qualifier in window for qualifier in _BIT_IDENTICAL_QUALIFIERS)


def _find_banned_phrases(text: str) -> list[tuple[re.Match[str], str]]:
    hits: list[tuple[re.Match[str], str]] = []
    lower = text.lower()
    for phrase in _SIMPLE_BANNED_PHRASES:
        start = 0
        needle = phrase.lower()
        while True:
            index = lower.find(needle, start)
            if index == -1:
                break
            match = re.compile(re.escape(phrase), re.IGNORECASE).match(text, index)
            assert match is not None
            hits.append((match, phrase))
            start = index + 1
    for match in _TODAYS_COMPLEX_RE.finditer(text):
        hits.append((match, "in today's complex"))
    for label, pattern in _WORD_BANNED_PATTERNS:
        for match in pattern.finditer(text):
            hits.append((match, label))
    for match in _BIT_IDENTICAL_RE.finditer(text):
        if not _bit_identical_is_qualified(text, match.end()):
            hits.append((match, "bit-identical (unqualified)"))
    return hits


# --- (c) Double punctuation -------------------------------------------------------------------

_DOUBLE_PUNCT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # "(?<!/)..(?!/)" guards: "../" in relative paths and "a..b" range notation stay legal
    # only when path-shaped; a stray prose ".." still trips.
    ("..", re.compile(r"(?<!\.)\.\.(?!\.)(?!/)")),
    (",,", re.compile(r",,")),
    ("!!", re.compile(r"!!")),
    ("??", re.compile(r"\?\?")),
)

_FENCE_RE = re.compile(r"^\s*```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _mask_markdown_code(text: str) -> str:
    """Blank fenced ``` code blocks and inline `code` spans, preserving length/offsets."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(" " * len(line))
            continue
        if in_fence:
            out.append(" " * len(line))
            continue
        out.append(_INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line))
    return "".join(out)


def _find_double_punctuation(text: str, *, is_markdown: bool) -> list[tuple[re.Match[str], str]]:
    scan_text = _mask_markdown_code(text) if is_markdown else text
    hits: list[tuple[re.Match[str], str]] = []
    for label, pattern in _DOUBLE_PUNCT_PATTERNS:
        for match in pattern.finditer(scan_text):
            hits.append((match, label))
    return hits


# --- Allowlist --------------------------------------------------------------------------------

# How far around a match's start/end the allowlist-matching window extends. Deliberately
# narrower than "the whole line": a line packed with several distinct banned phrases (or several
# internal refs) must be suppressible one phrase at a time, not all-or-nothing.
_ALLOWLIST_WINDOW_RADIUS = 80


def load_allowlist(path: Path = ALLOWLIST_PATH) -> tuple[str, ...]:
    """Substring-per-line reviewed false positives; blank lines and ``#`` comments are ignored."""
    if not path.exists():
        return ()
    entries: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return tuple(entries)


def _is_allowlisted(window: str, allowlist: tuple[str, ...]) -> bool:
    return any(entry in window for entry in allowlist)


# --- Per-file lint -----------------------------------------------------------------------------


def _line_number(line_starts: list[int], offset: int) -> int:
    return bisect.bisect_right(line_starts, offset)


def _line_text(text: str, line_starts: list[int], line_no: int) -> str:
    start = line_starts[line_no - 1]
    end = text.find("\n", start)
    if end == -1:
        end = len(text)
    return text[start:end]


def lint_text(text: str, *, relative_path: str) -> list[Violation]:
    """Run all three checks over ``text`` and return unfiltered (pre-allowlist) violations."""
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    is_markdown = relative_path.endswith(_MARKDOWN_SUFFIXES)
    violations: list[Violation] = []

    def _window(match: re.Match[str]) -> str:
        start = max(0, match.start() - _ALLOWLIST_WINDOW_RADIUS)
        end = min(len(text), match.end() + _ALLOWLIST_WINDOW_RADIUS)
        return text[start:end]

    for match, _label in _find_internal_refs(text):
        line_no = _line_number(line_starts, match.start())
        context = _line_text(text, line_starts, line_no)
        violations.append(
            Violation(
                relative_path,
                line_no,
                "internal-ref",
                match.group(0),
                context.strip(),
                _window(match),
            )
        )

    for match, label in _find_banned_phrases(text):
        line_no = _line_number(line_starts, match.start())
        context = _line_text(text, line_starts, line_no)
        violations.append(
            Violation(
                relative_path, line_no, "banned-phrase", label, context.strip(), _window(match)
            )
        )

    for match, _label in _find_double_punctuation(text, is_markdown=is_markdown):
        line_no = _line_number(line_starts, match.start())
        context = _line_text(text, line_starts, line_no)
        violations.append(
            Violation(
                relative_path,
                line_no,
                "double-punct",
                match.group(0),
                context.strip(),
                _window(match),
            )
        )

    return violations


def lint_file(path: Path, *, relative_path: str) -> list[Violation]:
    text = path.read_text(encoding="utf-8")
    return lint_text(text, relative_path=relative_path)


# --- Report -------------------------------------------------------------------------------


def _print_violations(title: str, violations: list[Violation]) -> None:
    print(f"--- {title} ---")
    if not violations:
        print("  OK -- no violations.")
        return
    for v in violations:
        snippet = v.context if len(v.context) <= 160 else v.context[:157] + "..."
        print(f"  VIOLATION: {v.path}:{v.line}: [{v.matched!r}] {snippet}")


def run(public_docs: tuple[str, ...] = PUBLIC_DOCS, *, allowlist: tuple[str, ...] = ()) -> int:
    all_violations: list[Violation] = []
    suppressed_count = 0
    missing_files: list[str] = []

    for relative_path in public_docs:
        path = REPO_ROOT / relative_path
        if not path.exists():
            missing_files.append(relative_path)
            continue
        for violation in lint_file(path, relative_path=relative_path):
            if _is_allowlisted(violation.window, allowlist):
                suppressed_count += 1
                continue
            all_violations.append(violation)

    if missing_files:
        print("=== Missing public docs (skipped) ===")
        for m in missing_files:
            print(f"  {m}")
        print()

    by_category = {
        "internal-ref": [v for v in all_violations if v.category == "internal-ref"],
        "banned-phrase": [v for v in all_violations if v.category == "banned-phrase"],
        "double-punct": [v for v in all_violations if v.category == "double-punct"],
    }

    print("=== Documentation lint: public docs ===")
    _print_violations("(a) internal spec/task references", by_category["internal-ref"])
    print()
    _print_violations("(b) banned phrases", by_category["banned-phrase"])
    print()
    _print_violations("(c) double punctuation", by_category["double-punct"])

    print("\n=== Violations by file ===")
    by_file: dict[str, int] = {}
    for v in all_violations:
        by_file[v.path] = by_file.get(v.path, 0) + 1
    if by_file:
        for path in sorted(by_file):
            print(f"  {path}: {by_file[path]}")
    else:
        print("  (none)")

    print("\n=== Violations by category ===")
    for category, items in by_category.items():
        print(f"  {category}: {len(items)}")

    total = len(all_violations)
    print(
        f"\n{total} violation(s) found across {len(by_file)} file(s) "
        f"({suppressed_count} suppressed by {ALLOWLIST_PATH.relative_to(REPO_ROOT)})."
    )
    return 1 if total else 0


# --- Self-test ------------------------------------------------------------------------------

_SELF_TEST_MARKDOWN = """\
# Sample doc

See Task 5 and Requirement 3 for background; Property 12 and Properties 4 also apply. This
document lives outside .kiro/ but references coding-style.md, the base spec, and this spec
anyway.

This is a seamlessly integrated, production-grade tool for energy quants everywhere, built
for people who need answers fast and do not want to wait around all day for them, ever.

Elsewhere and unrelated, this is an institutional-grade, battle-tested way to handle
hard things correctly in today's complex energy markets, or so a marketing page claimed.

This powerful tool is robust and flexible. It is important to understand that this was
a deliberate attempt to fix the real lesson: where the difficulty actually lives is the
small computational core. TODO: revisit this. FIXME later.

Results are bit-identical every single time no matter what, full stop, end of claim,
nothing further said about it at all here, padding this sentence out well past the two
hundred character lookahead window so the next paragraph's qualifier cannot reach back
into this one and wrongly excuse an otherwise bare claim from being flagged as such.

Results are bit-identical across the same build every run, which is a qualified claim.

Wait.. what? Really,, no!! Surely not??

```python
x = [1, 2, 3]
y = x[0..1]  # inside a fenced block: must NOT be flagged
```

Inline `x[0..1]` code span must also NOT be flagged.
"""


def _self_test() -> int:
    violations = lint_text(_SELF_TEST_MARKDOWN, relative_path="docs/_self_test.md")
    by_category: dict[str, list[Violation]] = {}
    for v in violations:
        by_category.setdefault(v.category, []).append(v)

    failures: list[str] = []

    internal_ref_matches = {v.matched for v in by_category.get("internal-ref", [])}
    expected_internal = {
        "Task 5",
        "Requirement 3",
        # The regex `\bProperty [0-9]` is anchored on a single digit by design (see the
        # (a) docstring above), so "Property 12" matches only its leading digit.
        "Property 1",
        "Properties 4",
        ".kiro/",
        "coding-style.md",
        "base spec",
        "this spec",
    }
    if internal_ref_matches != expected_internal:
        failures.append(
            f"internal-ref mismatch: got {sorted(internal_ref_matches)}, "
            f"expected {sorted(expected_internal)}"
        )

    banned_matches = [v.matched for v in by_category.get("banned-phrase", [])]
    banned_lower = {m.lower() for m in banned_matches}
    for expected in (
        "seamlessly",
        "production-grade",
        "institutional-grade",
        "battle-tested",
        "hard things correctly",
        "in today's complex",
        "this powerful",
        "robust and flexible",
        "it is important to understand",
        "a deliberate attempt to",
        "the real lesson",
        "where the difficulty actually lives",
        "small computational core",
        "todo",
        "fixme",
    ):
        if expected not in banned_lower:
            failures.append(f"banned-phrase missing: {expected!r} (got {sorted(banned_lower)})")

    bit_identical_hits = [m for m in banned_matches if m.lower().startswith("bit-identical")]
    if len(bit_identical_hits) != 1:
        failures.append(
            f"expected exactly 1 unqualified bit-identical violation, got {len(bit_identical_hits)}"
        )

    double_punct_matches = sorted(v.matched for v in by_category.get("double-punct", []))
    expected_double_punct = sorted(["..", ",,", "!!", "??"])
    if double_punct_matches != expected_double_punct:
        failures.append(
            f"double-punct mismatch: got {double_punct_matches}, expected {expected_double_punct}"
        )
    for v in by_category.get("double-punct", []):
        if "must NOT be flagged" in v.context or "x = [1, 2, 3]" in v.context:
            failures.append(f"double-punct false positive inside code: {v}")

    # _bit_identical_is_qualified: direct unit-level check, independent of any window-bleed
    # risk from neighbouring sentences in the shared fixture above.
    if not _bit_identical_is_qualified(" across the same build.", 0):
        failures.append("bit-identical: expected 'same' + 'build' within window to qualify")
    if _bit_identical_is_qualified(" every single time, no further comment.", 0):
        failures.append("bit-identical: expected no qualifier to NOT qualify")

    # Allowlist suppression: silence the "seamlessly" phrase without over-suppressing
    # "institutional-grade" on the same line.
    with tempfile.TemporaryDirectory() as tmp:
        allow_path = Path(tmp) / "docs_lint_allow.txt"
        allow_path.write_text(
            "# reviewed false positives\nseamlessly integrated, production-grade\n",
            encoding="utf-8",
        )
        allowlist = load_allowlist(allow_path)
        remaining = [v for v in violations if not _is_allowlisted(v.window, allowlist)]
        remaining_matches = {v.matched.lower() for v in remaining}
        if "seamlessly" in remaining_matches or "production-grade" in remaining_matches:
            failures.append("allowlist did not suppress the expected phrase")
        if "institutional-grade" not in remaining_matches:
            failures.append("allowlist over-suppressed an unrelated violation")

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELF-TEST PASSED ({len(violations)} violations found in the synthetic fixture).")
    return 0


# --- CLI ------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Exercise the checker against a synthetic fixture instead of the repo's docs.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    allowlist = load_allowlist()
    return run(allowlist=allowlist)


if __name__ == "__main__":
    sys.exit(main())
