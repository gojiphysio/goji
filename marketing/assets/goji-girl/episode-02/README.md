# Goji Girl · Episode 02 — TAP OUT

**Creative draft v6 · 25 November 2026 · proposed 47 seconds · vertical 9:16**

A frustrating work call sends Goji Girl rushing to Pilates. She steals a bus,
crashes outside Lentor Modern, remembers to tap out, and reaches the calm of
Goji while the police get stuck running against the glass.

## Storyboard from the top

The bus is now a **three-axle double-decker**, with two passenger decks and two
rows of glazing. It retains the supplied photo’s orange-red, deep-purple and
white livery, SOS Transit branding, smaller forward driver window and charcoal
door trim without a yellow outline.

**Panels 04–09 are direct Blender geometry blockouts**, with proxy people and
simplified buildings. The other panels are appearance concepts. Final PS2
finishing and continuous action animation remain production work.

### 01–04 · The call, the exit, the bus

![Storyboard 01–04](revision-06/frames/01-04-storyboard.png)

### 05–08 · Takeover, chase, crash, tap

![Storyboard 05–08](revision-06/frames/05-08-storyboard.png)

### 09–12 · Dust off, sprint, safehouse, Pilates

![Storyboard 09–12](revision-06/frames/09-12-storyboard.png)

[01–04 full size](revision-06/frames/01-04-storyboard.png) ·
[05–08 full size](revision-06/frames/05-08-storyboard.png) ·
[09–12 full size](revision-06/frames/09-12-storyboard.png)

## Double-decker continuity

One shared chassis supplies all six bus-action views. Shots 04/05 retain the
same parked pose in the left lane. Shots 07/08/09 retain exactly the same wreck
pose and heading, with the driver’s side down and passenger doorway facing up.
The reader remains inside that lower-deck doorway. The upper deck and rear
axle pair were added to that asset; the bus was not mirrored between cameras.

![Double-decker livery and geometry](revision-06/frames/bus-double-decker.png)

[Editable Blender master](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-girl-episode-2/marketing/assets/goji-girl/episode-02/revision-06/blender/double-decker-master.blend) ·
[Scene records](revision-06/blender/continuity-record.json) ·
[Revision notes](revision-06/README.md)

## Safehouse popup

> You can save your game and lose the police at a safehouse.

Exact user-provided copy, retaining the lower y=360 placement and 41.5–46.0s
interval. The clinic concept now uses the double-decker wreck reference while
preserving the engaged therapist, interior and two officers against the glass.

[Full clinic panel](revision-06/frames/12-safehouse-preview.png) ·
[Editable popup](revision-06/overlays/safehouse-popup.svg) ·
[UI reserve check](revision-06/frames/12-ui-clearance-check.png)

## Camera and look

**On foot:** the camera follows Goji Girl from behind at an ordinary gameplay
height. Keep her full body in the lower middle of the frame, her back toward
us and the route ahead readable. Small interaction-driven yaw is allowed;
low hero angles, face inserts and sweeping orbits are removed outdoors.

**Driving:** camera control transfers to the bus. Its rear grille and taillights
face us; the road ahead remains visible above it. Follow position and heading
with a little lag. The bus can yaw, lean and roll independently of the camera;
the horizon stays level. Scale follow distance to the bus rather than copying
the skill's sedan distances literally. These are framing proposals, not measured
PS2 camera constants.

**Indoors:** simple, deliberately staged San Andreas cutscenes. Medium shots,
fixed cameras, readable gestures. The clinic's quiet comes from pacing and sound,
while its people and materials remain in the same PS2 game as the street.

**Original PS2 target:** painted low-resolution surfaces, economical faces and
hair meshes, simple joint deformation, broad diffuse lighting, restrained
highlights, textured foliage and moderate distance haze. Every commuter, driver,
police officer and video-call participant follows the same standard. Avoid
modern glossy materials, photographic NPCs, toy-like faces and bare faceted
geometry. The cyan sky and warm concrete follow the selected daylight reference;
a heavy orange filter is not the definition of the look.

## Timed script

### 01 · 00:00–00:03 — Just one more thing

**Home cutscene.** Over her shoulder: headset with a visible boom microphone,
laptop full of meeting tiles. Her finger taps the desk. Her phone lights up:
**“Goji Pilates · Starts in 5 min.”** A colleague drones, **“Just one more thing…”**
She looks from the reminder to the call. The black handbag sits beside the desk.

Sound: flat laptop voice, notification ping, impatient finger tapping. Keep the
meeting faces as simple game characters too.

### 02 · 00:03–00:05 — Tap out of the call

**Home cutscene.** Medium view: she angrily rips off the headset, then slams
the laptop shut. The colleague is cut off mid-word. A tiny hold on the closed
lid. She takes the handbag in her left hand on the exit transition.

Sound: headset clatter, sharp **CLACK**, silence. This is her obvious burst of
anger; the rest is played with absurdly routine confidence.

### 03 · 00:05–00:08 — Player control resumes

**PLAYER follow.** Cut behind her, at normal gameplay height. She shoves the
front door open with her right hand, swaggers through, then accelerates toward
the street. Full-body player stays below centre; we see where she is going.
The camera follows through the doorway without dropping to shoe height.

Sound: door **BANG**, two heavy swagger steps, running feet. Brief objective:
**“Get to Goji.”** Bag stays in her left hand.

### 04 · 00:08–00:11 — Public transport, technically

**Same PLAYER follow.** She reaches a busy Singapore bus stop. A white/purple
**SOS Transit** double-decker bus with the familiar italic red/purple logo and a red roof band has its left passenger doors open and
commuters alighting. She runs around the nose toward the right-hand driver's
cab. The camera follows her route around the nose; the bus remains stationary
and parallel to the same curb through shot 05. Finish 04 at the nose with both
the front windscreen and her crossing direction readable before the view changes.

Sound: idle engine, air hiss, chatter. Show the last passenger step clear before
the takeover. The bus looks busy on arrival, but nobody remains aboard for the
crash. Keep traffic on the left and the driver's seat on the right.

### 05 · 00:11–00:15 — One star, zero hesitation

**PLAYER interaction view.** The camera settles modestly behind her right
shoulder at full-body distance, with both people readable. She hooks the bag
over her left forearm, smashes the driver's window, pulls the driver out,
lets him clear the cab, then climbs into the seat. He lands upright, alive
and indignant. Keep the separate removal, clearance and entry states.

The bus remains in the same left lane and the same parked transform as04.
The player is now on its road-centre/driver side; the shelter and bin remain
beyond the opposite passenger side. Camera screen positions follow the Blender
view rather than a mirrored image.

Sound: **CRASH**, surprised yelp, wanted sting. **One star lights up.** She places
the bag in the cab footwell as she gets in. Transfer to the vehicle camera only
once she is seated. This gets four seconds, borrowing one from the chase;
final contact timing still needs an animatic.

### 06 · 00:15–00:20 — The least relaxing commute

**BUS rear chase, one sustained view.** The bus accelerates away from us,
threads between traffic, then swerves toward the junction. The rear stays our
anchor while road markings, traffic and buildings pass around it. Suspension
reacts to steering; the chassis remains rigid. No front-quarter beauty shot,
cab insert or roadside tracking cut.

Sound: diesel, horn, tyre squeal and rattling fittings. Police remain behind
the camera, out of sight. Broad blue/red spill sweeps unevenly over the road, railing and bus body.
The sources belong to the unseen chasing cars, behind and offset from the camera,
with staggered pulses and different falloff. No paired glowing points, blue bus
lamps or symmetric red/blue patches. Normal bus tail lamps remain red/amber.
Sirens tell us the pursuit is getting closer. Keep the single star.

### 07 · 00:20–00:25 — Arrival is a strong word

**Continue the BUS chase camera.** Lentor Modern and an empty shelter appear
ahead. The bus takes a left turn too sharply, rolls onto its right/driver's
side and slides into the shelter. The camera follows its travelling centre
with heading lag, so its side can come into view as it slides. The camera itself
does not roll, orbit to the front or cut to an impact close-up.

Sound: squeal → scrape → enormous **CRUNCH**. Sparks start at road contact.
Keep the bus recognisable and the left passenger side upward. No explosion
covers the recovery. The shelter is empty. The storyboard shows the final sliding/settled pose:
right side down, passenger side upward, roof toward the road centre, wheels
toward the mall-side curb. From this rear view, the mall/canopy is screen left. The front bumper
stops at the damaged post. Freeze that chassis transform at the end of 07.

### 08 · 00:25–00:31 — Still must tap out

**Recovery camera transfers back to PLAYER.** First hold on the settled wreck
for one full second, preserving the exact end-of-07 bus transform, curb,
bent post and bin. A little piece of shelter drops. Use a deliberate recovery
camera cut from the rear vehicle view to the front passenger doorway, with the
same wreck still at rest; never rotate or relocate the bus to fit the new view.
The mall is now screen right in the front recovery view. The bus still points
in exactly the same world direction; the camera changes, not its heading. Then the camera settles
behind her as she climbs up through the upward-facing front passenger doorway.
A modest rise/offset keeps her and the reader visible, as an interaction camera
avoiding obstruction would; it does not become an aerial shot.

Halfway out, she remembers. She reaches back down and taps her EZ-Link card
on the reader attached just inside the doorway. Green light. **BEEP.** She
finishes climbing onto the upward-facing side panel, bringing the bag from the cab
with her. The geometry blockout allocates one second to the pause and five to the
rise, tap and climb clear; the pavement drop follows in shot 09. No hand insert,
face close-up or caption explains the joke: the reach, green flash and isolated
beep do the work at gameplay distance.

Keep the reader and its pole rotated with the bus. The opening faces upward;
it is not an upright door on the bus's rear. Protect the silence around the beep.

### 09 · 00:31–00:33 — Nothing to see here

**PLAYER follow, behind her.** She drops to the pavement, dusts her shoulders,
settles the handbag back into her left hand and sets off. Her back stays toward
us; no front-facing reaction shot. The wreck smokes off to one side and the
mall route is ahead. Sound: two brushing sounds, then returning sirens.

### 10 · 00:33–00:37 — Same appointment, new entourage

**PLAYER sprint.** Follow her toward the mall and Goji shopfront. Two officers
catch up from behind, their bodies only partly entering the lower frame edges.
She remains the centred, readable player; the camera never changes allegiance
to the pursuers. An intentional route-compression cut is allowed if needed,
but match rear view, gait and screen direction across it.

Sound: her feet, two heavier sets, radio chatter, one **“Oi!”** Keep one star.
If an entrance marker is used, retain episode one's established marker design.

### 11 · 00:37–00:39 — Safe zone

**Clinic cutscene begins at the threshold.** Cut to the fixed interior camera
as she enters. Her posture relaxes instantly. The officers stop outside;
the star and other gameplay HUD disappear. All sirens, shouting and running
sound cut dead on the threshold. Quiet room tone and a soft arrival chime.

Preserve the reference reception: warm timber, red/cream floor, deep-red table,
short-bobbed therapist in black. The officers' feet remain on exterior pavement.
The therapist greets her without acknowledging the pursuit.

### 12 · 00:39–00:47 — And… breathe out

**Fixed clinic cutscene.** Elliptical cut to her on the reformer, doing one slow
footwork repetition in grip socks. White shoes and the single handbag sit on
a bench. Therapist in a black crew-neck top and leggings, white shoes, small
left-chest mark only; plain black back, no name tag. She leans toward the footbar,
watches the near knee and cues alignment with one open hand while her other hand
demonstrates the extension direction. She follows the repetition attentively;
there is no passive hands-clasped pose.

Instructor: **“And… breathe out.”** Quiet breath and reformer mechanism.

Hold the same medium-wide composition for the whole eight seconds. Her movement
draws the eye first; the background is already there to discover, without a
cinematic pullback. Through the clear glass, two police face inward and run
against it—alternating knees, pumping arms, no forward progress, slightly out
of phase. Beyond them, the overturned bus burns. Nobody inside reacts.

At **41.5s**, show the tutorial box at y=360. Hold until **46s**:

> You can save your game and lose the police at a safehouse.

This is original San Andreas-style parody copy, not a verbatim game quote.
The joke stays entirely in the fictional game; no appointment or treatment claim.

Small final-two-second copy: **“Pilates at Goji · Lentor Modern.”** Keep it clear
of the background gag. End on the moving tableau.

## Continuity and review notes

- **Approved direction:** the user accepted the story intent and requested
  predominantly third-person outdoor gameplay with indoor cutscenes. The new
  illustrations, exact camera offsets and 47-second timing remain proposals.
- **Retain the comedy:** crash pause, isolated tap beep, hard audio boundary,
  slow reformer action and police with broken pathing. No blood or deaths;
  driver is visibly okay, passengers clear the bus, shelter is empty.
- **Prop ownership:** desk → left hand → left forearm during takeover → cab
  footwell → recovered during exit → left hand → bench in the Pilates cut.
  Do not silently change hands, add a shoulder strap or duplicate the bag.
- **Geography:** this is a fictional compressed Lentor Modern game set, allowing
  the bus to be visible through the clinic glass. The boards are not a surveyed
  route, verified transit service or faithful reconstruction of every frontage.
- **Geometry review:** the Blender asset fixes the previous rear-door/roof-hatch
  ambiguity. The reader and pole retain their chassis-local coordinates; the
  card meets the front-door reader. Constant-length limb solves and wheel/ground
  clearance are checked. The six-second blockout uses a procedural proxy and
  neutral surroundings, not approved final cast or a full accident simulation.
  Contact frames were inspected; the final PS2 motion and exit-to-ground cut still
  need production review. The earlier generated bus panels are superseded. The revision-06 `.blend`
  and its direct views are the geometry authority; the old revision-03 isolated
  exit motion remains a contact study, not the current street layout.
- **Service framing:** Pilates/studio experience, no medical or treatment claim.
  Her unhurt state is cartoon continuity, not recovery attributed to a session.
- **Future motion handoff:** the new skill's Blender staging and H3 continuous
  video guidance apply to these complex outdoor actions; simpler fixed-camera
  scenes can use H3 still guides. This revision updates the shared double-decker and all twelve storyboard panels, without launching
  a new H3 benchmark or rendering the full episode.

## References used

Applied the new [Goji GTA video skill](https://github.com/gojiphysio/goji/blob/a4cb40ee89d6baa9ca027785fca71abe56b65cb8/marketing/video-production/skills/goji-gta-video/SKILL.md),
[series bible](https://github.com/gojiphysio/goji/blob/a4cb40ee89d6baa9ca027785fca71abe56b65cb8/marketing/video-production/skills/goji-gta-video/references/series-bible.md)
and [San Andreas reference pack](https://github.com/gojiphysio/goji/blob/a4cb40ee89d6baa9ca027785fca71abe56b65cb8/marketing/video-production/skills/goji-gta-video/references/san-andreas-reference.md).

- **Identity/style:** the skill's recovered `ep01-street.png` (Episode 1 v6),
  plus `ep01-reception.png` for therapist identity, wardrobe and reception layout.
  The smoother reception rendering is simplified toward the street/PS2 standard.
- **Game-camera/look:** inspected cached samples from
  [Paulo Cassiano's reported original-hardware PS2 capture](https://www.youtube.com/watch?v=Z9cD9uj1fb8&t=240s),
  including the rear player view near 04:04 and rear driving view near 04:46.
  Also inspected the reference pack's takeover and turn contact sheets. These
  were still-frame inspections, not new normal-speed playback or measured physics.
  Source capture processing and cheats remain unverified, as recorded in the pack.
- **Generation:** built-in image generator, with identity and game-camera
  references assigned separate roles. Exact prompts, edits and reference hashes
  are in [v2 generation records](storyboard-prompts-v2.json).
- **Current shot states:** [camera and continuity record](camera-plan-v6.json).
- **This revision:** [double-decker geometry and full storyboard](revision-06/README.md).
- **Retained staging:** [source photos and Blender records](revision-03/README.md).
- **Earlier drafts:** [v1](creative-v1.md), [v2](creative-v2.md) and [v3](creative-v3.md) and [v4](creative-v4.md) and [v5](creative-v5.md), retained for comparison.

## Optional caption

> She took public transport. Technically.
>
> Goji Girl, Episode 02: TAP OUT.

Any later customer CTA must use a verified `go.gojiphysio.com/<slug>` redirect.
No Instagram publication or main-branch merge is included in this revision.
