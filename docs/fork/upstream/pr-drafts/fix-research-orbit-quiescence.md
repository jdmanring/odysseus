# Upstream PR Draft: fix-research-orbit-quiescence

**Branch:** `fix/research-orbit-quiescence` (from `upstream-mirror`)
**Target:** `pewdiepie-archdaemon/odysseus:dev`
**Fixes:** #_ (file issue-drafts/fix-research-orbit-quiescence.md first)
**Filing notes:** Net diff vs `dev` = remove the orbit ring (the branch's interim throttle/compositor commits were exploration; squash on filing).

## Title
`perf(research): remove the animated orbit border ring`

## Description
The orbit ring was a perpetual full-pane repaint (conic-gradient + mask driven by an rAF). Throttling/compositing it only moved the cost around: a compositor version needs a dedicated GPU layer (~32 MB texture on a hi-res pane). Odysseus runs local models, where VRAM is the scarce resource (it's the model's context), so a border effect should not hold a GPU layer. Removed it; job activity is still shown by the rail pulse / running dots / round counter.

## Tests
`tests/test_research_orbit_quiescence.py` — guards that the orbit DOM/CSS and any `will-change` layer in the research pane stay removed.

## Risk
None functional — pure decoration removed; the pane and its other indicators are unchanged.
