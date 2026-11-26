# Episode 2: motion revision

This pass is in production. The previous cut remains available in [first-cut-v1](../first-cut-v1/README.md).

The revision covers the running scenes, bus chase, rollover, exit and the dust-off transition. Both arms pump through the full running cycle, with the handbag attached as a rigid prop. Its long side runs alongside her body; it follows her grip instead of presenting its broad face to the camera. The bus carries speed through a sharp turn, a roll onto its side and a slide into the mall-side canopy. Goji Girl climbs through the passenger doorway with visible hand and foot support, taps the reader while braced, then climbs down and lands on the pavement.

The exit gets eight seconds, bringing the planned cut to 49 seconds. The safehouse message stays exactly as approved: “You can save your game, improve your stats, and lose the police at a safehouse.”

[Watch the new chase and crash motion test with SFX](deliverables/chase-crash-motion-test.mp4). This ten-second test is provisional and has been reviewed in frame samples. The impact still has some livery drift; the full revision is rendering. The [earlier chase-only test](deliverables/chase-motion-test.mp4) remains unchanged.

## Bag orientation correction

The revised references turn the bag alongside her body, with its narrow end visible from behind. The grip transform has the same correction in the running and exit guides. The new animation test is queued; this correction is not yet verified in finished motion.

| Previous reference | Revised reference |
| --- | --- |
| ![Previous broad bag face](inputs/03-full-left-pump.png) | ![Revised narrow bag end](inputs/03-grip-side-on.png) |

## New appearance references

These are still references for rendering, not proof that the animation passes review.

| Full arm pump | Braced exit |
| --- | --- |
| ![Running pose](inputs/03-grip-side-on.png) | ![Braced passenger-door exit](inputs/08-contact-look.png) |

![Mall-side impact](inputs/07-impact-end.png)

## Motion and continuity

[Geometry check record](guides/motion-audit.json) · [Render status](render-status.json) · [Selected takes](selected.json) · [Render prompts](revision-jobs.json)

The Blender guide covers 110 metres in five seconds for the chase. The crash separates steering, weight transfer, ground contact, sliding and impact. The exit checks limb reach and carries the same wreck transform into the next shot. These are original staging choices, not measurements of GTA or a real bus. Generated footage needs its own contact and continuity review.

The retained scenes are 01, 02, 05, 11 and 12. Scene 05's earlier driver-window contact roughness remains documented in the previous cut. No wanted stars or other gameplay HUD are baked into the new footage.
