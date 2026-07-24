#!/usr/bin/env python3
"""Compare embedding backends on retrieval quality and per-item latency.

Reproduces the claims in docs/dev/memory-architecture.md's backend-selection
section: that retrieval accuracy is backend/quant-independent on this workload,
and that per-item latency (the hot path) is a few ms on llama.cpp Q8. Run it to
regenerate the numbers rather than trusting a stale figure in prose.

    venv/bin/python tooling/benchmark_embedding_backends.py

It builds a small topic-labelled corpus, embeds documents and queries with each
available backend (fastembed INT8 and llama.cpp Q8_0), and reports:
  * top-1 topic-match accuracy per backend (retrieval correctness), and
  * cross-backend ranking agreement (do they retrieve the same doc?), and
  * single-item embed latency (p50).

Only backends that are installed are run, so it works on the BSDs (llama.cpp
only) and elsewhere (both).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

# Topic-labelled corpus: 6 topics x 5 documents. Queries are paraphrases (no term
# overlap with the target doc) so retrieval must be semantic, not lexical; several
# topics are deliberately adjacent (astronomy/physics, medicine/biology) so a weak
# model confuses them and accuracy does NOT saturate at 1.000 — that's what makes
# the set able to tell a better model from an equal one.
CORPUS = [
    ("astronomy", "A red giant is a dying star in a late phase of stellar evolution."),
    ("astronomy", "The event horizon marks the boundary of a black hole in spacetime."),
    ("astronomy", "Nebulae are clouds of interstellar gas where new stars are born."),
    ("astronomy", "A supernova is the explosive death of a massive star."),
    ("astronomy", "Exoplanets orbit stars beyond our own solar system."),
    ("physics", "Entropy measures the disorder of a thermodynamic system."),
    ("physics", "Superconductors carry current with zero electrical resistance."),
    ("physics", "The uncertainty principle bounds simultaneous knowledge of position and momentum."),
    ("physics", "Refraction bends light as it passes between media of different density."),
    ("physics", "A pendulum's period depends on its length and local gravity."),
    ("cooking", "Searing meat at high heat develops flavour through the Maillard reaction."),
    ("cooking", "Proofing dough lets yeast ferment and the bread rise before baking."),
    ("cooking", "Emulsifying egg yolk and oil slowly is how you make mayonnaise."),
    ("cooking", "Deglazing a pan with wine lifts the fond into a sauce."),
    ("cooking", "Blanching vegetables briefly sets their colour and halts enzymes."),
    ("finance", "A bond's yield moves inversely to its price on the secondary market."),
    ("finance", "Diversifying a portfolio spreads risk across uncorrelated assets."),
    ("finance", "Compound interest grows principal faster as returns are reinvested."),
    ("finance", "Inflation erodes the purchasing power of held currency over time."),
    ("finance", "A short seller profits when the borrowed asset falls in price."),
    ("medicine", "Antibiotics treat bacterial infections but do nothing against viruses."),
    ("medicine", "The immune system produces antibodies in response to an antigen."),
    ("medicine", "Insulin regulates blood glucose by signalling cells to absorb sugar."),
    ("medicine", "Vaccines prime immunity by presenting a harmless piece of a pathogen."),
    ("medicine", "Anaesthesia suppresses pain signalling during surgery."),
    ("biology", "Photosynthesis converts sunlight into chemical energy in plants."),
    ("biology", "Mitosis divides one cell into two genetically identical daughters."),
    ("biology", "Natural selection favours traits that improve reproductive success."),
    ("biology", "Enzymes catalyse reactions by lowering activation energy."),
    ("biology", "DNA encodes heredity in sequences of four nucleotide bases."),
]
# ---------------------------------------------------------------------------
# HARD SET — built after the all-MiniLM A/B showed the topic corpus saturates
# for both models (top-1 0.917-1.000): it can prove backend/quant neutrality
# but cannot separate models. This set targets the two axes where the models
# genuinely differ, with content shaped like REAL memory-store entries and
# personal-doc chunks (the production workloads), not encyclopedia trivia:
#
#   * TRAPS — pairs of plausible stored memories that share surface vocabulary
#     but differ in meaning (python the pet vs Python the language, SSH keys
#     vs house keys). Retrieval must resolve polysemy from context; lexical
#     overlap actively points at the wrong memory.
#   * LONG — consolidated-note/document chunks (~300+ words, the size
#     personal_docs.py actually produces at CHUNK_SIZE=2048 chars) where the
#     queried fact sits in the final quarter — PAST all-MiniLM's 256-token
#     window, within nomic's. Each has a short same-topic decoy that lacks
#     the fact. A truncating model literally cannot see the answer.
#
# All hard docs score against ONE pool (like a real memory store). Accuracy
# is deterministic per backend, so a single run reproduces exactly.
HARD_TRAPS = [
    # (query, target_text, decoy_text)
    ("when does the user get their teeth checked",
     "The user's dentist appointment recurs every six months at the downtown clinic.",
     "The user's dog has a vet appointment every six months for booster vaccinations."),
    ("which color scheme does the user's IDE use after sunset",
     "The user switches their code editor to a dark theme in the evening.",
     "The user prefers dark roast beans, ground right before brewing."),
    ("what is the user's snake called",
     "The user's pet python is named Monty and gets fed every Friday.",
     "The user writes most automation scripts in Python with strict type hints."),
    ("which programming language did the user migrate away from",
     "The user ported the backend service from Java to Go last spring.",
     "The user orders a single-origin java at the corner cafe most mornings."),
    ("who holds the user's backup key to the front door",
     "The user keeps a spare house key with the neighbor two doors down.",
     "The user rotates SSH keys on the first of every month."),
    ("how much system memory does the user's desktop have",
     "The user upgraded their workstation to 64 GB of RAM in March.",
     "The user practices memory palace techniques when studying for exams."),
    ("which office location does the user visit weekly",
     "The user works from the bank's Riverside branch office on Tuesdays.",
     "The user names git branches with a ticket-number prefix."),
    ("which fruit causes the user an allergic reaction",
     "The user is allergic to apples but tolerates cooked pears fine.",
     "The user's laptop is an Apple silicon MacBook from 2023."),
    ("why does the user close the blinds after lunch",
     "The user's desk faces a south window that glares badly in the afternoon.",
     "The user tiles application windows with a keyboard-driven manager."),
    ("which golf club did the user recently have serviced",
     "The user had their golf driver regripped last summer.",
     "The user pins the GPU driver version to avoid rendering regressions."),
    ("what part-time job does the user do on Saturdays",
     "The user waits tables as a server on weekend evenings.",
     "The user's home server runs backups at two in the morning."),
    ("what treat does the user bring coworkers",
     "The user bakes oatmeal cookies for the office every Friday.",
     "The user clears browser cookies weekly out of privacy habit."),
    ("what souvenir does the user gather by the ocean",
     "The user collects seashells from every beach trip.",
     "The user's login shell is zsh with a deliberately minimal prompt."),
    ("which airport building does the user fly out of",
     "The user departs from terminal B for most work trips.",
     "The user prefers a tiling terminal emulator with a dark background."),
    ("what bedtime habit does the user keep for better rest",
     "The user aims for seven hours of sleep and avoids screens after eleven.",
     "The user disabled system sleep on the NAS so network shares stay available."),
]

_LONG_A = (
    "Home network notes, consolidated. The router was replaced in February with a "
    "unit that runs a community firmware build, chosen so the same configuration "
    "can be exported and restored after upgrades instead of being re-entered by "
    "hand. The main network uses the same SSID the household has had for years, "
    "and every wired device in the office hangs off the eight-port switch under "
    "the desk: the workstation, the NAS, the printer, and the test laptop dock. "
    "The NAS pulls a nightly snapshot of the shared folders at two in the "
    "morning and keeps fourteen days of history; restores have been tested twice "
    "and take about ten minutes for a single folder. Port forwarding is disabled "
    "except for the one rule the game console needs, and that rule is documented "
    "on the wiki page along with the DHCP reservations. Reserved addresses cover "
    "the printer, the NAS, both smart speakers, and the thermostat, which "
    "misbehaved twice after lease changes before it was pinned. The mesh "
    "extender in the hallway only serves the far bedroom and the porch camera; "
    "it bridges rather than routes, so all devices still appear on one subnet. "
    "DNS goes through the filtering resolver, with the kids' devices in a "
    "stricter policy group that shuts off social domains after nine on school "
    "nights. When friends visit they go on the guest network, which is isolated "
    "from the LAN and cannot reach the NAS or printer. For hygiene, the guest "
    "Wi-Fi password rotates on the first Sunday of each month, and the new one "
    "gets written on the whiteboard by the kitchen door."
)
_LONG_B = (
    "Workstation build and tuning log. The case swap happened in May because the "
    "old chassis could not fit the new cooler; everything else carried over "
    "except the power supply, which was replaced with a higher-efficiency unit "
    "after the old one developed coil whine under load. The build now runs the "
    "eight-core part at stock clocks — an experiment with a mild overclock was "
    "reverted after two crashes during long compiles, and stability has been "
    "clean since. Storage is split across a fast NVMe drive for the system and "
    "projects and a pair of larger SATA drives mirrored for archives; the mirror "
    "scrubs monthly and has never reported an error. The GPU is deliberately one "
    "generation old, bought used, and undervolted, which keeps it quiet and cool "
    "enough that its fans stay off at idle. Memory sits at 64 GB after the March "
    "upgrade, which ended the swapping that used to happen with several virtual "
    "machines open. Peripheral quirks are documented too: the webcam needs the "
    "rear USB port or it renegotiates constantly, and the audio interface wants "
    "its own bus. Thermal work finished in June with an afternoon of testing "
    "under sustained load at summer room temperatures, comparing three fan "
    "curves for noise against package temperature. After that June thermal "
    "test, the BIOS fan curve was set to the silent profile, trading about four "
    "degrees for near-inaudibility, and it has stayed there since."
)
_LONG_C = (
    "Garden journal, season summary. The raised beds were rebuilt in early "
    "spring with untreated cedar and refilled with a mix of last year's soil, "
    "fresh compost from the municipal program, and a bag of coarse sand to "
    "loosen drainage on the tomato side. Planting followed the usual order: "
    "peas and lettuce first while nights were still cold, then tomatoes, "
    "basil, and hot peppers after the last frost date, and finally the "
    "cucumbers once the trellis netting went up. The peas overperformed and "
    "shaded the lettuce longer than expected, which actually kept it from "
    "bolting until July. Pest pressure was mild: one aphid wave on the "
    "peppers handled with soap spray, and a groundhog that lost interest "
    "after the lower fence gap was blocked with paving stones. Watering is "
    "drip line on a morning timer for the beds, fifteen minutes on alternate "
    "days, which kept the tomatoes from splitting even in the August heat. "
    "The herb pots by the door dry out faster and get hand-watered whenever "
    "the top inch feels dry. The fruit trees follow their own schedule "
    "entirely: the young plum wants steady moisture and gets checked twice a "
    "week, while the fig, now in its third year and well established, gets a "
    "deep soak only every ten days — more than that and it puts out leaves "
    "at the expense of fruit, a lesson learned the hard way last summer."
)
_LONG_D = (
    "Trip planning notes, Lisbon in October. Flights are booked on points "
    "leaving the Thursday evening before the conference and returning the "
    "following Saturday morning, with the long layover outbound spent in the "
    "lounge rather than risking the tight connection that burned us in "
    "spring. The hotel is the small one near the funicular that was so good "
    "two years ago; breakfast is included this time, and the room is on the "
    "quiet side of the building per the confirmation email. The conference "
    "badge pickup is Friday morning, so Thursday night is free for the "
    "seafood place by the market — reservation already made under the usual "
    "name. Day trips are penciled in for the middle weekend: Sintra by train "
    "on Saturday if the weather holds, otherwise the tile museum and the "
    "aquarium. Phone plans are sorted with an eSIM purchased in advance that "
    "activates on landing, and the bank's travel notice is filed so the cards "
    "don't freeze at the first foreign charge. Packing is the usual carry-on "
    "setup with the folding tote for the return, since the book haul is "
    "inevitable. Paper backups matter after the phone-death fiasco in Rome: "
    "printed boarding passes and the hotel confirmation go in the blue "
    "folder, and the travel insurance policy — the one whose number ends in "
    "4471 — is kept in that same blue folder in the front pocket of the "
    "carry-on."
)
_LONG_E = (
    "Physio and running log. The knee flare-up in April turned out to be "
    "tendon irritation rather than anything structural, confirmed by the "
    "scan, and the rehab plan has been boring but effective: three sessions "
    "of targeted strength work per week, mostly single-leg presses, step-"
    "downs, and the balance-board routine, with soreness tracked in the "
    "notes app each evening. Swimming stayed on the menu throughout since it "
    "never aggravated anything, and the Friday pool session is now a fixture "
    "regardless of how the knee feels. The stationary bike came back in "
    "week four at low resistance, then hills by week eight. Footwear got an "
    "overhaul after the gait check — the cushioned pair for pavement, the "
    "older stable pair kept only for the gym. Sleep and load clearly "
    "correlate in the log: every setback week lines up with a stretch of "
    "short nights, so the eleven-o'clock screens-off rule counts as rehab "
    "too. The August review went well: full squat depth pain-free, no "
    "swelling after the test week, and the physiotherapist formally cleared "
    "running again — with the firm cap that runs stay at or under five "
    "kilometers until the October follow-up, on the flat river path only, "
    "no track intervals until then."
)
_LONG_F = (
    "Book club notes. The group has settled into a rhythm this year: one "
    "book a month, alternating fiction and nonfiction, chosen by rotation so "
    "nobody dominates the list. January's pick divided the room, February's "
    "was abandoned by half the group by chapter six, and the March memoir "
    "was the rare unanimous favorite that kept discussion going well past "
    "ten. The spreadsheet tracks attendance and ratings, and the running "
    "joke is that the harshest rater has never once finished a book she "
    "scored. Snacks rotate with hosting duties, and the unwritten rule "
    "against spoilers before everyone arrives is enforced with real "
    "conviction. Summer scheduling was the usual mess of vacations, so June "
    "and July merged into one long-novel month, which worked better than "
    "expected and might become tradition. The autumn lineup is set: the "
    "translated crime novel for September, the naturalist essays for "
    "October, and a member-published manuscript in November that everyone "
    "is being carefully kind about in advance. One logistics change to "
    "remember: because of the venue conflict with the school fundraiser, "
    "the next meeting has moved to the second Thursday of the month, at "
    "Elena's place instead of the library annex, potluck rules as usual."
)

HARD_LONG = [
    # (query, long_doc_with_late_fact, short_same_topic_decoy)
    ("how often does the guest network password change", _LONG_A,
     "Visitors at the user's home connect to an isolated guest Wi-Fi network."),
    ("what fan profile did the user settle on after thermal testing", _LONG_B,
     "The user's workstation was rebuilt in May with a new case and cooler."),
    ("how frequently does the established fig tree get watered", _LONG_C,
     "The user's garden grows tomatoes, basil, peppers, and a young fig tree."),
    ("where is the travel insurance document kept for the trip", _LONG_D,
     "The user is attending a conference in Lisbon in October."),
    ("what distance limit applies to the user's runs", _LONG_E,
     "The user is rehabbing a knee with physiotherapy and swims on Fridays."),
    ("where is the upcoming book club gathering being held", _LONG_F,
     "The user's book club meets monthly, alternating fiction and nonfiction."),
]


def evaluate_hard(client, name):
    """Score the hard set: one pooled index (like a real memory store), report
    per-section top-1. Deterministic per backend — no repetition needed."""
    pool, owners = [], []
    for i, (_q, target, decoy) in enumerate(HARD_TRAPS):
        pool += [target, decoy]; owners += [("trap", i, True), ("trap", i, False)]
    for i, (_q, long_doc, decoy) in enumerate(HARD_LONG):
        pool += [long_doc, decoy]; owners += [("long", i, True), ("long", i, False)]
    doc_vecs = np.asarray(client.encode(pool, is_query=False), dtype="float32")
    scores = {"trap": [0, 0], "long": [0, 0]}
    misses = []
    for section, items in (("trap", HARD_TRAPS), ("long", HARD_LONG)):
        for i, item in enumerate(items):
            q = item[0]
            qv = np.asarray(client.encode([q], is_query=True), dtype="float32")[0]
            top = int(np.argmax(doc_vecs @ qv))
            scores[section][1] += 1
            if owners[top] == (section, i, True):
                scores[section][0] += 1
            else:
                misses.append((section, q, pool[top][:60]))
    t, l = scores["trap"], scores["long"]
    print(f"  {name:16s} HARD traps {t[0]}/{t[1]}  long-docs {l[0]}/{l[1]}  "
          f"overall {(t[0] + l[0]) / (t[1] + l[1]):.3f}")
    if os.environ.get("BENCH_HARD_VERBOSE") == "1":
        for section, q, hit in misses:
            print(f"      miss [{section}] {q!r} -> {hit!r}...")
    return scores


QUERIES = [
    ("astronomy", "what happens to a star at the end of its life"),
    ("astronomy", "worlds circling distant suns"),
    ("physics", "why does a straw look bent in a glass of water"),
    ("physics", "materials that conduct electricity without any loss"),
    ("cooking", "why does browning make food taste better"),
    ("cooking", "turning pan drippings into gravy"),
    ("finance", "how does reinvesting returns build wealth over time"),
    ("finance", "why is cash worth less each year"),
    ("medicine", "how does the body defend against an infection"),
    ("medicine", "how do shots prevent disease"),
    ("biology", "how do green leaves make food from light"),
    ("biology", "how one cell becomes two identical cells"),
]


def _rank(doc_vecs, query_vec):
    sims = doc_vecs @ query_vec
    return np.argsort(-sims)


def evaluate(client, name):
    labels = [t for t, _ in CORPUS]
    docs = [d for _, d in CORPUS]
    doc_vecs = np.asarray(client.encode(docs, is_query=False), dtype="float32")
    # single-item latency — THE hot path. Every live request embeds one QUERY
    # (search_query: prefix), so that is what gets timed, and the tail matters
    # as much as the median for perceived response time, so report p50/p95/max.
    # perf_counter, not monotonic: on Windows (< 3.13) monotonic ticks at
    # ~15.6 ms, which quantizes every sub-tick embed to a meaningless 0.0.
    lat = []
    for topic, q in (QUERIES * 9)[:100]:
        t = time.perf_counter()
        client.encode([q], is_query=True)
        lat.append((time.perf_counter() - t) * 1000)
    lat.sort()

    # bulk throughput: embed all docs in one batched call (the reindex path).
    # Repeated 5x — a single sample can't distinguish a real difference from
    # one scheduler hiccup; report the median and the observed spread.
    bulk_docs = docs * 8  # 96 documents
    rates = []
    for _ in range(5):
        t = time.perf_counter()
        client.encode(bulk_docs, is_query=False)
        rates.append(len(bulk_docs) / (time.perf_counter() - t))
    rates.sort()
    bulk_rate = rates[2]
    bulk_spread = (rates[0], rates[-1])

    correct = correct3 = 0
    top1_docs = []
    for topic, q in QUERIES:
        qv = np.asarray(client.encode([q], is_query=True), dtype="float32")[0]
        order = _rank(doc_vecs, qv)
        top1_docs.append(int(order[0]))
        if labels[order[0]] == topic:
            correct += 1
        if any(labels[i] == topic for i in order[:3]):
            correct3 += 1
    acc = correct / len(QUERIES)
    acc3 = correct3 / len(QUERIES)
    n = len(lat)
    print(f"  {name:16s} top-1 {acc:.3f}  top-3 {acc3:.3f}  "
          f"query p50 {lat[n // 2]:.1f} / p95 {lat[int(n * 0.95) - 1]:.1f} / "
          f"p99 {lat[int(n * 0.99) - 1]:.1f} / max {lat[-1]:.1f} ms  "
          f"bulk {bulk_rate:.0f} docs/s median of 5 "
          f"[{bulk_spread[0]:.0f}-{bulk_spread[1]:.0f}] (reindex-only)")
    return acc, top1_docs


def _windows_idle_fraction(sample_s: float = 1.0):
    """CPU idle fraction over a short sample via GetSystemTimes (no psutil).
    Returns None if the call is unavailable."""
    import ctypes

    class _FT(ctypes.Structure):
        _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]

    def snap():
        idle, kern, user = _FT(), _FT(), _FT()
        if not ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
            raise OSError("GetSystemTimes failed")
        as64 = lambda t: (t.hi << 32) | t.lo
        # kernel time INCLUDES idle time; busy = (kern - idle) + user
        return as64(idle), as64(kern) + as64(user)
    try:
        i0, t0 = snap()
        time.sleep(sample_s)
        i1, t1 = snap()
        return (i1 - i0) / max(1, (t1 - t0))
    except Exception:
        return None


def _guard_idle_host():
    """Refuse to benchmark under load. These backends are CPU-bound with OpenMP
    threads, so a competing load (e.g. a VM compiling in the background) inflates
    per-item latency ~100x and makes the numbers meaningless — the failure that
    once nearly reversed an architecture decision. Set BENCH_FORCE=1 to override."""
    forced = os.environ.get("BENCH_FORCE") == "1"
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        # No loadavg (Windows): sample CPU idle directly so the guard still
        # has teeth there instead of silently waving everything through.
        idle = _windows_idle_fraction() if os.name == "nt" else None
        if idle is None or idle >= 0.80 or forced:
            if idle is not None and idle < 0.80:
                print(f"WARNING: host CPU only {idle * 100:.0f}% idle; latency "
                      f"numbers may be unreliable (BENCH_FORCE set, continuing).\n")
            return
        raise SystemExit(
            f"Refusing to benchmark: host CPU is only {idle * 100:.0f}% idle "
            f"(<80%).\nLatency here is CPU/contention-sensitive; measure on an "
            f"idle host.\nSet BENCH_FORCE=1 to override.")
    if load1 <= 2.0 or forced:
        if load1 > 2.0:
            print(f"WARNING: host load {load1:.1f} is high; latency numbers may be "
                  f"unreliable (BENCH_FORCE set, continuing).\n")
        return
    raise SystemExit(
        f"Refusing to benchmark: host 1-min load average is {load1:.1f} (>2.0).\n"
        f"Latency here is CPU/contention-sensitive; measure on an idle host.\n"
        f"Set BENCH_FORCE=1 to override.")


def dim_sweep(client):
    """Is 256-dim Matryoshka truncation the right operating point?

    Embed the corpus ONCE at the full 768 dims, then truncate+renormalize in
    numpy per candidate dim — mathematically identical to setting
    EMBEDDING_TRUNCATE_DIM, without re-embedding. Reports accuracy plus the
    mean top1-vs-top2 similarity margin (how decisively the right document
    wins; degrades before accuracy does on a small query set)."""
    import src.embeddings as _emb
    saved = _emb._TRUNCATE_DIM
    _emb._TRUNCATE_DIM = 0
    try:
        docs = [d for _, d in CORPUS]
        doc_full = np.asarray(client.encode(docs, is_query=False), dtype="float32")
        q_full = np.asarray(client.encode([q for _, q in QUERIES], is_query=True),
                            dtype="float32")
    finally:
        _emb._TRUNCATE_DIM = saved
    labels = [t for t, _ in CORPUS]
    print("\n  Matryoshka dim sweep (same 768-dim embeddings, truncated + renormalized):")
    for dim in (64, 128, 192, 256, 384, 512, 768):
        def cut(m):
            v = m[:, :dim]
            n = np.linalg.norm(v, axis=1, keepdims=True)
            return v / np.where(n == 0, 1, n)
        dv, qv = cut(doc_full), cut(q_full)
        correct = correct3 = 0
        margins = []
        for i, (topic, _q) in enumerate(QUERIES):
            sims = dv @ qv[i]
            order = np.argsort(-sims)
            if labels[order[0]] == topic:
                correct += 1
            if any(labels[j] == topic for j in order[:3]):
                correct3 += 1
            margins.append(float(sims[order[0]] - sims[order[1]]))
        print(f"    {dim:4d}-dim  top-1 {correct / len(QUERIES):.3f}  "
              f"top-3 {correct3 / len(QUERIES):.3f}  "
              f"mean top1-top2 margin {np.mean(margins):.4f}")


def main():
    _guard_idle_host()
    print("Embedding backend comparison (retrieval accuracy + per-item latency)\n")
    results = {}
    # Force local backends (no HTTP endpoint) for a clean comparison.
    os.environ.pop("EMBEDDING_URL", None)
    from src.embeddings import LlamaCppEmbedClient
    try:
        from src.embeddings import FastEmbedClient
        fe = FastEmbedClient(); fe.get_sentence_embedding_dimension()
        results["fastembed"] = evaluate(fe, "fastembed INT8")
        evaluate_hard(fe, "fastembed INT8")
    except Exception as e:
        print(f"  fastembed: not available ({type(e).__name__}) — skipping")
    # The model this stack replaced, at its NATIVE 384 dims: MiniLM is not
    # Matryoshka-trained, so letting the module's 256-dim truncation chop it
    # would sandbag the baseline and fake the comparison.
    try:
        from src.embeddings import FastEmbedClient
        import src.embeddings as _emb
        mini = FastEmbedClient(model="sentence-transformers/all-MiniLM-L6-v2")
        saved = _emb._TRUNCATE_DIM
        _emb._TRUNCATE_DIM = 0
        try:
            mini.get_sentence_embedding_dimension()  # probe at native dims too
            results["minilm"] = evaluate(mini, "all-MiniLM (old)")
            evaluate_hard(mini, "all-MiniLM (old)")
        finally:
            _emb._TRUNCATE_DIM = saved
    except Exception as e:
        print(f"  all-MiniLM: not available ({type(e).__name__}) — skipping")
    lc = LlamaCppEmbedClient(); lc.get_sentence_embedding_dimension()
    results["llamacpp"] = evaluate(lc, "llama.cpp Q8_0")
    evaluate_hard(lc, "llama.cpp Q8_0")

    if "fastembed" in results and "llamacpp" in results:
        fe_top1 = results["fastembed"][1]
        lc_top1 = results["llamacpp"][1]
        agree = sum(1 for a, b in zip(fe_top1, lc_top1) if a == b)
        print(f"\n  cross-backend top-1 agreement: {agree}/{len(QUERIES)} "
              f"queries retrieve the same document")
    print("\nInterpretation: equal accuracy across nomic backends = retrieval is "
          "backend/quant-independent; the all-MiniLM row is the replaced model "
          "at native dims, i.e. the before/after comparison.")
    if os.environ.get("BENCH_DIM_SWEEP") == "1":
        dim_sweep(lc)


if __name__ == "__main__":
    main()
