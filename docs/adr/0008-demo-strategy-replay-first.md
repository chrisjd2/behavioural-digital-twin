# ADR-0008: Demo strategy — replay first, interview as a bonus

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Chris Davies
- **Related:** ADR-0001

## Context

The app is shown in a 10-minute panel presentation. A full test run (300 users × 5 arms; 200 before the ADR-0001 power check) takes 10+ minutes and depends on network and API availability. Venue Wi-Fi and rate-limit blips are the usual demo killers.

## Decision

- **Simulation is always shown as a replay** of the frozen run, at sped-up playback (~2 minutes), stated openly ("this is the recorded run, sped up").
- **Interview** (Step 5) is **not** in the scripted 10 minutes. It is a Q&A bonus or a quick drop-in if time allows. It runs live, with **2–3 pre-recorded exchanges** stored in the run file and shown, labelled "recorded", if the live call fails.
- **Step 0 hook:** title question → two headlines with no context → panel votes → toggle "Show what this reader clicked before" (~6 past clicks) → vote again → reveal, optionally with arm A and D predictions. Example chosen from the **dev set**, where the typical-reader pick is wrong and the history points the right way; labelled **illustrative**, not evidence. ~90 seconds.
- **Fully offline-capable frontend:** fonts and scripts bundled; no CDN.
- The live run path (SSE) is still built, for development and for reviewers.

## Consequences

**Becomes easier:**
- A dead network costs only the live interview.

**Becomes harder:**
- Recorded interview exchanges must be prepared before the panel.

## Alternatives considered

- **Live simulation at small N:** shows a different, noisier result than the reported one.
- **Interview in the scripted talk:** unscripted, network-dependent, and not budgeted in the 10 minutes.
