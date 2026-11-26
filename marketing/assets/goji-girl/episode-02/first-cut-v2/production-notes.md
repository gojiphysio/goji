# Motion revision record

## User direction

Both arms pump in the GTA SA running cycle. The handbag is a rigid object attached to the carrying hand. The bus weave must feel dangerous and fast. At Lentor, a sharp turn at speed causes the rollover and a slide into the mall side. The passenger-door exit must show climbing rather than vertical root motion. Blender proxies supply contacts, paths and camera geometry; approved cast and SOS-BUS-01 supply the finished shapes.

## Reference and provenance

- Appearance: the approved [SOS-BUS-01](../../references/sos-bus-01/README.md), existing Goji Girl references, and the existing photo-derived Lentor/Goji look frames.
- Motion observation: [Paulo Cassiano's PS2 San Andreas gameplay](https://www.youtube.com/watch?v=Z9cD9uj1fb8), approximately 248–249.5 seconds for running and 362–377 seconds for a fast vehicle collision/roll. The creator identifies this as the PS2 release. Hardware/mod provenance is not independently verified. Reference clips stay outside the repository and are not used as generation inputs.
- Gait and vehicle numbers in these scripts are original proposed choreography, not extracted animation or measured game physics.
- Rendering uses the existing local H3 Ref2VA Q4 / Turbo four-step route. No new paid video service is used.

## Spatial decisions

The neighbourhood pocket used by 03–05 has a local origin mapped to world Y minus 200 metres for the long chase. Its camera-relative geometry stays unchanged. Bus forward is +Y; driver side is +X; passenger side is -X. Northbound traffic stays at x < 0.

The bus exits 06 at Y=-66 and enters 07 at the same mark and speed. The crash ends at chassis X=-6.5, Y=0 with a 94-degree right roll. Ground height comes from transformed structural bounds and the kerb, rather than a fixed root height. The struck canopy bay buckles up; supports bend with the impact. The first approach tree moves out of the slide/camera corridor. Unharmed extras remain in the storefront pockets.

Scene 08 opens the saved end state of 07. Passenger frame and reader contacts are transformed from the same chassis coordinates. The actor braces, crosses the sill, taps, lowers over the chassis edge and drops to pavement. Scene 08 ends and 09 starts at (-7.35, 4.4, 0.13), facing forward. Scene 10 continues northward away from the wreck toward Goji. The wreck stays behind its camera.

## Review gates

- Reject restrained bag-arm motion even if the right arm looks good.
- Reject a slow roll or slide, missing ground strike, magical braking or a changed final bus heading.
- Reject an exit with no load-bearing contacts, feet through panels, a front-facade cutout, a new roof hatch or an ending still on top of the bus.
- Check finished forms against SOS-BUS-01; a textured blockout does not pass.
- Keep all raw attempts and record decisions in each take's run.json. A completed render is not an accepted take.

The first v2 run test, 03-01, is rejected because the bag arm still has reduced range. The next test changes the finished first-frame pose while retaining the same seed and full two-arm guide.

## Bag orientation and running follow-up

The user rejected the broad bag face pointing at the rear camera. The grip transform now turns the bag 90 degrees around its local vertical axis before applying the arm rotation. Its long side runs fore-aft beside her body. Updated look references carry the same direction. The exit uses the body/hand orientation rather than a world-fixed, camera-facing bag.

Run test 03-02 also fails: the first raised-arm pose decays into the old low carry. The next attempt adds alternating indexed pose anchors through the whole three-second stride sequence, alongside the continuous Blender guide. It stays on the same H3 model and seed.

The clinic chase camera moves closer and rotates through the turn. The officers follow continuous flanking arcs, keeping the player visible. The left runner stays clear of the tree. These changes still need generated-footage review.

The latest scene 10 guide has been inspected across the full route at 3fps. Both officers remain beside the camera edges and the player stays visible through the turn. The scene 07 render establishes the fast roll and slide but changes some side livery as it reaches the final anchor; it is a provisional rough-cut selection with that defect retained in the review record.

Run test 03-03 holds both arm extremes throughout the 8fps full-shot review and keeps the narrow bag end toward the rear camera. It is selected provisionally, pending normal-speed playback. Scenes 04 and 10 add this finished clip as Video 2 for locomotion only, retaining their own Video 1 route/camera and appearance frame.

The final revision selects seven new outdoor shots and retains 01, 02, 05, 11 and 12. Scene 09 uses a recorded gradual crop to counter generated camera pullback. The 49-second export uses half-open overlay intervals so the calendar does not spill onto the departure frame. Exact frame-index cut samples and the full-decode check are retained in deliverables. Normal-speed playback and audio audition remain blocked by the locked Mac.
