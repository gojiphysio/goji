# Goji reel — revision 8

[**Watch or download the 30.8s cut**](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/goji-v8-ui-sfx.mp4) · [Silent version](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/goji-v8-ui-silent.mp4) · [Editing pack](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/goji-v8-editing-pack.zip)

1080 × 1920 · 30 fps · original game-style sound effects · no music. The GIF is a lightweight 8 fps preview; use the MP4 to judge motion.

![Mobile preview](preview.gif)

## Changes

- **Half a second more to exit:** the arrival now runs through v6 **00:12.500**, then cuts to the same running frame at v6 **00:16.000**. This restores 15 frames of motion at 30 fps.
- All other v7 footage, black Goji uniforms, handbag HUD and popup wording remain unchanged. Sound effects follow the revised cut; no music.

## Timing

| Time | Action |
|---|---|
| 0.0–4.3s | Extended walking swagger |
| 4.3–7.1s | Wrench open taxi door; driver falls out |
| 7.1–11.1s | Fast driving, trimmed before orientation glitch |
| 11.1–12.5s | Arrival, cut at original 00:12.5 |
| 12.5–14.9s | Running, resumed at original 00:16 |
| 14.9–16.9s | Yellow entrance cone |
| 16.9–17.3s | Loading transition |
| 17.3–19.8s | Seated Goji welcome |
| 19.8–24.8s | Assisted stretch + Mobility popup |
| 24.8–30.8s | Spotted squat + Body Muscle popup |

## Clips for editing

- [Extended walking swagger](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/01-swagger.mp4)
- [Wrench open taxi door; driver falls out](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/02-takeover.mp4)
- [Fast driving, trimmed before orientation glitch](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/03-drive.mp4)
- [Arrival, cut at original 00:12.5](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/04-arrival.mp4)
- [Running, resumed at original 00:16](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/05-run.mp4)
- [Yellow entrance cone](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/06-marker.mp4)
- [Seated Goji welcome](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/07-entry.mp4)
- [Assisted stretch + Mobility popup](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/08b-mat.mp4)
- [Spotted squat + Body Muscle popup](https://raw.githubusercontent.com/gojiphysio/goji/codex/goji-reel-mobile-handoff/marketing/assets/goji-reel-prototype/animation-v8/clips/09-squat.mp4)

## Uniform reference

The black fitted top and leggings follow the therapist's clothing in Goji's [official website treatment photo](https://www.gojiphysio.com/photos/services/prenatal-physiotherapy-warm.webp), linked from the [Goji homepage](https://www.gojiphysio.com/). The small chest mark uses Goji's supplied brand logo. The reference is used for clothing, not to replace the existing character's face or haircut.

[Welcome keyframe](assets/07-entry.png) · [Mat keyframe](assets/08b-mat-start.png) · [Squat keyframe](assets/09-squat.png)

## Editable sources

[Prompts](jobs.json) · [Keyframe prompts](assets/image-prompts.json) · [PNG/SVG overlays](overlays) · [Sound stems](audio) · [Timing](edit-timeline.json) · [Continuity record](continuity.json) · [LTX playbook](research/LTX_PLAYBOOK.md) · [Validation](validation.json)

Generated clips are 576 × 1024 at 24 fps. The precisely trimmed arrival and running excerpts are 1080 × 1920 at 30 fps, extracted from the previous edit. The final master is 1080 × 1920 at 30 fps. The pack contains clips, keyframes, separate overlays, ready-to-use SFX stems and editing scripts. Scripts retain Tidepool's local engine paths; audio conformation reads the previous v6 workspace. Original reference photographs stay local.

Animation uses the installed local LTX-2.5 distilled Q8 MLX model. Keyframes use the built-in image generator. No music or sampled GTA sound files are included; the short effects are original game-style approximations.

The action remains a stylised game parody; the popups are fictional game stats. This is a review cut, not an Instagram publication.

## Motion review

The car-exit shot includes 15 additional source frames (0.5 seconds), showing the player stepping out before the direct cut to running at 00:12.500. No stumble is included. The running shot resumes from the same v6 source frame as v7. Both 30.8-second exports pass full decoding, duration, audio and overlay checks.
