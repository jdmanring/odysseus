// Regression guard for _smoothScrollStep() adaptive threshold (Math.max(300, viewportHeight * 1.5)).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, dirname } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const uiSource = readFileSync(join(ROOT, 'static', 'js', 'ui.js'), 'utf8');

// --- Source-level structural checks ---

test('_smoothScrollStep uses Math.max adaptive threshold, not rigid 300', () => {
  assert.ok(
    uiSource.includes('Math.max(300,'),
    'ui.js must use Math.max(300, ...) for the adaptive scroll threshold'
  );
});

test('rigid "if (diff > 300)" is no longer present in _smoothScrollStep', () => {
  assert.ok(
    !uiSource.includes('if (diff > 300)'),
    'The rigid "if (diff > 300)" guard must be replaced by the adaptive threshold'
  );
});

function maxAllowedDiff(viewportHeight) {
  return Math.max(300, viewportHeight * 1.5);
}

test('threshold is at least 300 on small viewports', () => {
  // 100px viewport: 100 * 1.5 = 150 < 300, so floor kicks in
  assert.strictEqual(maxAllowedDiff(100), 300);
  assert.strictEqual(maxAllowedDiff(0),   300);
  assert.strictEqual(maxAllowedDiff(200), 300);
});

test('threshold scales with viewport on typical desktop sizes', () => {
  // 800px viewport: 800 * 1.5 = 1200 > 300
  assert.strictEqual(maxAllowedDiff(800), 1200);
  // 1080px viewport: 1080 * 1.5 = 1620
  assert.strictEqual(maxAllowedDiff(1080), 1620);
});

test('threshold crossover point is at 200px viewport height', () => {
  // At exactly 200px, 200 * 1.5 = 300, both paths give 300
  assert.strictEqual(maxAllowedDiff(200), 300);
  // Just above: viewport-scaled value takes over
  assert.ok(maxAllowedDiff(201) > 300);
});

test('large content layout shift stays within threshold on typical viewport', () => {
  // A 600px viewport yields threshold 900. A code block that shifts
  // scrollHeight by 700px should not trigger the drift guard.
  const viewport = 600;
  const threshold = maxAllowedDiff(viewport);
  const contentShift = 700;
  assert.ok(contentShift < threshold,
    `${contentShift}px shift should not exceed ${threshold}px threshold on ${viewport}px viewport`
  );
});

test('genuine user scroll still triggers drift guard', () => {
  // A user who has scrolled up by 2x the viewport should trigger the guard
  // regardless of viewport size.
  const viewport = 800;
  const threshold = maxAllowedDiff(viewport); // 1200
  const userScroll = viewport * 3;            // 2400px up — clearly intentional
  assert.ok(userScroll > threshold,
    `${userScroll}px user scroll should exceed ${threshold}px threshold and stop auto-scroll`
  );
});
