# H3 Ref2VA prompt template

A worked example in MiniMax's six-section Ref2VA format, using the Episode 1 taxi
chase conversion job (`chase-benchmark/prompts.json`, key `conversion`). Inputs, in
node order: `ref_image_0` is the look frame (`<Picture 1>`), `ref_video_0` is the
124-frame Blender layout (`<Video 1>`). This is a format example. It has not been
rendered yet, so compare it against the original prose prompt before adopting it.

What changed from the original prompt:

- The "No realistic humans, no new vehicles, no spawning…" list is gone. Each
  ban is restated as what does exist.
- The Blender clip is limited to motion, layout and camera through
  `attribute_transfer`. Its placeholder surfaces are stated as replaced. In the
  Episode 2 tests this held for subjects with a reference image, not for
  text-only NPCs; render those as grey clay in the guide.
- Cast, vehicles, street and look are separate Subjects, so later shots and
  episodes can reuse the same lines word for word.
- The audio fields are filled in explicitly.

Copy the structure. Replace the Subjects with the episode's approved cast and
location lines from the [series bible](../references/series-bible.md), and keep
them identical across shots.

```text
subject_definitions:
<Subject 1> is the original 2004 PlayStation 2 game look of <Picture 1>: angular low-poly meshes, flat painted textures with visible texel detail, simple diffuse shading, warm hazy daylight and short draw distance.
<Subject 2> is the cobalt-blue Comfort taxi in <Picture 1>, with a white roof sign, yellow rear number plate and black rear bumper.
<Subject 3> is the adult woman driving <Subject 2>, seen through its rear window on the right-hand side, with a black ponytail and a maroon sleeveless top, built as an angular PS2 character mesh with painted skin.
<Subject 4> is the silver sedan and <Subject 5> is the white van from <Picture 1>, both rigid low-poly vehicles.
<Subject 6> is the Singapore road in <Picture 1>: three lanes of textured warm-grey asphalt, green roadside railings, leafy tropical trees, grey HDB blocks and a pale cyan sky.
<Video 1> is the Blender layout clip that defines the vehicle trajectories, relative positions, timing and rear-follow camera path; its grey placeholder surfaces carry no appearance.

summary:
[reference generation] One continuous five-second rear chase shot in the look of <Subject 1>. <Subject 2>, driven by <Subject 3>, passes <Subject 4> on its right, moves left to pass <Subject 5>, then returns to the middle lane on <Subject 6>, following the motion and camera structure of <Video 1>.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - every surface, vehicle and person is rendered in the painted PS2 style of <Picture 1>.
<Subject 2> (appears in [Shot 1]): fully_preserved - colour, roof sign, plate and bumper stay unchanged and the body stays rigid.
<Subject 3> (appears in [Shot 1]): fully_preserved - ponytail, maroon top and seating position stay unchanged.
<Subject 4> (appears in [Shot 1]): fully_preserved - silver finish and shape stay unchanged.
<Subject 5> (appears in [Shot 1]): fully_preserved - white finish and shape stay unchanged.
<Subject 6> (appears in [Shot 1]): fully_preserved - lane layout, railings, trees, blocks and sky stay unchanged.
<Video 1> (vehicle trajectories, timing and camera path): attribute_transfer - motion, spacing and camera follow are transferred to the styled vehicles while its placeholder surfaces are fully replaced by <Subject 1>.

detailed_description:
The target video is original 2004 PlayStation 2 open-world gameplay footage with angular low-poly geometry, flat painted textures, simple diffuse shading and warm hazy daylight, framed as vertical 9:16.
[Shot 1] A rear chase camera sits behind and slightly above <Subject 2>, the cobalt-blue Comfort taxi with a white roof sign, yellow rear plate and black bumper, in the left lane of <Subject 6>. Through the rear window, <Subject 3>, the woman with a black ponytail and maroon sleeveless top, sits in the right-hand driver's seat with both hands on the wheel. Ahead in the same left lane drives <Subject 4>, the silver sedan, and further ahead in the middle lane drives <Subject 5>, the white van. Following the timing and trajectories of <Video 1>, the taxi accelerates, moves right into the middle lane and overtakes the silver sedan on its right side, leaving the sedan behind in the left lane. Approaching the white van, the taxi steers back into the left lane, draws level with the van, passes it, and eases into the middle lane ahead of both vehicles. The sedan and van hold their own lanes at a steady speed and slip back down the road. All four wheels of every vehicle stay on the asphalt and each body stays rigid, with only a slight lean as the taxi changes lanes. The camera follows behind the taxi at a constant distance and height, panning left and right with small amplitude at slow speed to keep the taxi centred, with the horizon level throughout. White lane dashes stream toward the camera beneath the taxi, and each vehicle casts a soft, blocky shadow directly under its body from the high afternoon sun. Engine and tyre noise swell briefly as the taxi passes each vehicle. Green railings, palm and rain trees, and grey HDB blocks slide past on both sides in the same painted texture style as <Picture 1>, and the pale cyan sky stays unchanged. These three vehicles and the driver are the only moving things on the road, and every surface keeps the PS2 look of <Subject 1>.

overall_soundscape:
A steady petrol engine note rises as the taxi accelerates, with tyre hum on warm asphalt and the brief whoosh of each vehicle it passes. Distant city traffic ambience continues throughout.

non_diegetic_music:
N/A
```
