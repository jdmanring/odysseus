"""Guards for the PR-draft file-claims checker (fork-only tooling).

Every one of these encodes a defect the tool actually shipped with. It reported
"83 drafts, 0 with a problem" for months; the real figure was 83 of 99, and the
16 it never examined were invisible. Widening the header match surfaced four
findings that the silence had been hiding, one of them in a draft edited and
declared clean the same day.

Only the two pure judgement calls are tested. Branch resolution needs git and is
exercised by running the tool itself, which the post-ingest checklist requires.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tooling"))

from draft_file_claims import asserted_paths, branch_of  # noqa: E402


# --- Header spellings -------------------------------------------------------
# All three are in use across the drafts. Requiring the colon inside the bold
# skipped 12 real drafts.

def test_branch_header_colon_inside_bold():
    assert branch_of("**Branch:** `fix/a-thing`") == "fix/a-thing"


def test_branch_header_colon_outside_bold():
    assert branch_of("**Branch**: `fix/a-thing`") == "fix/a-thing"


def test_branch_header_unbolded():
    assert branch_of("Branch: `fix/a-thing`") == "fix/a-thing"


def test_branch_header_is_found_below_a_title():
    # Every other fixture here puts the header on line 1, so dropping re.M from
    # BRANCH_RE passed all of them -- while returning None for all 99 real
    # drafts, which start with a title. That is the exact "0 problems" failure
    # this module exists to prevent, reproduced by its own test suite.
    assert branch_of("# PR Draft: fix/a-thing\n\n**Branch:** `fix/a-thing`\n") == "fix/a-thing"


def test_branch_header_absent_is_none():
    # Must be None rather than a guess: the caller reports it as a named skip.
    assert branch_of("# A draft with no header\n\nSome prose.") is None


def test_branch_header_must_start_the_line():
    # Avoids matching prose like "the branch: `x` was deleted".
    assert branch_of("Note that the Branch: `fix/a-thing` is stale") is None


# --- Which paths count as the draft's own claims ----------------------------

def test_a_plain_backticked_path_is_a_claim():
    assert asserted_paths("Adds `src/thing.py` to the tree.") == {"src/thing.py"}


def test_a_linked_path_is_a_citation_not_a_claim():
    # The whole point of the fix-dom-oom-virtualization evidence table: the
    # benchmark is linked into the workbench and is explicitly NOT in the PR.
    line = "| harness | [`tests/bench/x.py`](https://github.com/o/r/blob/develop/tests/bench/x.py) |"
    assert asserted_paths(line) == set()


def test_a_hedged_path_is_not_a_claim():
    assert asserted_paths("A test `tests/test_x.py` can be added later.") == set()


def test_a_claim_and_a_citation_on_the_same_line_are_separated():
    line = "Adds `src/real.py`; see [`docs/ref.py`](https://example.com/docs/ref.py)."
    assert asserted_paths(line) == {"src/real.py"}


def test_non_source_extensions_are_ignored():
    # The matcher is deliberately extension-scoped; prose backticks are noise.
    assert asserted_paths("See `README.md` and `--flag` and `x.txt`.") == set()


def test_paths_are_collected_across_lines():
    text = "Adds `src/a.py`.\n\nAlso `static/js/b.js`.\n"
    assert asserted_paths(text) == {"src/a.py", "static/js/b.js"}
