# Episode 2 — first cut v1

**Render in progress · 26 November 2026 · 7 provisional shot selections; running revisions queued; bus-action takes being revised.**

**Next revision:** scenes03 and10 are queued; the short bus approach in04 is being updated too. All use an original rig cycle informed by sampled [PS2 running footage](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=248s): flared bent elbows, stronger heel recovery and forward lean. The current checkpoint preserves the version being reviewed. [Reference and retarget notes](guides/sa-gait-reference.json).

[**Watch review checkpoint 01 — full 47-second timeline with SFX**](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/review-checkpoint-01.mp4)

This checkpoint combines **22 seconds of selected animation** (01–04, 06, 08) with **25 seconds of clearly labelled storyboard holds** (05, 07, 09–12). It is ready for initial comments while rendering continues. Use the video timestamps when reviewing.

[Newer driver-interaction take — scene05, silent, rough motion](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/05-02/raw_00001_.mp4)

The driver window and white panel now remain fixed. The pull-out and climb still look floaty and need contact-animation polish. This newer take is not in checkpoint01.

The run around the bus now reaches the driver side. The chase has no outside runner; a fixed crop keeps the pursuit car offscreen. The exit still has a small initial body dip and a rounder handbag silhouette to polish.

[Play the animated opening with SFX — scenes 01–03](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/opening-pass.mp4)

[Chase motion preview with SFX — scene 06](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/chase-pass.mp4)

[Exit motion take — scene 08, silent](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/08-02/raw_00001_.mp4)

These are first-pass motion previews. The exit preserves the doorway and climb,
with a small initial body dip and a rounder handbag shape noted for polish.
The rest of the animated cut is still rendering. The first approach take incorrectly
boarded the passenger door; the first driver take enlarged the window into a door.
The initial chase also added an outside runner, and the recovery shot invented an
upright bus at the frame edge. These takes are rejected. Replacement takes use repaired Blender camera/contact paths
and finished-look anchors that preserve the small window and solid body panel.
Blender proxies supply motion and layout only; they do not define final mesh shapes.

[Play the timing animatic with SFX](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/timing-animatic.mp4)

This preview is a **static-board timing animatic**, not the animated H3 cut.
Remaining shots and targeted replacements are queued locally. Original takes and
rejection reasons remain in the take folders; no failed take is silently selected.

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
