# Singapore vehicle references — CONFRONT / GRIP

Generated 25 November 2026 using the built-in image-generation tool. These are proposed vehicle appearance references for the Goji GTA series, matching the accepted SOS Transit bus look; they are not rigged 3D assets or motion/geometry validation.

## CONFRONT cab

Blue older Singapore-style sedan with the 2006 Comfort logo treatment adapted to read **Confront**: red open-ring emblem, orange underline, and narrow italic white lettering on the front door and roof sign. Current reference: **v3**, with manufacturer badges removed, plain wheel caps and fictional plate **S7K9X2Q**. The 2006-style Confront logo is retained.

![CONFRONT cab](confront-cab-v3.png)

[Open full-size CONFRONT reference](confront-cab-v3.png)

## GRIP private-hire car

White compact liftback with green door/rear-quarter wrap and white double-line GRIP lettering. Plain roof; private-hire windscreen decal. Current reference: **v2**, with manufacturer and HYBRID badges removed, plain wheel caps and fictional plate **S4N8V6R**.

![GRIP car](grip-car-v2.png)

[Open full-size GRIP reference](grip-car-v2.png)

## Continuity and provenance

- Both images use the same SOS Transit bus image as the style/composition reference: `episode-02/revision-07/frames/vehicle-style-reference.png` from the active Episode 2 worktree.
- Preserve the spelling **CONFRONT** and **GRIP** in future views; preserve the taxi/private-hire roof distinction.
- Match angular game geometry, painted wear, subdued reflections and the tropical parking-lot setting.
- Singapore vehicles use right-hand driving positions. Before door-entry or driving animation, confirm seat/door anchors in the 3D asset; a single still is not a geometry test.
- Visual review of current revisions: real maker emblems removed from grilles and wheel caps; GRIP fender badge removed; both plates match the recorded strings. Full vehicles, accepted service branding and common rendering style remain visible.
- User approved the 2006-style Confront logo direction, then requested manufacturer anonymisation and jumbled plates starting with S. The current revisions implement that request; no episode frames were replaced.
- Use unbadged generic vehicle descriptions in future generation, not real manufacturer/model names. Keep the same fictional plates across reverse views and motion.
- Full generation prompts: [prompts.json](prompts.json).

### 2006 logo source for CONFRONT v2

Logo reference: [Comfort Taxi-Crown.JPG](https://commons.wikimedia.org/wiki/File:Comfort_Taxi-Crown.JPG), photographed by Terence Ong on 14 March 2006, available under [CC BY 2.5](https://creativecommons.org/licenses/by/2.5/). Used as the visual reference for the emblem, lettering and front-door placement; the name was changed from Comfort to Confront. The generated car and setting are retained from v1. The roof-sign logo is an adaptation, not a claim that this exact sign existed in 2006.

Built-in image generation performed the edit. Visual review confirmed the requested spelling, red ring/orange underline, front-door placement and retained car/background.

### Archived revisions

- [CONFRONT v1](confront-cab-v1.png): initial generic service lettering.
- [CONFRONT v2](confront-cab-v2.png): accepted 2006-style logo, before manufacturer removal.
- [GRIP v1](grip-car-v1.png): initial version before manufacturer removal.

The archived files retain superseded real maker emblems and plate strings; use the current references above for new scenes. Full prompts for every version are retained in prompts.json.
