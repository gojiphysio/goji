# Watercolour studio

Paints Goji's watercolour blooms and exports them as social video or stills, in the same style as the website. No install, no account, no build step.

## Use it

1. Open `index.html` in Chrome (double-click it; it works from disk).
2. Pick a **format**, a **painting**, the **paper** and a **seed** (Shuffle for a new variation; the same seed always paints the same picture).
3. Edit the headline and second line, or clear them for a painting-only clip.
4. **Play preview** to watch it, **Record video** to save an MP4, **Save still** for a PNG.

| Format | Size | For |
|---|---|---|
| Reel or Story 9:16 | 1080 x 1920 | Reels, Stories, TikTok |
| Feed portrait 4:5 | 1080 x 1350 | Instagram feed |
| Square 1:1 | 1080 x 1080 | Instagram square |
| Google Business Profile | 1200 x 1200 | GBP posts |
| Landscape 16:9 | 1920 x 1080 | YouTube, website, slides |

- The dashed lines mark the safe zone (Reels hide the top 220px and bottom 340px under their UI). They are never exported.
- A clip is the painting's own length plus a 2.6s hold, so it ends on the finished picture: about 9s for Ripen, 6s for the others, 23s for two breaths.
- Keep the tab in front while recording; browsers slow down background tabs and the clip will stutter.
- Chrome and Safari record MP4 (H.264), which Instagram takes directly. If a browser can only make WebM, the status line says so.
- Burgundy paper suits the flower and the breathing bloom; the red berry reads best on linen or blush.

## Rules for what you post

- Copy follows `../../strategy/03-compliance-guardrails.md`: no outcome or time promises, no superlatives, no testimonials.
- Links in captions and bios go through `go.gojiphysio.com/<slug>`, never a raw `wa.me` link.
- The breathing clip is guidance: have a physiotherapist check any breathing instructions in the caption.

## Files

- `goji-watercolor.js`: the design system's engine (`components/bundle.js` from the Goji design system, https://claude.ai/artifact/GGKPrziiY9GdwFqYLbW51t), copied unchanged. Copy it again when the engine changes.
- `tokens.css`: the colour tokens the engine paints with, compiled from that system's `tokens.json`.
- `brand-logos.js`: the two GOJI wordmarks inlined as data URIs, so exports work when the page is opened from disk (a file image would block canvas export).
