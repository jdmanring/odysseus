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
  ].join('\n');
  const ctx = { console, Math, Date, JSON };
  vm.createContext(ctx);
  vm.runInContext(code + `
    ;globalThis.api = { _parseDownloadState, _isAria2cRun, _shouldStopBackgroundMonitor, _authStatusForTask, _dlFileTracker };`,
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
