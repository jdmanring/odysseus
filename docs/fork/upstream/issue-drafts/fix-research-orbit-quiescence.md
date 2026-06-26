# Upstream Issue Draft: fix-research-orbit-quiescence

**File on:** `pewdiepie-archdaemon/odysseus`
**Related PR draft:** `docs/fork/upstream/pr-drafts/fix-research-orbit-quiescence.md`
**Branch:** `fix/research-orbit-quiescence`
**Type:** Performance

## Title
`perf(research): remove the animated orbit border ring (perpetual repaint / VRAM cost)`

## Body
The Research pane's animated accent ring (`_ensureOrbit` rAF driving a full-pane `conic-gradient` + mask on `.research-pane::after`) is a perpetual per-frame **repaint** while the panel is open — invisible on a fast GPU, but a CPU fire under software rendering (a GPU-driver fallback to llvmpipe pegged ~12 cores on it).

Making it a compositor transform instead fixes the CPU cost but trades it for a **dedicated GPU layer** — measured ~32 MB texture on a hi-res pane (it scales with screen size). For Odysseus specifically, which runs **local models**, video memory is the scarce resource: that VRAM is the model's context window, so spending ~20–32 MB on a border effect is the wrong trade on any device and can push a marginal model OOM.

**Fix:** remove the effect. Research-job activity is already signalled by the rail pulse, the running dots, and the round counter — the ring is redundant decoration. Affected: `static/js/research/panel.js`, `static/style.css`.
