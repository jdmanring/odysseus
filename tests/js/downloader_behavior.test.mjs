// Behavioral tests for the download-card state machine, driven by REAL
// aria2c transcripts (tests/fixtures/) — not synthetic strings.
//
// cookbookRunning.js imports DOM-heavy modules at load, so the pure
// functions under test are extracted by brace-matching from the source and
// evaluated in a bare VM context. If extraction fails (function renamed or
// moved), the test fails loudly — that is intentional: these functions are
// the contract.
//
// Run: node --test tests/js/downloader_behavior.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SRC = readFileSync(join(ROOT, 'static', 'js', 'cookbookRunning.js'), 'utf8');
const FIX = (name) => readFileSync(join(ROOT, 'tests', 'fixtures', name), 'utf8');

// ── extraction harness ──────────────────────────────────────────────────────
function extractBlock(startMarker) {
  const start = SRC.indexOf(startMarker);
  assert.notEqual(start, -1, `marker not found in source: ${startMarker}`);
  // brace-match from the first '{' after the marker
  const open = SRC.indexOf('{', start);
  let depth = 0, i = open;
  for (; i < SRC.length; i++) {
    if (SRC[i] === '{') depth++;
    else if (SRC[i] === '}') { depth--; if (depth === 0) break; }
  }
  return SRC.slice(start, i + 1);
}

function buildSandbox() {
  const code = [
    'const _dlFileTracker = new Map();',
    extractBlock('function _parseIecBytes'),
    extractBlock('function _fmtIecBytes'),
    extractBlock('function _fmtSpeed'),
    extractBlock('function _fmtEtaSecs'),
    extractBlock('function _parseDownloadState'),
    extractBlock('function _isAria2cRun'),
    extractBlock('function _authStatusForTask'),
    extractBlock('export function _shouldStopBackgroundMonitor').replace(/^export /, ''),
    extractBlock('export function _nextDownloadStatus').replace(/^export /, ''),
  ].join('\n');
  const ctx = { console, Math, Date, JSON };
  vm.createContext(ctx);
  vm.runInContext(code + `
    ;globalThis.api = { _parseDownloadState, _isAria2cRun, _shouldStopBackgroundMonitor, _authStatusForTask, _nextDownloadStatus, _dlFileTracker };`,
    ctx);
  return ctx.api;
}

const api = buildSandbox();
const SID = 'test-session';

// ── phase truth against a real complete run ────────────────────────────────
test('complete launcher output WITHOUT wrapper sentinel is NOT done', () => {
  // The launcher prints "[*] Download complete." and /snapshots/ paths; only
  // the tmux wrapper appends DOWNLOAD_OK. Trusting the loose markers is the
  // exact bug that showed "finished before finished" (defect D5).
  const out = FIX('aria2c_transcript_tiny_success.txt');
  assert.match(out, /Download complete/);
  assert.match(out, /\/snapshots\//);
  const st = api._parseDownloadState(out, SID);
  assert.equal(st.done, false, 'done must require the DOWNLOAD_OK sentinel');
  assert.equal(st.failed, false);
});

test('same output WITH the wrapper sentinel is done', () => {
  const out = FIX('aria2c_transcript_tiny_success.txt') + '\nDOWNLOAD_OK\n';
  const st = api._parseDownloadState(out, SID);
  assert.equal(st.done, true);
  assert.equal(st.failed, false);
});

test('mid-run transcript: neither done nor failed, progress parsed', () => {
  const out = FIX('aria2c_transcript_midrun.txt');
  const st = api._parseDownloadState(out, `${SID}-mid`);
  assert.equal(st.done, false);
  assert.equal(st.failed, false);
  assert.equal(st.totalFiles, 10, 'file count from "[*] N file(s) to download"');
});

test('long-form progress line parses pct/speed/eta; xet 403 noise is not failure', () => {
  const out = FIX('aria2c_progress_longform.txt');
  const st = api._parseDownloadState(out, `${SID}-long`);
  assert.equal(st.failed, false,
    'transient xet-bridge 403 "Download aborted" lines are NORMAL, never a failure');
  assert.equal(st.done, false);
  assert.ok(st.pct > 0 && st.pct <= 100, `pct parsed (got ${st.pct})`);
});

test('DOWNLOAD_FAILED sentinel wins regardless of earlier optimistic lines', () => {
  const out = FIX('aria2c_transcript_midrun.txt') + '\n[!] Download failed (aria2c exit 1).\nDOWNLOAD_FAILED (exit 1)\n';
  const st = api._parseDownloadState(out, `${SID}-fail`);
  assert.equal(st.failed, true);
});

// ── aria2c-run detection (defect D5's adopted-task gap) ─────────────────────
test('_isAria2cRun: payload flag, output fingerprint, and hf-negative', () => {
  assert.equal(api._isAria2cRun({ payload: { use_aria2c: true }, output: '' }), true);
  // adopted task: NO payload flag, detected by launcher fingerprint
  assert.equal(api._isAria2cRun({ payload: { repo_id: 'x' }, output: '[*] Using aria2c: /usr/bin/aria2c\n' }), true);
  // adopted task: detected by gid progress line alone
  assert.equal(api._isAria2cRun({ payload: {}, output: '[#d48f1e 1.5GiB/4.1GiB(37%) CN:2 DL:21MiB ETA:2m2s]' }), true);
  // hf-CLI output must NOT be classified aria2c (its loose markers stay valid)
  assert.equal(api._isAria2cRun({ payload: {}, output: "Downloading 'model.safetensors' to '.incomplete'\nmodel-00001-of-00002.safetensors: 56%|" }), false);
  assert.equal(api._isAria2cRun(null), false);
});

// ── monitor stop decision (defect D8's launch race) ─────────────────────────
test('monitor must NOT stop when localStorage has a live task the server has not registered yet', () => {
  // the launch race: first poll returns an empty server list in the same
  // tick as the download POST
  assert.equal(api._shouldStopBackgroundMonitor([], true), false);
  assert.equal(api._shouldStopBackgroundMonitor(null, true), false);
});

test('monitor stops only when BOTH views are idle', () => {
  assert.equal(api._shouldStopBackgroundMonitor([], false), true);
  assert.equal(api._shouldStopBackgroundMonitor([{ status: 'done' }], false), true);
  assert.equal(api._shouldStopBackgroundMonitor([{ status: 'running' }], false), false);
  assert.equal(api._shouldStopBackgroundMonitor([{ status: 'error' }], false), false);
});

// ── auth pill survival (the "auth indicator is missing" regression) ─────────
test('auth status survives after the header lines scroll out of the capture window', () => {
  // parsed output wins while present
  assert.equal(api._authStatusForTask({ type: 'download' }, 'authenticated'), 'authenticated');
  // once persisted on the task, it survives an output that lost the header
  assert.equal(api._authStatusForTask({ type: 'download', _authStatus: 'authenticated' }, ''), 'authenticated');
  // payload fallback when nothing was ever parsed
  assert.equal(api._authStatusForTask({ type: 'download', payload: { hf_token: 'hf_x' } }, ''), 'token provided');
  assert.equal(api._authStatusForTask({ type: 'download', payload: { hf_token: '' } }, ''), 'no token — public models only');
  // never invents a pill for non-downloads or unknown auth
  assert.equal(api._authStatusForTask({ type: 'serve', _authStatus: 'authenticated' }, ''), '');
  assert.equal(api._authStatusForTask({ type: 'download', payload: { repo_id: 'x' } }, ''), '');
});

// ── quant quality ladder consistency (cookbookDownload.js) ──────────────────
test('quant tier ranges cover the quality ladder exactly, and modern 6-bit variants outrank Q6_K', () => {
  const dlSrc = readFileSync(join(ROOT, 'static', 'js', 'cookbookDownload.js'), 'utf8');
  const grab = (marker) => {
    const start = dlSrc.indexOf(marker);
    assert.notEqual(start, -1, `marker not found: ${marker}`);
    const open = dlSrc.indexOf('[', start);
    let depth = 0, i = open;
    for (; i < dlSrc.length; i++) {
      if (dlSrc[i] === '[') depth++;
      else if (dlSrc[i] === ']') { depth--; if (depth === 0) break; }
    }
    return vm.runInNewContext(dlSrc.slice(open, i + 1));
  };
  const quality = grab('const _QUANT_QUALITY');
  const ranges = grab('const _QUANT_TIER_RANGES');
  // ranges must tile [0, quality.length) contiguously — an insertion into the
  // ladder without updating the index table silently corrupts tier matching
  let next = 0;
  for (const [start, end] of ranges) {
    assert.equal(start, next, `tier range starts at ${start}, expected ${next}`);
    assert.ok(end >= start);
    next = end + 1;
  }
  assert.equal(next, quality.length, 'ranges must cover every ladder entry');
  // modern 6-bit variants outrank plain Q6_K (lower index = better)
  assert.ok(quality.indexOf('UD-Q6_K_XL') < quality.indexOf('Q6_K'));
  assert.ok(quality.indexOf('Q6_K_L') < quality.indexOf('Q6_K'));
  assert.ok(quality.indexOf('UD-Q4_K_XL') < quality.indexOf('Q4_K_M'));
});

// ── output compaction (the vanished multi-file bars regression) ─────────────
test('URL-noise walls must not evict the progress summary the file bars need', () => {
  const ctx2 = { console, Math, JSON };
  vm.createContext(ctx2);
  vm.runInContext(
    'const _DL_OUTPUT_KEEP = 20000;' +
    extractBlock('function _compactDlOutput') +
    ';globalThis.compact = _compactDlOutput;', ctx2);
  const summary = [
    ' *** Download Progress Summary as of Mon Jul 20 02:14:37 2026 ***',
    '===============================================================================',
    '[#aaaa01 1.1GiB/7.9GiB(14%) CN:2 DL:2.8MiB ETA:40m43s]',
    'FILE: /home/user/.cache/huggingface/hub/models--x--y/snapshots/abc/model-00001-of-00003.safetensors',
    '-------------------------------------------------------------------------------',
    '[#aaaa02 0.4GiB/2.0GiB(20%) CN:2 DL:1.1MiB ETA:20m1s]',
    'FILE: /home/user/.cache/huggingface/hub/models--x--y/snapshots/abc/model-00002-of-00003.safetensors',
    '-------------------------------------------------------------------------------',
  ].join('\n');
  // simulate the xet-bridge redirect walls: three ~2.5KB signed-URL notices
  const urlWall = Array.from({length: 3}, (_, i) =>
    `07/20 02:14:40 [NOTICE] CUID#${i} - Redirecting to https://us.aws.cdn.hf.co/xet-bridge-us/${'A'.repeat(2500)}`
  ).join('\n');
  const raw = summary + '\n' + urlWall;
  // old behavior: slice(-5000) keeps mostly URL wall, summary evicted
  assert.ok(!raw.slice(-5000).includes('Download Progress Summary'),
    'precondition: the old 5000-char window loses the summary to URL noise');
  const kept = ctx2.compact(raw);
  assert.ok(kept.includes('Download Progress Summary'));
  assert.ok(kept.includes('[#aaaa01') && kept.includes('[#aaaa02'),
    'both per-file progress lines survive compaction');
  const st = api._parseDownloadState(kept, 'compact-test');
  assert.equal(st.perFileData.length, 2, 'parser sees one row per file again');
});

// ── poll-loop state machine over real transcripts (tier-1 harness) ─────────
// Simulates what the client actually sees: a rolling 500-line capture window
// sliding over a real pane transcript, fed in order through the status
// reducer. Pins the invariant that broke all week: status never regresses
// out of 'done', and 'done' appears ONLY after the DOWNLOAD_OK sentinel.
function* rollingWindows(transcript, winLines = 500, stride = 25) {
  const lines = transcript.split('\n');
  for (let end = stride; end < lines.length + stride; end += stride) {
    const e = Math.min(end, lines.length);
    yield lines.slice(Math.max(0, e - winLines), e).join('\n');
  }
}

function runMachine(transcript, { liveStatus } = {}) {
  let status = 'running';
  const trace = [];
  for (const win of rollingWindows(transcript)) {
    status = api._nextDownloadStatus(status, win, liveStatus);
    trace.push({ status, hasOk: win.includes('DOWNLOAD_OK'), hasFail: win.includes('DOWNLOAD_FAILED') });
  }
  return trace;
}

test('multi-file success run: done only after DOWNLOAD_OK enters the window, then sticky', () => {
  const trace = runMachine(FIX('aria2c_transcript_multifile_success.txt'));
  const firstDone = trace.findIndex(t => t.status === 'done');
  assert.notEqual(firstDone, -1, 'machine never reached done on a successful run');
  for (let i = 0; i < firstDone; i++) {
    assert.notEqual(trace[i].status, 'done', 'done before sentinel');
    assert.notEqual(trace[i].status, 'error', `false error at window ${i} on a successful run`);
  }
  assert.equal(trace[firstDone].hasOk, true, 'done entered without the sentinel in-window');
  for (let i = firstDone; i < trace.length; i++) {
    assert.equal(trace[i].status, 'done', `done regressed at window ${i}`);
  }
});

test('done survives the window scrolling PAST the sentinel and a dead-pane stopped report', () => {
  // After completion the pane keeps its shell prompt; a later poll may see a
  // window with no sentinel at all, and the blind background poll may see the
  // server report the dead pane as 'stopped'. Neither may regress 'done'.
  assert.equal(api._nextDownloadStatus('done', 'shell prompt, no markers', undefined), 'done');
  assert.equal(api._nextDownloadStatus('done', '', 'stopped'), 'done');
  assert.equal(api._nextDownloadStatus('done', 'random [ERROR] CUID#7 errorCode=24', 'error'), 'done');
});

test('gated failure run: benign errorCode=24 walls stay running; only the sentinel fails it', () => {
  const fx = FIX('aria2c_transcript_gated_failure.txt');
  assert.match(fx, /errorCode=24/);
  const trace = runMachine(fx);
  const firstErr = trace.findIndex(t => t.status === 'error');
  assert.notEqual(firstErr, -1, 'gated run never classified as error');
  for (let i = 0; i < firstErr; i++) {
    assert.equal(trace[i].status, 'running', `errorCode=24 noise misclassified at window ${i}`);
  }
  assert.equal(trace[firstErr].hasFail, true, 'error entered without DOWNLOAD_FAILED in-window');
});

test('aria2c exit-2 failure run: fails only on the sentinel, never on optimistic per-file lines', () => {
  const trace = runMachine(FIX('aria2c_transcript_exit2_failure.txt'));
  const firstErr = trace.findIndex(t => t.status === 'error');
  assert.notEqual(firstErr, -1);
  assert.equal(trace[firstErr].hasFail, true);
  for (let i = 0; i < firstErr; i++) assert.notEqual(trace[i].status, 'done', 'false done on a failed run');
});

test('mid-run window: stays running under aria2c noise', () => {
  const trace = runMachine(FIX('aria2c_transcript_midrun.txt'));
  for (const t of trace) assert.equal(t.status, 'running');
});

test('DOWNLOAD_OK beats DOWNLOAD_FAILED when one pane holds both (failed attempt, then success)', () => {
  const both = 'DOWNLOAD_FAILED (exit 1)\n...retry...\nDOWNLOAD_OK';
  assert.equal(api._nextDownloadStatus('running', both), 'done');
});

test('auth pill: token + reached downloading phase infers authenticated (header lines evicted)', () => {
  const t = { type: 'download', payload: { hf_token_used: true } };
  assert.equal(api._authStatusForTask(t, '', 'downloading'), 'authenticated');
  assert.equal(api._authStatusForTask(t, '', 'done'), 'authenticated');
  // not yet resolved → still pending, not a lie
  assert.equal(api._authStatusForTask(t, '', 'resolving'), 'token provided');
  // no token never upgrades
  assert.equal(api._authStatusForTask({ type: 'download', payload: { hf_token_used: false } }, '', 'downloading'),
    'no token — public models only');
});

// ── /api/shell/exec outcome semantics (tier-2: guard the behavior, not the string)
const SERVE_SRC = readFileSync(join(ROOT, 'static', 'js', 'cookbookServe.js'), 'utf8');
function extractFromServe(marker) {
  const start = SERVE_SRC.indexOf(marker);
  assert.notEqual(start, -1, `marker not found in cookbookServe.js: ${marker}`);
  const open = SERVE_SRC.indexOf('{', start);
  let depth = 0, i = open;
  for (; i < SERVE_SRC.length; i++) {
    if (SERVE_SRC[i] === '{') depth++;
    else if (SERVE_SRC[i] === '}') { depth--; if (depth === 0) break; }
  }
  return SERVE_SRC.slice(start, i + 1).replace(/^export /, '');
}

test('shell-exec outcome: HTTP 200 with nonzero exit_code is a FAILURE, not success', () => {
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(extractFromServe('export function _shellExecFailure')
    + ';globalThis.f = _shellExecFailure;', ctx);
  const f = ctx.f;
  // real success shape
  assert.equal(f({ exit_code: 0, stdout: '', stderr: '' }), '');
  // failed rm: HTTP 200, exit_code 1 — must surface stderr
  assert.equal(f({ exit_code: 1, stderr: 'rm: cannot remove: Permission denied' }),
    'rm: cannot remove: Permission denied');
  // stdout-only failure (some shells write errors to stdout)
  assert.equal(f({ exit_code: 2, stdout: 'no such file' }), 'no such file');
  // unparseable / missing body is a failure, never a silent success
  assert.equal(f(null), 'unknown error');
  assert.equal(f({}), 'unknown error');
  // the delete path must actually consume it
  assert.match(SERVE_SRC, /_shellExecFailure\(_delResult\)/);
});

// ── tier-4 adjacent paths: pause/resume semantics and the full card build ──
test('paused is user intent: no window content or live report may flip it', () => {
  // Pause sends C-c, which makes the wrapper print DOWNLOAD_FAILED — that
  // artifact must never turn a paused task into error/crashed.
  assert.equal(api._nextDownloadStatus('paused', 'DOWNLOAD_FAILED (exit 1)'), 'paused');
  assert.equal(api._nextDownloadStatus('paused', '', 'stopped'), 'paused');
  assert.equal(api._nextDownloadStatus('paused', '', 'error'), 'paused');
  // even a stale DOWNLOAD_OK from a previous attempt in the same scrollback
  // does not auto-resume a task the user paused
  assert.equal(api._nextDownloadStatus('paused', 'DOWNLOAD_OK'), 'paused');
});

function buildCardSandbox() {
  const UI_SRC = readFileSync(join(ROOT, 'static', 'js', 'ui.js'), 'utf8');
  const escStart = UI_SRC.indexOf('export function esc');
  assert.notEqual(escStart, -1);
  const escOpen = UI_SRC.indexOf('{', escStart);
  let d = 0, j = escOpen;
  for (; j < UI_SRC.length; j++) {
    if (UI_SRC[j] === '{') d++;
    else if (UI_SRC[j] === '}') { d--; if (d === 0) break; }
  }
  const code = [
    'const _dlFileTracker = new Map();',
    // esc() depends on module-level _ESC_MAP — pull the REAL line from ui.js
    UI_SRC.split('\n').find(l => l.startsWith('const _ESC_MAP')),
    UI_SRC.slice(escStart, j + 1).replace(/^export /, ''),
    extractBlock('function _parseIecBytes'),
    extractBlock('function _fmtIecBytes'),
    extractBlock('function _fmtSpeed'),
    extractBlock('function _fmtEtaSecs'),
    extractBlock('function _parseDownloadState'),
    extractBlock('function _midTrunc'),
    extractBlock('function _buildSingleFileRow'),
    extractBlock('function _authStatusForTask'),
    extractBlock('function _buildAuthPillHtml'),
    extractBlock('function _buildDownloadCardHtml'),
  ].join('\n');
  const ctx = { console, Math, Date, JSON };
  vm.createContext(ctx);
  vm.runInContext(code + ';globalThis.build = _buildDownloadCardHtml;', ctx);
  return ctx.build;
}

test('card build: paused status overrides a downloading transcript (pause during downloading)', () => {
  const build = buildCardSandbox();
  const out = FIX('aria2c_transcript_midrun.txt');
  const html = build({ status: 'paused', output: out, sessionId: 'sid-p' });
  assert.match(html, /data-dl-phase="paused"/,
    'paused task must render the paused card even while the pane still shows progress');
});

test('card build: multi-file run renders downloading phase with per-file rows', () => {
  const build = buildCardSandbox();
  const out = FIX('aria2c_transcript_midrun.txt');
  const html = build({ status: 'running', output: out, sessionId: 'sid-m' });
  assert.match(html, /data-dl-phase="downloading"/);
  assert.match(html, /dl-file-row/, 'per-file progress rows missing for a parallel download');
});

test('card build: early flood window (no markers yet) renders initializing, not error', () => {
  const build = buildCardSandbox();
  const html = build({ status: 'running', output: 'random noise with no markers', sessionId: 'sid-i' });
  assert.match(html, /data-dl-phase="initializing"/);
});
