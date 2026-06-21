// Deferred syntax highlighting via IntersectionObserver.
//
// hljs.highlightElement() allocates hundreds of <span> nodes per code block.
// Calling it immediately for off-screen blocks (history loads, frozen streaming
// blocks above the viewport) generates Oilpan garbage that may never be seen.
//
// This module queues code blocks for highlight-on-scroll: the single shared
// observer fires when a block enters within 200px of the viewport and highlights
// it exactly once. Blocks that are already on-screen fire within one observer
// tick (~16 ms) — no perceptible delay.
//
// Usage:
//   import { deferHighlight, deferHighlightAll } from './hljsDefer.js';
//   deferHighlight(codeEl);          // one <pre><code> element
//   deferHighlightAll(containerEl);  // all pre code:not(.hljs) inside root
//
// Non-module scripts access the same functions via window.hljsDeferHighlightAll,
// set by the first ES-module caller (chat.js init).

const _obs = new IntersectionObserver(
  function (entries) {
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry.isIntersecting) continue;
      var block = entry.target;
      _obs.unobserve(block);
      if (window.hljs && !block.classList.contains('hljs')) {
        window.hljs.highlightElement(block);
      }
    }
  },
  { rootMargin: '200px 0px' }
);

export function deferHighlight(block) {
  if (!window.hljs || block.classList.contains('hljs')) return;
  _obs.observe(block);
}

export function deferHighlightAll(root) {
  var blocks = root.querySelectorAll('pre code:not(.hljs)');
  for (var i = 0; i < blocks.length; i++) deferHighlight(blocks[i]);
}
