r"""Values interpolated into `slashReply()`'s innerHTML are escaped.

`slashReply()` (static/js/slashCommands.js) assigns its argument to
`body.innerHTML`. Callers build that string from template literals, escaping
each field with `ctx.esc(...)`. A field left raw is an injection sink the
moment anything upstream stops constraining it.

**These tests EXECUTE the templates.** An earlier version scanned the source
with a regex that classified an interpolation as safe if it contained no `.`,
or contained the substring `esc(`, `.join(`, or `.length`. An adversarial
review passed seven live XSS variants through it, including the original defect
re-introduced as `${m['category']}` (no dot, so it read as a literal) and one
wrapped in `${fmtTag({label: m.source})}` (the inner braces meant the scanner
found no interpolation at all). Any guard that reasons *about* source rather
than running it has that class of hole. This one renders each template with a
hostile object and inspects the output.

The escaper is stubbed with a marker rather than imported: `ui.js` starts work
at import time and hangs under a bare node DOM shim. What matters here is
whether a field went through `esc` at all, and a marker answers exactly that.
What `esc` itself does is pinned separately, by the escaping tests for ui.js.

DEFER(ui.js becomes importable under node): import the real `esc` and assert on
final rendered HTML instead of on marker presence.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SLASH = _REPO / "static" / "js" / "slashCommands.js"
_HAS_NODE = shutil.which("node") is not None

pytestmark = pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")

PAYLOAD = "<img src=x onerror=alert(1)>"
ATTR_PAYLOAD = '" onmouseover=alert(1) x="'

# Template literals are located by content, not by a list of function names.
# A hand-maintained name list is what let a review defeat the previous guard by
# moving the raw field into a helper function.
_TEMPLATE_RE = re.compile(r"`(?:[^`\\]|\\.)*`", re.S)


# A template is in scope if it reaches an innerHTML sink. Filtering on "contains
# a tag" was the first attempt and it was wrong in the worst possible way: the
# original defect lived in `[${m.category}] ${ctx.esc(m.text)}`, which has no
# markup at all because `slashReply()` supplies the surrounding <pre>. Six of
# the seven known evasions were invisible under that filter.
_SINK_RE = re.compile(
    r"(slashReply\s*\(|_setupReply\s*\(|typewriterReply\s*\(|innerHTML\s*=|"
    r"(?:const|let|var)\s+(?:lines|rows|out|html|body|parts|items)\b)")
_SINK_LOOKBEHIND = 220

# Request URLs are not innerHTML sinks; proximity to a sink call sweeps them in
# otherwise, and a URL is a different concern (encodeURIComponent, not esc).
#
# There is deliberately NO "looks like a CSS selector" rule here. The first
# version excluded any template starting with `[`, `.` or `#`, which silently
# excluded `[${m.category}] ${ctx.esc(m.text)}` -- the exact line this suite
# exists to guard. An exclusion that hides the original defect is worse than
# the false positives it was added to remove.
_NOT_A_SINK_RE = re.compile(r"\$\{API_BASE\}|://|^`/api/")


def _sink_templates():
    """Template literals that reach an innerHTML sink, plus any that carry markup."""
    src = _SLASH.read_text(encoding="utf-8")
    out = []
    for m in _TEMPLATE_RE.finditer(src):
        lit = m.group(0)
        if "${" not in lit:
            continue
        if _NOT_A_SINK_RE.search(lit):
            continue
        preceding = src[max(0, m.start() - _SINK_LOOKBEHIND):m.start()]
        if "<" in lit or _SINK_RE.search(preceding):
            out.append(lit)
    return out


# Kept as the narrower set for the attribute-position baseline below.
def _markup_templates():
    src = _SLASH.read_text(encoding="utf-8")
    return [lit for lit in _TEMPLATE_RE.findall(src)
            if "${" in lit and "<" in lit]


_NODE_HARNESS = r"""
const PAYLOAD = __PAYLOAD__;
const ATTR = __ATTR__;

// Marker escaper: proves a value passed through esc(), whatever esc does.
const ESC_OPEN = 'E';
const ESC_CLOSE = 'E';
const esc = (s) => ESC_OPEN + String(s) + ESC_CLOSE;

// `truthy` decides which branch a ternary or `||` takes, so every template is
// rendered under both. A raw value sitting in the branch the default happens
// not to take would otherwise never be rendered at all.
const IS_HOSTILE = '__hostile__';

// Scope rule: a bare identifier is BENIGN, every property read off it is
// HOSTILE. That is exactly the defect class -- a field read off a data object
// and interpolated without esc(). A bare local (`usage`, `status`, `lines`) is
// typically assembled and escaped further up the function, which a
// template-level harness cannot see, so treating it as hostile would report
// false positives on already-safe code.
function makeHostile(falsyProp) {
  const hostile = new Proxy(function () {}, {
    get(_t, k) {
      if (k === Symbol.toPrimitive || k === 'toString' || k === 'valueOf')
        return () => PAYLOAD;
      if (k === 'then') return undefined;            // must not look thenable
      if (k === 'esc') return esc;   // uiModule.esc / ctx.esc are the escaper
      if (k === IS_HOSTILE) return true;
      // Numeric formatters cannot carry markup out.
      if (k === 'toFixed' || k === 'toPrecision') return () => '0';
      if (k === 'length') return PAYLOAD.length;
      // Collection methods must APPLY their callback, or the escape-at-join
      // idiom (`lines.map(l => esc(l)).join('')`) reads as unescaped.
      if (k === 'map' || k === 'filter' || k === 'flatMap')
        return (fn) => [fn ? fn(hostile, 0, [hostile]) : hostile];
      if (k === 'forEach') return (fn) => { if (fn) fn(hostile, 0, [hostile]); };
      if (k === 'join') return () => String(hostile);
      // One property forced falsy per pass, so both branches of a ternary or
      // an `||` get rendered. Without this, `m.pinned ? esc(m.text) : m.source`
      // always takes the escaped branch and the raw one is never evaluated.
      if (k === falsyProp) return '';
      return hostile;
    },
    apply() { return hostile; },
    has() { return true; },
  });
  return hostile;
}

const BENIGN = 'benign';

// Does this argument carry a hostile value anywhere inside it? Catches
// `fmtTag({label: m.source})`, where a raw field is laundered through a helper.
function carriesHostile(v, depth) {
  if (v === null || v === undefined) return false;
  if (depth > 3) return false;
  try {
    if (v[IS_HOSTILE]) return true;
    if (typeof v === 'object' || typeof v === 'function') {
      for (const key of Object.keys(v)) {
        if (carriesHostile(v[key], depth + 1)) return true;
      }
    }
  } catch (e) { /* exotic proxy */ }
  return false;
}

function renderOnce(source, falsyProp) {
  const hostile = makeHostile(falsyProp);
  // A bare identifier yields an object that stringifies benignly but whose
  // properties are hostile.
  const carrier = new Proxy(function () {}, {
    get(_t, k) {
      if (k === Symbol.toPrimitive || k === 'toString' || k === 'valueOf')
        return () => BENIGN;
      if (k === 'then') return undefined;
      if (k === 'esc') return esc;
      if (k === IS_HOSTILE) return false;
      if (k === 'toFixed' || k === 'toPrecision') return () => '0';
      if (k === 'length') return BENIGN.length;
      if (k === 'map' || k === 'filter' || k === 'flatMap')
        return (fn) => [fn ? fn(carrier, 0, [carrier]) : carrier];
      if (k === 'forEach') return (fn) => { if (fn) fn(carrier, 0, [carrier]); };
      if (k === 'join') return () => BENIGN;
      if (k === falsyProp) return '';
      return hostile;
    },
    // A helper called with a hostile field returns the field: a wrapper is not
    // an escape.
    apply(_t, _this, args) {
      for (const a of args || []) if (carriesHostile(a, 0)) return hostile;
      return carrier;
    },
    has() { return true; },
  });

  // A `with` scope resolves ANY identifier the template names, so the harness
  // never needs a list of variable names kept in sync with the source.
  const scope = new Proxy({}, {
    has: () => true,
    get(_t, k) {
      if (k === Symbol.unscopables) return undefined;
      if (k === 'esc') return esc;
      if (k === 'String') return String;
      if (k === 'JSON') return JSON;
      if (k === 'Math') return Math;
      if (k === 'Object') return Object;
      if (k === 'Array') return Array;
      if (k === 'Date') return Date;
      if (k === 'ctx') return new Proxy({}, {
        has: () => true,
        get: (_t2, k2) => (k2 === 'esc' ? esc : hostile),
      });
      return carrier;
    },
  });
  const fn = new Function('scope', 'with (scope) { return (' + source + '); }');
  const rendered = String(fn(scope));
  // Remove everything that went through esc(). A payload in what is left is raw.
  const stripped = rendered.split(ESC_OPEN).map((chunk, n) => {
    if (n === 0) return chunk;
    const end = chunk.indexOf(ESC_CLOSE);
    return end === -1 ? '' : chunk.slice(end + ESC_CLOSE.length);
  }).join('');
  return stripped.includes(PAYLOAD) || stripped.includes(ATTR);
}

// Property names the template mentions, each tried as the falsy one.
function candidateProps(source) {
  const names = new Set([null]);
  const re = /\.([A-Za-z_$][\w$]*)|\[\s*['"]([^'"]+)['"]\s*\]/g;
  let m;
  while ((m = re.exec(source)) !== null) names.add(m[1] || m[2]);
  return [...names].slice(0, 40);
}

const results = [];
for (const [i, source] of TEMPLATES.entries()) {
  let raw = false, ok = false, err = null;
  for (const falsyProp of candidateProps(source)) {
    try {
      raw = renderOnce(source, falsyProp) || raw;
      ok = true;
      if (raw) break;
    } catch (e) {
      err = String(e && e.message);
    }
  }
  results.push(ok ? { i, raw: raw } : { i, skipped: err });
}
console.log(JSON.stringify(results));
"""


def _render_all(templates):
    harness = (_NODE_HARNESS
               .replace("__PAYLOAD__", json.dumps(PAYLOAD))
               .replace("__ATTR__", json.dumps(ATTR_PAYLOAD)))
    js = "const TEMPLATES = " + json.dumps(templates) + ";\n" + harness
    proc = subprocess.run(["node", "--input-type=module"], input=js,
                          capture_output=True, text=True, cwd=str(_REPO), timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


# --- the harness must be doing real work -------------------------------------

def test_the_harness_actually_renders_the_file():
    """Denominator guard: a harness that skipped everything would pass silently."""
    templates = _sink_templates()
    assert len(templates) >= 100, f"only found {len(templates)} sink templates"
    results = _render_all(templates)
    rendered = [r for r in results if "raw" in r]
    assert len(rendered) >= len(templates) * 0.8, (
        f"only {len(rendered)} of {len(templates)} templates rendered; "
        "the harness is not exercising the file"
    )


def test_the_check_can_actually_fail():
    """Mutation control: an unescaped interpolation must be detected."""
    assert _render_all(["`<pre>${m.category}</pre>`"])[0]["raw"] is True
    assert _render_all(["`<pre>${ctx.esc(m.category)}</pre>`"])[0]["raw"] is False


@pytest.mark.parametrize("evasion", [
    "`<pre>${m['category']}</pre>`",                           # bracket notation
    "`<pre>${fmtTag({label: m.source})}</pre>`",               # nested braces
    "`<pre>${m.pinned ? ctx.esc(m.text) : m.source}</pre>`",   # ternary launder
    "`<pre>${m.source.length ? m.source : ''}</pre>`",         # .length decoy
    "`<pre>${m.source + m.tags.join(',')}</pre>`",             # .join decoy
])
def test_the_evasions_that_defeated_the_regex_are_caught(evasion):
    """Every one of these passed the previous source-scanning guard."""
    assert _render_all([evasion])[0].get("raw") is True, f"evasion not caught: {evasion}"


@pytest.mark.parametrize("safe", [
    "`<pre>${ctx.esc(m.category)} ${ctx.esc(m.text)}</pre>`",
    "`<pre>${lines.map(line => ctx.esc(line)).join('')}</pre>`",   # escape at join
    "`<pre>${ctx.esc(category)}</pre>`",                           # destructured
    "`<span>${ctx.esc(s.name || 'Untitled')}</span>`",             # default value
])
def test_safe_forms_do_not_false_positive(safe):
    """A refactor that keeps escaping must not break the suite.

    The previous guard failed on destructuring and on renaming, because it
    compared source literals.
    """
    assert _render_all([safe])[0].get("raw") is False, f"false positive: {safe}"


# --- the actual assertion over the shipped file -------------------------------

def test_no_sink_template_emits_an_unescaped_value():
    templates = _sink_templates()
    results = _render_all(templates)
    offenders = [templates[r["i"]].strip()[:200] for r in results if r.get("raw")]
    assert not offenders, (
        f"{len(offenders)} template(s) interpolate a value into markup "
        "without esc():\n\n" + "\n\n".join(offenders)
    )


# --- bare identifiers in attribute position ----------------------------------
#
# The executing harness treats a BARE identifier as benign, because a local is
# usually assembled and escaped further up the function and a template-level
# harness cannot see that. Attribute position is the exception worth pinning
# separately: there a missing escape covers the quote that ends the attribute,
# which is a worse failure than the text case. This is a baseline, so anything
# NEW fails until it is reviewed and added here with a reason.

_ATTR_BARE_RE = re.compile(r'=\s*"[^"]*\$\{\s*([A-Za-z_$][\w$]*)\s*\}')

REVIEWED_ATTR_IDENTIFIERS = {
    # _eggRender internals, all computed locally, never external data.
    "clr",    # a colour picked from a fixed palette
    "pct",    # a number formatted for a progress bar width
    "sides",  # a dice-side count, an integer
    # (querySelector selector strings contain no "<" and so never reach this
    # set at all; they are not a markup sink.)
}


def test_no_new_bare_identifier_in_an_attribute():
    found = set()
    for lit in _markup_templates():
        found.update(_ATTR_BARE_RE.findall(lit))
    new = found - REVIEWED_ATTR_IDENTIFIERS
    assert not new, (
        "bare identifier interpolated into an attribute value: " + ", ".join(sorted(new))
        + " -- escape it, or add it to REVIEWED_ATTR_IDENTIFIERS with a reason"
    )


def test_the_attribute_baseline_is_not_stale():
    """A reviewed entry that no longer appears should be removed, not left to rot."""
    found = set()
    for lit in _markup_templates():
        found.update(_ATTR_BARE_RE.findall(lit))
    stale = REVIEWED_ATTR_IDENTIFIERS - found
    assert not stale, f"REVIEWED_ATTR_IDENTIFIERS lists identifiers that are gone: {stale}"
