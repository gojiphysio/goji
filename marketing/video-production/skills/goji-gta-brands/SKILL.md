---
name: goji-gta-brands
description: Reuse, extend or revise the fictional Singapore brand logos in Goji's GTA-style world. Preserve approved assets and the user's colour, lettering and emblem-shape direction for shopfronts, bank signs, aircraft and other scene props.
---

# Goji GTA world brands

Use the established fictional logo assets when placing brands in the Goji GTA
world. Read [the brand library](references/brand-library.md) before selecting a
logo or extending the set. It distinguishes accepted masters from rejected drafts.

## Art direction

The user's settled direction is: “keep the genral vibe and brand clours, just
change the shape of the main mark”. Keep the fictional name, familiar colour
palette and lettering character. Redesign the principal symbol's silhouette
without turning it into a completely different corporate identity.

The first attempt kept real emblems too closely; a later wholesale rebrand
strayed too far. Neither exact original emblems with renamed text nor unrelated
colours/type styles meet this brief. The accepted logos are the best calibration.
Do not describe a visual revision or user acceptance as legal clearance.

## Reuse accepted assets

- The repository's `marketing/assets/goji-girl/world-brands/approved-assets.json`
  identifies six accepted masters with SHA-256 hashes. Use those exact files,
  rather than regenerating their appearance from prose.
- **KPKB has no approved logo.** Its hexagonal chart emblem was rejected as
  too far from the reference. `drafts/` and `reference-inputs/` are not production
  asset directories. Revise KPKB only when requested; do not silently substitute
  a rejected or earlier exact-emblem version into a scene.
- Masters are white-background PNGs, not vectors or transparent cutouts. If a
  scene needs another format, derive it from the accepted master and inspect
  lettering, emblem geometry and edges before use. The initial transparent
  generations had fringes/glow; check alpha against both light and dark surfaces.
- For exact in-scene lettering, place the saved logo as a texture or composite
  where practical. Apply the scene's PS2-style material treatment to its surface
  without changing the identity. Use the Goji GTA video workflow for footage.

## Add or revise a brand

Inspect the relevant real-logo reference and label it as research input. For a
revision, also inspect the current fictional master and use that as the edit
target. Lock approved wording, colours and type style; describe the emblem
shape change explicitly. Use built-in image generation for raster artwork.

Save numbered sibling outputs and the exact prompt/reference provenance. Show
a mobile-readable review page with embedded images. New concepts remain proposed
until accepted; approval of one brand does not approve unrelated variants.
Update the selected manifest and checksums only for accepted artwork. Keep the
canonical skill in the repository and refresh the installed copy after changes.
