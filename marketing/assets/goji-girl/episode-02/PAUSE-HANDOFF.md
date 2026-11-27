# Episode 2 pause handoff

Paused at the user's request on **27 November 2026, Singapore time**. The user
authorized merging the current work. This preserves a creative review draft;
it is not approval of every generated detail or authorization to publish on Instagram.
Do not start more production until the user resumes it.

## Saved state

- Current deliverable: [49-second revised cut and review notes](first-cut-v2/README.md),
  with original SFX. The [previous 47-second cut](first-cut-v1/README.md) remains available.
- [Selected takes](first-cut-v2/selected.json), prompts, source hashes, rejected
  attempts, Blender scenes, sound stems and overlays are retained.
- Seven outdoor shots were replaced. Scenes 01, 02, 05, 11 and 12 were retained.
- The completed episode-specific renderer on port 8196 was stopped after its
  queue emptied. No production jobs were left running by this session.
- The full export passes strict decoding and source-range checks. Uploaded
  video, poster and review-page hashes were verified. Playback and audio audition
  remain pending because the Mac relocked.

## Lessons from this pass

1. **An opening pose does not lock a running cycle.** Tests 03-01 and 03-02
   returned to a restrained bag arm. Test 03-03 combined the continuous guide
   with alternating pose anchors every six frames at 24fps. Full-shot 8fps
   samples then showed both arms pumping. This is evidence for this take, not
   a guarantee for every H3 shot. The selected clip also helped scenes 04 and 10
   as a locomotion reference alongside their own route/camera guide.
2. **Bag orientation belongs to the hand grip.** The broad face points outward
   beside her body; the rear view mostly sees the narrow end. A profile camera
   can naturally see the broad face. Audit relative hand/bag rotation, offset
   and scale across the saved motion, then inspect generated frames separately.
   [Grip audit](first-cut-v2/guides/bag-grip-audit.json).
3. **Geometry and appearance need different references.** Blender establishes
   the route, camera, door, reader and contacts. SOS-BUS-01 supplies the formed
   vehicle shapes and livery. A correct blockout does not prevent H3 from copying
   primitive shapes or changing paint. The impact's livery drift remains evidence
   of that limit.
4. **Action needs cause, contacts and enough time.** Speed, steering load, roll,
   ground strike and sliding impact need distinct motion. The exit improved when
   staged as palms, knee, weight transfer, supported tap, descent and landing.
   Expanding it from six to eight seconds made room for the complete action.
5. **Sample within a stride and at exact cut frames.** Half-second samples can
   repeatedly show the same phase of a half-second gait. Exact frame-index cut
   samples avoid timestamp seeking selecting the next scene. Use half-open
   overlay intervals so the calendar does not leak onto the departure frame.
6. **Review the whole camera path.** Check rigid-prop clearance, foreground
   officers and the player through the turn. Scene 09 needed a recorded crop
   to counter generated camera pullback. That fixes framing, not 3D geometry.
7. **A successful render is not final acceptance.** Keep rejected takes and
   provisional selections distinct. File decoding, Blender audits and sampled
   frames each answer different questions; none replaces normal-speed playback
   or listening review. Local renders took many minutes per short shot, so test
   the difficult action before spending that time on related shots.

## Resume from here

Start with playback of the saved cut and the user's next comments, not a fresh
batch. The open polish items are the retained floaty driver takeover, impact
livery drift, the small/partly hidden card tap, reception bag-hand continuity,
and slight reformer foot/bar drift. The standing grip at the end of 04 matches
the retained 05 opening; the clasp is visible there.

Keep the current choices: original PS2/SA appearance, outdoor player camera,
SOS Transit double-decker, unhurt pedestrians, no baked wanted stars, uniform
calendar type size and the lowered safehouse popup. Its wording remains:

> You can save your game, improve your stats, and lose the police at a safehouse.

Before a future code or asset follow-up, check PR #265's merged state and start
a new feature branch from current `origin/main`. Do not push follow-ups to a
merged branch expecting them to reach main.
