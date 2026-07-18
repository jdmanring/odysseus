# Verified citations for the #2 upstream contribution (plan Part 2.3)

Each source was OPENED AND VERIFIED (2026-07-18) with the quoted line confirmed present.
Use these in the file-time draft rewrite; re-verify links at filing.

| claim | source | verified quote |
|---|---|---|
| Removed-but-referenced DOM stays in memory (why true node removal beats detach-preserve) | MDN, "Memory management" — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Memory_management | "Starting from the roots, the garbage collector will thus find all *reachable* objects and collect all non-reachable objects." |
| Detached-reference leaks are a recognized failure class | web.dev, "Detached window memory leaks" — https://web.dev/articles/detached-window-memory-leaks | "These references prevent the unneeded objects from being reclaimed by the garbage collector." |
| Observers must be disconnected on teardown | MDN, `IntersectionObserver.disconnect()` — https://developer.mozilla.org/en-US/docs/Web/API/IntersectionObserver/disconnect | "The `disconnect()` method … stops the observer watching all of its target elements for visibility changes." |
| IO delivers QUEUED entries — several per callback (grounds the newest-entry sentinel read) | W3C Intersection Observer spec — https://www.w3.org/TR/intersection-observer/ | "Let queue be a copy of observer's internal `[[QueuedEntries]]` slot... Invoke callback with queue as the first argument…" |
| Windowing/virtualization is the standard treatment for large lists (prior art, not source) | react-window — https://github.com/bvaughn/react-window | "React components for efficiently rendering large lists and tabular data" |
| DOM/C++ object lifetime is Oilpan-managed in Blink (why JS-heap-only metrics miss DOM cost) | V8 blog, "Oilpan library" — https://v8.dev/blog/oilpan-library | "Oilpan was initially developed specifically for Blink to simplify the programming model and get rid of memory leaks and use-after-free issues." |

Measured evidence lives in the generated benchmark artifact (`tests/bench/results/`) — never
transcribed here. The comparison matrix (Part 2.1) is derived from that artifact at file time.
