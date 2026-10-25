# ADR-0012: Talk structure — a presenter deck over the existing steps

- **Status:** Accepted
- **Date:** 2026-10-24
- **Deciders:** Chris Davies
- **Related:** ADR-0008 (amended), ADR-0010, ADR-0011

## Context

The panel format changed from ADR-0008's 10-minute in-room talk. It is now **15 minutes over a video call** (screen share). **Part 1, About me** (5 minutes) introduces Chris. **Part 2, Learn · Tinker · Teach** (10 minutes) is the task: pick a new idea, explore it, build something, explain it. The panel scores the learning process, handling changing requirements, and engaging the audience and checking understanding. The app was a free six-step stepper with no story around it.

## Decision

- **Presenter mode is the app's default view.** It is a deck that moves through one running order of new slides and existing steps. The free stepper stays, unchanged, behind an "Explore" link, for reviewers and the hosted demo.
- **Running order** (★ new slide):

    | #   | Screen                                                                                                | Section  |
    | --- | ----------------------------------------------------------------------------------------------------- | -------- |
    | 1–3 | ★ About me (title only), Career (the roles, all at once), Learn · Tinker · Teach in my life           | About me |
    | 4–7 | ★ The brief, Back to MiroFish, Research path, The gap and my angle                                    | Learn    |
    | 8   | ★ What I built (incl. "Who did what": the honest AI-use statement)                                    | Tinker   |
    | 9   | Population                                                                                            | Tinker   |
    | 10  | Hook                                                                                                  | Teach    |
    | 11  | Simulation replay                                                                                     | Teach    |
    | 12  | Report                                                                                                | Teach    |
    | 13  | ★ Check-in question (calibration)                                                                     | Teach    |
    | 14  | ★ Takeaways                                                                                           | Teach    |
    | 15  | ★ Thanks / questions (Interview as a Q&A bonus)                                                       | Teach    |

- **About me is mostly said, not shown** (#66). Chris is on camera, so the deck opens on a plain "About me" title, with no name, photo or "Who I am" list; Chris says who they are over it. No hand-off slide: Chris says the "learn, tinker, teach" line on the way into Learn.

- **Teach is woven in.** The Hook moves from the opening into Teach: Learn's MiroFish question opens Part 2 instead.
- **Audience interaction is verbal.** The Hook vote and the check-in question have no on-screen tally or phone voting.
- **Seed is out of the talk.** Screen 8 explains the arms. The Interview is a Q&A bonus (screen 15), as in ADR-0008.
- **Navigation:**
    - Right/left arrows and PageDown/PageUp (presentation clickers) move between screens.
    - A screen with its own stages (the Hook, click-to-reveal slides, the Report's pages) takes the key first, and the deck moves only when nothing on screen used it.
    - Keys are ignored while typing.
- **The deck shows one run:** the default run (`defaultRunId`), with no run picker or live-run controls.
- **Personal media is never committed:**
    - Photos and screenshots live in `frontend/public/private/`, which is gitignored and dockerignored (ADR-0010).
    - Each media slot shows a placeholder when its file is missing.
- **About me is hidden in `DEMO_MODE`.** The hosted demo (ADR-0011) starts at Learn. (Built in #53.)
- **No speaker notes in the app.**

## Consequences

**Becomes easier:**

- One URL and one keyboard flow for the whole talk.
- The existing steps are reused, not rebuilt as slides.

**Becomes harder:**

- Screens must fit a 1920×1080 shared screen. The deck is laid out on a fixed 1920×1080 canvas and zoomed to fit the window (#64), so no window size or display scaling makes a screen scroll; deck styles use `cqw`/`cqh`, not `vw`/`vh`.
- Slide copy lives in code and must be reviewed by Chris before the panel.

## Alternatives considered

- **A separate slide deck around the app:** switching windows mid-talk, and the screens can't share the run's data.
- **Phone voting via QR code:** needs network and a live backend for about 20 seconds of value.
- **Speaker notes in a synced second window:** more to build than notes on paper.
