// Regression guard for _smoothScrollStep(): the follow lerp defers to the
// direction-based isPinned intent flag and carries NO distance-based drift
// guard of its own. The old adaptive threshold (Math.max(300, viewport*1.5))
// existed to guess user intent from distance — a guess a wheel notch could
// never overcome (#145). Direction made the guess unnecessary: content
// growth never decreases scrollTop, only the user scrolling up does.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const uiSource = readFileSync(join(ROOT, 'static', 'js', 'ui.js'), 'utf8');

function stepBody() {
  const start = uiSource.indexOf('function _smoothScrollStep()');
  assert.ok(start !== -1, '_smoothScrollStep must exist');
  return uiSource.slice(start, uiSource.indexOf('\n}', start));
}

test('lerp bails when the user is not pinned', () => {
  assert.ok(
    stepBody().includes('if (!isPinned)'),
    '_smoothScrollStep must stop the follow loop the frame after an unpin'
  );
});

test('no distance-based drift guard remains in the lerp', () => {
  const body = stepBody();
  assert.ok(!body.includes('maxAllowedDiff'), 'adaptive distance guard must be gone');
  assert.ok(!/diff\s*>\s*(300|Math\.max)/.test(body),
    'the lerp must never infer user intent from distance');
});

test('unpin is direction-based in the stick observer', () => {
  assert.ok(uiSource.includes('box.scrollTop < _lastScrollTop'),
    'unpin must key off upward scroll movement');
});

test('wheel-up unpins ahead of the scroll event', () => {
  assert.ok(uiSource.includes("box.addEventListener('wheel'"), 'wheel listener required');
  assert.ok(uiSource.includes('e.deltaY < 0'), 'only upward wheel unpins');
});

test('re-pin epsilon is small, per stick-to-bottom practice', () => {
  const m = uiSource.match(/const REPIN_DISTANCE = (\d+);/);
  assert.ok(m, 'REPIN_DISTANCE must be a named constant');
  const px = Number(m[1]);
  // Direction-based libraries pair gesture unpinning with a small at-bottom
  // epsilon (react-virtuoso atBottomThreshold defaults to 4px; chat UIs
  // commonly use tens of px). Three digits would recreate the unescapable
  // slack this design removed.
  assert.ok(px >= 4 && px <= 100, `REPIN_DISTANCE ${px}px outside sane 4..100 range`);
});
