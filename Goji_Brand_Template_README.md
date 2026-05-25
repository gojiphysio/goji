# Goji Physiotherapy - Brand Slide Template

A 13-slide pptx design template built from the official Goji Brand Guidelines (Annie Lye, designer) and tuned for use as a reusable Google Slides template.

## Files

- `Goji_Brand_Template.pptx` - the master template
- `Goji_Brand_Template_Preview.pdf` - flat preview of every layout
- `Goji_Brand_Template_source.js` - the build script (rebuild after changes with `node Goji_Brand_Template_source.js`)
- `Goji_Brand_Template_README.md` - this file
- `brand_assets/` - the official guideline PDF and transparent logo PNGs

## How to use it in Google Slides

1. In Google Drive, click **New > File upload** and upload `Goji_Brand_Template.pptx`.
2. Right-click the uploaded file > **Open with > Google Slides**. The deck converts (logos render as PNG images; fonts are Google Fonts so they survive the conversion).
3. Once open: **File > Save as Google Slides** to keep a native Google Slides copy.
4. **File > Make a copy** every time you start a new deck.
5. To get strict brand weights (SemiBold display, Light body), select all text and adjust weight in the font picker. See "Font weight nuance" below.

## What is in the deck

| # | Layout | Use for |
|---|--------|---------|
| 1 | Cover / hero | Opening slide of any deck |
| 2 | Agenda | Table of contents, 1-5 items numbered |
| 3 | Section divider | Major chapter breaks |
| 4 | Content (bullets) | Standard text slide, 3-5 points |
| 5 | Two-column | Side-by-side comparison or paired ideas |
| 6 | Image + text | Half-bleed photo on the left, story on the right |
| 7 | Data / chart | One chart with a callout insight panel |
| 8 | KPI dashboard | Four big-number stats in a row |
| 9 | Services grid | Three product/service cards |
| 10 | Testimonial / quote | Pull quote on Deep Red (uses Primary Logo 3 rule) |
| 11 | CTA / contact | Booking prompt with address, hours, contact |
| 12 | Thank you / closing | Final slide on Deep Red |
| 13 | Brand reference | Cheat sheet of colours, fonts, voice |

## Brand system (per official guidelines)

### Colours

| Role | Name | Hex |
|------|------|-----|
| Brand primary | Deep Red | `#91171D` |
| Text primary | Earth Brown | `#3C1E1F` |
| Background primary / text secondary | Linen White | `#F7F2E0` |
| Accent | Midnight Blue | `#176591` |
| Content background | White | `#FFFFFF` |

Use Deep Red as an accent (dots, callouts, key numbers, CTAs). Linen White and White are the working backgrounds. Earth Brown is text. Midnight Blue is a sparingly-used accent for secondary chart series or signal moments.

### Typography

- **Display:** Inter Bold
- **Body:** Inter Regular (never italic; Inter Bold for emphasis)

The template uses Inter for everything. Inter is a Google Font and renders natively in Google Slides. The brand guideline names Plus Jakarta Sans SemiBold for display, but a single-family approach keeps the deck simpler and avoids font-weight friction in Google Slides. If you ever want to switch back to the Jakarta+Inter pairing, edit the `F.H` constant at the top of `Goji_Brand_Template_source.js`.

### Logos

The deck uses the actual logo PNGs from the brand guideline:

- `logo_main_transparent.png` - GOJI wordmark in Earth Brown with Deep Red O (for light backgrounds)
- `logo_light_transparent.png` - GOJI wordmark in Linen White with Deep Red O (for dark/red backgrounds)
- `logo_with_tagline_transparent.png` - horizontal lockup with "Women's and Family Physiotherapy" tagline (cover slides)
- `logo_mark_transparent.png` - the standalone O mark (favicons, small spaces)

Per brand rule: use the variant that matches the slide background. The deck handles this automatically.

## Voice & tone

From the brand guideline: "premium, modern and expertise."

From the clinic's own copy:

> We are not here to fix you. We help you feel confident in your body again.

Warm. Confident. Clinical without coldness. Lead with the insight or the patient outcome, not the setup.

## Do / do not

**Do**
- Keep slide titles to one short sentence
- Use the berry dot motif as a bullet (already styled)
- Pair an image with text when possible
- Use Deep Red as an accent, not a fill area (the testimonial and closing slides are the exception)

**Do not**
- Use emdashes - use regular dashes only (project style)
- Stretch Deep Red across large surfaces beyond the testimonial/closing
- Italicise Inter body text (against brand spec)
- Mix in other fonts - stick to Plus Jakarta Sans + Inter

## Editing the template

The source of truth is `Goji_Brand_Template_source.js`. To rebuild after changes:

```
cd '/Users/charles/Documents/Claude/Projects/Goji Business Inteligence'
npm install pptxgenjs path
node Goji_Brand_Template_source.js
```

The script references the logos in `brand_assets/` (script expects a sibling `logo_extract/` folder by default; adjust LOGO_DIR if running from the workspace folder).
