# Episode 2 — first cut v1

**Render in progress · 26 November 2026 · 11 provisional selections covering 39 seconds.**

[**Watch review checkpoint 02 — 47 seconds with SFX**](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/deliverables/review-checkpoint-02.mp4)

This checkpoint has **35 seconds of animation and 12 seconds of labelled storyboard holds**. Scene12 is still rendering; newer recovery and arrival takes are linked below. Checkpoint01 remains unchanged for earlier comments.

**Running revision:** the departure, bus approach and clinic sprint now use an original rig cycle informed by sampled [PS2 running footage](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=248s): bent elbows, firmer arm pumping, stronger heel recovery and forward lean. The bag stays in her left hand. H3 still softens the poses; this is a closer approximation, not the exact game animation. [Reference and retarget notes](guides/sa-gait-reference.json).

[Departure run — scene03](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/03-02/raw_00001_.mp4) · [Run around the bus — scene04](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/04-04/raw_00001_.mp4) · [Clinic sprint — scene10](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/10-02/raw_00001_.mp4)

The clinic sprint keeps the wreck behind camera and both officers following. A foreground officer briefly obscures her near the turn; that framing needs polish. Samples show no impact with the passing pedestrian.

Normal-speed playback checks for the latest revisions are pending because the Mac has locked. The new shots were reviewed with full-route samples and denser 8fps stride/contact samples; the assembled MP4 passes a strict full-decode check.

[New recovery take — scene09](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/09-02/raw_00001_.mp4) · [New clinic arrival — scene11](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/11-01/raw_00001_.mp4)

These two takes are newer than checkpoint02. The recovery keeps the wreck on its side at the edge and continues forward. The arrival settles into calm with an attentive therapist and both officers outside. The bag appears in the near/right hand at reception, a small continuity issue for polish.

[Newer driver-interaction take — scene05, silent, rough motion](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/05-02/raw_00001_.mp4)

The driver window and white panel now remain fixed. The pull-out and climb still look floaty and need contact-animation polish. This take is included in checkpoint02.

[Newer crash take — scene07, silent, rough impact](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/first-cut-v1/takes/07-02/raw_00001_.mp4)

The bus rolls onto the correct side and pedestrians stay clear. The sharp turn and shelter impact need stronger motion/contact. This take is included in checkpoint02.

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
