# Episode 2 — first cut v1

**Render in progress · 26 November 2026 · 4 shots held for the edit; 2 interaction takes being revised.**

[Play the animated opening with SFX — scenes 01–03](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/opening-pass.mp4)

[Exit motion take — scene 08, silent](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/08-02/raw_00001_.mp4)

These are first-pass motion previews. The exit preserves the doorway and climb,
with a small initial body dip and a rounder handbag shape noted for polish.
The rest of the animated cut is still rendering. The first approach take incorrectly
boarded the passenger door; the first driver take enlarged the window into a door.
Both are rejected. Replacement takes use repaired Blender camera/contact paths
and finished-look anchors that preserve the small window and solid body panel.
Blender proxies supply motion and layout only; they do not define final mesh shapes.

[Play the timing animatic with SFX](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/timing-animatic.mp4)

This preview is a **static-board timing animatic**, not the animated H3 cut.
The twelve H3 shots are queued locally; the exit continuity take renders first.

This cut uses the approved v8 boards and the same Blender street, vehicle and
crowd layout. H3 Ref2VA handles the moving shots locally, with continuous Blender
guidance for outdoor interactions and still guidance for simpler scenes.

The safehouse message is now:

> You can save your game, improve your stats, and lose the police at a safehouse.

The editable overlay retains its y=360 placement and original box/type treatment.
Wanted stars and other gameplay HUD remain out of the picture for post-production.

Audio is an original SFX-only stereo mix, with separate foley, vehicle, UI and
clinic stems. It includes the calendar ping, crash pause, isolated card-reader
beep, chase and abrupt calm at the clinic threshold. No music or synthetic dialogue.

[Shot prompts and guidance choices](shots.json) ·
[Sound cues](audio/cues.json) · [Safehouse overlay](overlays/safehouse-popup.svg)

The first exit take hit a missing-model setup error: the two pinned H3 weights had
been deliberately evicted after the workflow benchmark. They have been restored and verified
against the recorded revisions and SHA-256 hashes; no paid API is used.

Do not treat queued or successfully encoded takes as reviewed footage. Selection,
actual frame ranges and known defects will be recorded after visual review.
