# Upstream PR Draft: fix-research-orbit-quiescence

**Branch:** `fix/research-orbit-quiescence` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Fixes:** #_ (file issue-drafts/fix-research-orbit-quiescence.md first)
**Filing notes:** Single concern, one commit. JS-only (the conic-gradient visual is unchanged).

---

## Title

`perf(research): run orbit ring only during active jobs; throttle + quiesce`

## Description

`--research-orbit-angle` feeds a conic-gradient + mask on `.research-pane::after`, so advancing
it every frame is a full-pane **repaint**. The old rAF loop ran perpetually while the panel was
open — even idle with no job — a continuous paint producer (invisible on a GPU, but a CPU fire
under software rendering).

**Change** (`static/js/research/panel.js`):
- Loop runs only while a research job is active (`_orbitActive = running > 0`).
- Pauses on `document.hidden` and `prefers-reduced-motion` (`_orbitShouldRun`).
- Throttles the repaint to ~30fps (the orbit is slow; halves re-raster work).
- Re-evaluates on `visibilitychange` so a job's orbit stops in the background and resumes on
  return. When inactive the ring holds a static angle — still visible, zero cost.

Visual unchanged (same conic-gradient ring); only the drive frequency changes.

## Tests

`tests/test_research_orbit_quiescence.py` (5 static guards): job-gated; visibility/reduced-motion
gate; repaint throttle; visibilitychange re-eval; clean `cancelAnimationFrame` stop.

## Risk
Low — JS-only, single caller, falls back to a static ring when inactive.
