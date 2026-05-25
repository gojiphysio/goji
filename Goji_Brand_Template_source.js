// Build Goji Physiotherapy pptx design template
// Brand spec from official Goji Brand Guidelines PDF (Annie Lye, designer)
//   DEEP RED      #91171D  brand-primary
//   LINEN WHITE   #F7F2E0  bg-primary / text-secondary
//   EARTH BROWN   #3C1E1F  text-primary
//   MIDNIGHT BLUE #176591  accent
// Fonts: Plus Jakarta Sans SemiBold (display), Inter Light (body), Inter Bold (emphasis)

const pptxgen = require("pptxgenjs");
const path = require("path");

const C = {
  EARTH:    "3C1E1F",   // text-primary
  RED:      "91171D",   // brand-primary
  LINEN:    "F7F2E0",   // bg-primary, text-secondary
  WHITE:    "FFFFFF",
  BLUE:     "176591",   // accent (midnight blue)
  LINEN_DEEP:"E8DEC5",  // slightly deeper linen for dividers
  MUTED_DARK:"8B7373",  // muted earth tone for captions
  MUTED_LIGHT:"D9C9A9", // muted linen for dark-bg captions
  // chart support tones harmonised with the palette
  BLUE_LIGHT: "5A92B5",
  ROSE:       "C68B7A",
  EARTH_LIGHT:"6B4448",
};

// User preference: use Inter throughout (skip Plus Jakarta Sans).
// Display uses Inter with bold:true; body uses Inter regular.
const F = {
  H: "Inter",  // display - paired with bold:true downstream
  B: "Inter",  // body - paired with bold:false
};

const LOGO_DIR = path.join(__dirname, "logo_extract");
const LOGO_DARK_ON_LIGHT = path.join(LOGO_DIR, "logo_main_transparent.png");  // earth brown wordmark on transparent
const LOGO_LIGHT_ON_DARK = path.join(LOGO_DIR, "logo_light_transparent.png"); // linen white wordmark on transparent
const LOGO_WITH_TAGLINE  = path.join(LOGO_DIR, "logo_with_tagline_transparent.png"); // horizontal w/ tagline

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.title = "Goji Physiotherapy - Brand Template";
pres.author = "Goji Physiotherapy";
pres.company = "Goji Physiotherapy";

const W = 13.333;
const H = 7.5;
const M = 0.6;

// Logo native dimensions: 4096 x 2000 (aspect ~2.048:1)
// Use this when sizing the logo so we never distort it.
const LOGO_ASPECT = 4096 / 2000;

// ---------- helpers ----------

function addLogo(slide, opts = {}) {
  // Small wordmark bottom-left
  const { x = M, y = H - 0.65, h = 0.4, dark = false } = opts;
  const w = h * LOGO_ASPECT;
  slide.addImage({
    path: dark ? LOGO_LIGHT_ON_DARK : LOGO_DARK_ON_LIGHT,
    x, y, w, h,
  });
}

function addFooter(slide, opts = {}) {
  const { light = false } = opts;
  const txtColor = light ? C.MUTED_LIGHT : C.MUTED_DARK;
  slide.addText("Lentor Modern  •  gojiphysio.com", {
    x: W - 4.2, y: H - 0.5, w: 4.2 - M, h: 0.3,
    fontFace: F.B, fontSize: 10, color: txtColor,
    align: "right", valign: "middle", margin: 0,
  });
}

function addTitle(slide, text, opts = {}) {
  const { color = C.EARTH, size = 32, x = M, y = M + 0.4, w = W - 2*M, h = 0.9 } = opts;
  slide.addText(text, {
    x, y, w, h,
    fontFace: F.H, fontSize: size, bold: true,
    color, charSpacing: -2, margin: 0,
    align: "left", valign: "top",
  });
}

function addEyebrow(slide, text, opts = {}) {
  const { color = C.RED, x = M, y = M, w = 4, h = 0.3 } = opts;
  slide.addText(text.toUpperCase(), {
    x, y, w, h,
    fontFace: F.H, fontSize: 10, bold: true,
    color, charSpacing: 3, margin: 0,
    align: "left", valign: "top",
  });
}

function addBerryDot(slide, x, y, size = 0.14, color = C.RED) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: size, h: size,
    fill: { color }, line: { color, width: 0 },
  });
}

// =====================================================================
// SLIDE 1 - COVER / HERO  (Linen White bg, per Primary Logo 1 rule)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.LINEN };

  // Earth brown vertical band on the right for visual weight
  s.addShape(pres.shapes.RECTANGLE, {
    x: W - 3.2, y: 0, w: 3.2, h: H,
    fill: { color: C.EARTH }, line: { color: C.EARTH, width: 0 },
  });
  // Deep red dot inside the band (echo of the O)
  s.addShape(pres.shapes.OVAL, {
    x: W - 2.6, y: 2.4, w: 1.8, h: 1.8,
    fill: { color: C.RED }, line: { color: C.RED, width: 0 },
  });

  // Large primary logo with tagline (centered in left area)
  // Native aspect ~3.6:1
  const taglineLogoW = 5.6;
  const taglineLogoH = taglineLogoW / (4096 / 1138);
  s.addImage({
    path: LOGO_WITH_TAGLINE,
    x: M, y: 1.4,
    w: taglineLogoW, h: taglineLogoH,
  });

  // Main title
  s.addText("Presentation Title", {
    x: M, y: 3.2, w: W - 4.2, h: 1.6,
    fontFace: F.H, fontSize: 54, bold: true,
    color: C.EARTH, charSpacing: -3, margin: 0,
    align: "left", valign: "top",
  });

  // Subtitle
  s.addText("A short, supporting line that sets up the deck.", {
    x: M, y: 5.0, w: W - 4.2, h: 0.7,
    fontFace: F.B, fontSize: 18,
    color: C.MUTED_DARK, margin: 0,
  });

  // Presenter line
  s.addText("Presenter Name  •  Role  •  Date", {
    x: M, y: H - 0.9, w: W - 4.2, h: 0.3,
    fontFace: F.B, fontSize: 12,
    color: C.EARTH, margin: 0,
  });
}

// =====================================================================
// SLIDE 2 - AGENDA
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  addEyebrow(s, "Agenda");
  addTitle(s, "What we'll cover today");

  const items = [
    "Where we are now",
    "What we're seeing",
    "What we'll do next",
    "How we'll measure progress",
    "Questions & discussion",
  ];

  items.forEach((item, i) => {
    const y = 2.3 + i * 0.85;
    s.addText(String(i + 1).padStart(2, "0"), {
      x: M, y: y, w: 0.9, h: 0.7,
      fontFace: F.H, fontSize: 36, bold: true,
      color: C.RED, charSpacing: -2, margin: 0,
      align: "left", valign: "middle",
    });
    s.addText(item, {
      x: M + 1.0, y: y, w: W - M - 1.0 - M, h: 0.7,
      fontFace: F.H, fontSize: 22, bold: true,
      color: C.EARTH, charSpacing: -1, margin: 0,
      align: "left", valign: "middle",
    });
    s.addShape(pres.shapes.LINE, {
      x: M, y: y + 0.78, w: W - 2*M, h: 0,
      line: { color: C.LINEN_DEEP, width: 1 },
    });
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 3 - SECTION DIVIDER (Linen White)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.LINEN };

  // Vertical earth band on the left
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.4, h: H,
    fill: { color: C.EARTH }, line: { color: C.EARTH, width: 0 },
  });

  s.addText("01", {
    x: 1.1, y: 2.5, w: 2.5, h: 1.8,
    fontFace: F.H, fontSize: 120, bold: true,
    color: C.RED, charSpacing: -5, margin: 0,
    align: "left", valign: "middle",
  });

  s.addText("SECTION", {
    x: 4.0, y: 2.95, w: 4, h: 0.4,
    fontFace: F.H, fontSize: 12, bold: true,
    color: C.RED, charSpacing: 4, margin: 0,
  });

  s.addText("Section Title Goes Here", {
    x: 4.0, y: 3.35, w: W - 4.0 - M, h: 1.4,
    fontFace: F.H, fontSize: 48, bold: true,
    color: C.EARTH, charSpacing: -2, margin: 0,
    align: "left", valign: "top",
  });

  s.addText("Optional one-line context that frames what's coming.", {
    x: 4.0, y: 4.55, w: W - 4.0 - M, h: 0.6,
    fontFace: F.B, fontSize: 16,
    color: C.MUTED_DARK, margin: 0,
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 4 - CONTENT (title + bullets)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  addEyebrow(s, "Topic");
  addTitle(s, "Single-idea slide title");

  s.addText("Optional short intro that sets up the bullets below. Keep this to one or two sentences.", {
    x: M, y: 1.85, w: W - 2*M, h: 0.7,
    fontFace: F.B, fontSize: 16,
    color: C.EARTH, margin: 0,
  });

  const bullets = [
    "First key point - lead with the insight, not the setup.",
    "Second key point - keep each line to a single idea.",
    "Third key point - supporting detail or numbers go inline.",
    "Fourth key point - end with the implication or next step.",
  ];

  bullets.forEach((line, i) => {
    const y = 3.0 + i * 0.7;
    addBerryDot(s, M + 0.08, y + 0.18, 0.16);
    s.addText(line, {
      x: M + 0.45, y: y, w: W - M - 0.45 - M, h: 0.55,
      fontFace: F.B, fontSize: 16,
      color: C.EARTH, margin: 0,
      valign: "middle",
    });
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 5 - TWO COLUMN
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  addEyebrow(s, "Comparison");
  addTitle(s, "Two-column layout");

  const colW = (W - 2*M - 0.5) / 2;
  const colY = 2.1;
  const colH = 4.6;

  s.addText("Heading A", {
    x: M, y: colY, w: colW, h: 0.6,
    fontFace: F.H, fontSize: 22, bold: true,
    color: C.RED, charSpacing: -1, margin: 0,
  });
  s.addText([
    { text: "Point one in this column.", options: { bullet: { code: "25CF" }, breakLine: true } },
    { text: "Point two with a bit more detail.", options: { bullet: { code: "25CF" }, breakLine: true } },
    { text: "Point three to round it out.", options: { bullet: { code: "25CF" } } },
  ], {
    x: M, y: colY + 0.7, w: colW, h: colH - 0.7,
    fontFace: F.B, fontSize: 15,
    color: C.EARTH, paraSpaceAfter: 8, margin: 0,
  });

  s.addShape(pres.shapes.LINE, {
    x: M + colW + 0.25, y: colY, w: 0, h: colH,
    line: { color: C.LINEN_DEEP, width: 1 },
  });

  s.addText("Heading B", {
    x: M + colW + 0.5, y: colY, w: colW, h: 0.6,
    fontFace: F.H, fontSize: 22, bold: true,
    color: C.RED, charSpacing: -1, margin: 0,
  });
  s.addText([
    { text: "Counterpoint or parallel point.", options: { bullet: { code: "25CF" }, breakLine: true } },
    { text: "Supporting detail.", options: { bullet: { code: "25CF" }, breakLine: true } },
    { text: "Closing thought.", options: { bullet: { code: "25CF" } } },
  ], {
    x: M + colW + 0.5, y: colY + 0.7, w: colW, h: colH - 0.7,
    fontFace: F.B, fontSize: 15,
    color: C.EARTH, paraSpaceAfter: 8, margin: 0,
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 6 - IMAGE + TEXT
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  const imgX = M, imgY = M, imgW = 6.0, imgH = H - 2*M;
  s.addShape(pres.shapes.RECTANGLE, {
    x: imgX, y: imgY, w: imgW, h: imgH,
    fill: { color: C.LINEN }, line: { color: C.LINEN_DEEP, width: 0 },
  });
  s.addText("[ Replace with image ]", {
    x: imgX, y: imgY + imgH/2 - 0.3, w: imgW, h: 0.6,
    fontFace: F.B, fontSize: 13,
    color: C.MUTED_DARK, align: "center", valign: "middle", margin: 0,
  });

  const txtX = imgX + imgW + 0.5;
  const txtW = W - txtX - M;

  s.addText("CATEGORY", {
    x: txtX, y: imgY + 0.3, w: txtW, h: 0.3,
    fontFace: F.H, fontSize: 11, bold: true,
    color: C.RED, charSpacing: 4, margin: 0,
  });
  s.addText("Image-led slide for narrative or product moments.", {
    x: txtX, y: imgY + 0.7, w: txtW, h: 2.4,
    fontFace: F.H, fontSize: 30, bold: true,
    color: C.EARTH, charSpacing: -2, margin: 0,
    align: "left", valign: "top",
  });
  s.addText("Use the left panel for a photograph - clinic, team, patient moment (with consent). Keep the right side calm: a single supporting paragraph, no bullets.", {
    x: txtX, y: imgY + 3.4, w: txtW, h: 2.4,
    fontFace: F.B, fontSize: 15,
    color: C.EARTH, paraSpaceAfter: 8, margin: 0,
  });

  addBerryDot(s, txtX, imgY + imgH - 0.5, 0.16);
  s.addText("Caption or attribution", {
    x: txtX + 0.3, y: imgY + imgH - 0.6, w: txtW - 0.3, h: 0.3,
    fontFace: F.B, fontSize: 11,
    color: C.MUTED_DARK, margin: 0, valign: "middle",
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 7 - DATA / CHART
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  addEyebrow(s, "Performance");
  addTitle(s, "Sample monthly metric");

  const chartData = [{
    name: "Visits",
    labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    values: [120, 180, 210, 260, 305, 360],
  }];

  s.addChart(pres.charts.BAR, chartData, {
    x: M, y: 2.0, w: 8.0, h: 4.8,
    barDir: "col",
    chartColors: [C.RED],
    chartArea: { fill: { color: C.WHITE } },
    plotArea: { fill: { color: C.WHITE } },
    catAxisLabelColor: C.MUTED_DARK,
    catAxisLabelFontFace: F.B,
    catAxisLabelFontSize: 11,
    valAxisLabelColor: C.MUTED_DARK,
    valAxisLabelFontFace: F.B,
    valAxisLabelFontSize: 10,
    valGridLine: { color: C.LINEN_DEEP, size: 0.5 },
    catGridLine: { style: "none" },
    showValue: true,
    dataLabelPosition: "outEnd",
    dataLabelColor: C.EARTH,
    dataLabelFontFace: F.B,
    dataLabelFontSize: 10,
    showLegend: false,
    barGapWidthPct: 60,
  });

  const ix = 8.9, iy = 2.0, iw = W - ix - M, ih = 4.8;
  s.addShape(pres.shapes.RECTANGLE, {
    x: ix, y: iy, w: iw, h: ih,
    fill: { color: C.LINEN }, line: { color: C.LINEN, width: 0 },
  });
  s.addText("INSIGHT", {
    x: ix + 0.3, y: iy + 0.3, w: iw - 0.6, h: 0.3,
    fontFace: F.H, fontSize: 10, bold: true,
    color: C.RED, charSpacing: 4, margin: 0,
  });
  s.addText("+200%", {
    x: ix + 0.3, y: iy + 0.7, w: iw - 0.6, h: 1.0,
    fontFace: F.H, fontSize: 48, bold: true,
    color: C.EARTH, charSpacing: -2, margin: 0,
  });
  s.addText("growth in monthly patient visits over the first half of the year.", {
    x: ix + 0.3, y: iy + 1.8, w: iw - 0.6, h: 1.8,
    fontFace: F.B, fontSize: 13,
    color: C.EARTH, margin: 0,
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 8 - KPI DASHBOARD (4 stats)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  addEyebrow(s, "At a glance");
  addTitle(s, "Key metrics this period");

  const stats = [
    { value: "342",  label: "Patients seen",       sub: "+18% vs last month" },
    { value: "94%",  label: "Return rate",          sub: "Across all services" },
    { value: "4.9",  label: "Avg. patient rating",  sub: "From 87 reviews" },
    { value: "$28k", label: "Revenue",              sub: "Recognised this month" },
  ];

  const gap = 0.3;
  const cardW = (W - 2*M - 3*gap) / 4;
  const cardY = 2.2;
  const cardH = 3.8;

  stats.forEach((stat, i) => {
    const x = M + i * (cardW + gap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cardY, w: cardW, h: cardH,
      fill: { color: C.LINEN }, line: { color: C.LINEN, width: 0 },
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cardY, w: cardW, h: 0.12,
      fill: { color: C.RED }, line: { color: C.RED, width: 0 },
    });
    s.addText(stat.value, {
      x: x + 0.3, y: cardY + 0.6, w: cardW - 0.6, h: 1.6,
      fontFace: F.H, fontSize: 56, bold: true,
      color: C.EARTH, charSpacing: -3, margin: 0,
      align: "left", valign: "middle",
    });
    s.addText(stat.label, {
      x: x + 0.3, y: cardY + 2.3, w: cardW - 0.6, h: 0.5,
      fontFace: F.H, fontSize: 16, bold: true,
      color: C.EARTH, charSpacing: -1, margin: 0,
    });
    s.addText(stat.sub, {
      x: x + 0.3, y: cardY + 2.85, w: cardW - 0.6, h: 0.5,
      fontFace: F.B, fontSize: 12,
      color: C.MUTED_DARK, margin: 0,
    });
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 9 - SERVICES GRID (3 tiles) - on Linen White bg
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.LINEN };

  addEyebrow(s, "What we offer");
  addTitle(s, "Care that grows with you.");

  const services = [
    { title: "Physiotherapy", body: "Assessment and treatment for pain, injury, recovery, pelvic health, women's health, paediatric, vestibular, and lymphatic concerns." },
    { title: "Mummy & Baby Assessment", body: "A joint assessment for postpartum mothers and babies aged 0-6 months, supporting recovery and early development." },
    { title: "Clinical Pilates", body: "Physiotherapist-led reformer Pilates for rehabilitation, movement retraining, strength, and a safe return to activity." },
  ];

  const gap = 0.4;
  const cardW = (W - 2*M - 2*gap) / 3;
  const cardY = 2.3;
  const cardH = 4.4;

  services.forEach((svc, i) => {
    const x = M + i * (cardW + gap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: cardY, w: cardW, h: cardH,
      fill: { color: C.WHITE }, line: { color: C.WHITE, width: 0 },
    });
    addBerryDot(s, x + 0.4, cardY + 0.5, 0.18);
    s.addText(String(i + 1).padStart(2, "0"), {
      x: x + 0.7, y: cardY + 0.32, w: 1.5, h: 0.5,
      fontFace: F.H, fontSize: 12, bold: true,
      color: C.RED, charSpacing: 3, margin: 0,
      valign: "middle",
    });
    s.addText(svc.title, {
      x: x + 0.4, y: cardY + 1.2, w: cardW - 0.8, h: 1.4,
      fontFace: F.H, fontSize: 22, bold: true,
      color: C.EARTH, charSpacing: -1, margin: 0,
      align: "left", valign: "top",
    });
    s.addText(svc.body, {
      x: x + 0.4, y: cardY + 2.5, w: cardW - 0.8, h: cardH - 2.7,
      fontFace: F.B, fontSize: 12,
      color: C.EARTH, margin: 0,
    });
  });

  addLogo(s);
  addFooter(s);
}

// =====================================================================
// SLIDE 10 - TESTIMONIAL / PULL QUOTE  (Deep Red bg per Primary Logo 3)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.RED };

  // Quote mark in linen
  s.addText("“", {
    x: M, y: 0.6, w: 2.5, h: 2.5,
    fontFace: F.H, fontSize: 220, bold: true,
    color: C.LINEN, charSpacing: 0, margin: 0,
    align: "left", valign: "top",
  });

  // Quote - per brand spec, quotes are always Plus Jakarta Sans SemiBold
  s.addText("You are heard before you are treated, with care that combines clinical expertise and real understanding.", {
    x: M, y: 2.6, w: W - 2*M, h: 2.6,
    fontFace: F.H, fontSize: 34, bold: true,
    color: C.LINEN, charSpacing: -1.5, margin: 0,
    align: "left", valign: "top",
  });

  s.addText("Cheryl Long", {
    x: M, y: 5.4, w: 8, h: 0.5,
    fontFace: F.H, fontSize: 18, bold: true,
    color: C.LINEN, charSpacing: -1, margin: 0,
  });
  s.addText("Founder & Clinical Director, Goji Physiotherapy", {
    x: M, y: 5.85, w: 8, h: 0.4,
    fontFace: F.B, fontSize: 13,
    color: C.MUTED_LIGHT, margin: 0,
  });

  addLogo(s, { dark: true });
  addFooter(s, { light: true });
}

// =====================================================================
// SLIDE 11 - CTA / CONTACT  (Linen White)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.LINEN };

  addEyebrow(s, "Get in touch");
  s.addText("Book your appointment.", {
    x: M, y: M + 0.5, w: W - 2*M, h: 1.8,
    fontFace: F.H, fontSize: 60, bold: true,
    color: C.EARTH, charSpacing: -3, margin: 0,
    align: "left", valign: "top",
  });

  s.addText("Care that grows with you - one clinic, every life stage.", {
    x: M, y: 2.8, w: W - 2*M, h: 0.7,
    fontFace: F.B, fontSize: 18,
    color: C.MUTED_DARK, margin: 0,
  });

  const blockY = 4.4;
  const blockH = 2.0;
  const blocks = [
    { label: "ADDRESS", lines: ["Lentor Modern, #01-13", "1 Lentor Central", "Singapore 788887"] },
    { label: "HOURS",   lines: ["Mon - Sat: 8am - 8pm", "Sun & PH: By appointment"] },
    { label: "CONTACT", lines: ["WhatsApp: +65 8377 0401", "hello@gojiphysio.com", "gojiphysio.com"] },
  ];
  const bgap = 0.4;
  const bw = (W - 2*M - 2*bgap) / 3;

  blocks.forEach((b, i) => {
    const x = M + i * (bw + bgap);
    addBerryDot(s, x, blockY, 0.16);
    s.addText(b.label, {
      x: x + 0.3, y: blockY - 0.05, w: bw - 0.3, h: 0.3,
      fontFace: F.H, fontSize: 10, bold: true,
      color: C.RED, charSpacing: 4, margin: 0, valign: "middle",
    });
    s.addText(b.lines.map((l, k) => ({
      text: l, options: k === b.lines.length - 1 ? {} : { breakLine: true },
    })), {
      x, y: blockY + 0.45, w: bw, h: blockH - 0.45,
      fontFace: F.B, fontSize: 14,
      color: C.EARTH, paraSpaceAfter: 4, margin: 0,
    });
  });

  addLogo(s);
}

// =====================================================================
// SLIDE 12 - CLOSING / THANK YOU  (Deep Red bg, primary logo 3 rule)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.RED };

  // Linen-toned dot mark top-right
  s.addShape(pres.shapes.OVAL, {
    x: W - 2.1, y: 0.5, w: 1.6, h: 1.6,
    fill: { color: C.LINEN }, line: { color: C.LINEN, width: 0 },
  });

  s.addText("Thank you.", {
    x: M, y: 2.8, w: W - 2*M, h: 2.0,
    fontFace: F.H, fontSize: 96, bold: true,
    color: C.LINEN, charSpacing: -4, margin: 0,
    align: "left", valign: "top",
  });

  s.addText("Questions are welcome.", {
    x: M, y: 5.0, w: W - 2*M, h: 0.7,
    fontFace: F.B, fontSize: 20,
    color: C.MUTED_LIGHT, margin: 0,
  });

  s.addText("hello@gojiphysio.com   •   WhatsApp +65 8377 0401   •   gojiphysio.com", {
    x: M, y: H - 1.3, w: W - 2*M, h: 0.4,
    fontFace: F.B, fontSize: 12,
    color: C.LINEN, margin: 0,
  });

  addLogo(s, { dark: true });
}

// =====================================================================
// SLIDE 13 - STYLE GUIDE / BRAND REFERENCE
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.WHITE };

  addEyebrow(s, "Reference");
  addTitle(s, "Brand quick reference");

  const swatches = [
    { c: C.RED,    name: "Deep Red",      hex: "#91171D", role: "Brand primary" },
    { c: C.LINEN,  name: "Linen White",   hex: "#F7F2E0", role: "Bg / text-secondary" },
    { c: C.EARTH,  name: "Earth Brown",   hex: "#3C1E1F", role: "Text primary"  },
    { c: C.BLUE,   name: "Midnight Blue", hex: "#176591", role: "Accent"        },
    { c: C.WHITE,  name: "White",         hex: "#FFFFFF", role: "Content bg"    },
  ];
  const sgap = 0.3;
  const sw = (W - 2*M - 4*sgap) / 5;
  const sy = 1.95;
  swatches.forEach((sw_, i) => {
    const x = M + i * (sw + sgap);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: sy, w: sw, h: 1.6,
      fill: { color: sw_.c },
      line: { color: sw_.c === C.WHITE ? C.LINEN_DEEP : sw_.c, width: sw_.c === C.WHITE ? 1 : 0 },
    });
    s.addText(sw_.name, {
      x, y: sy + 1.7, w: sw, h: 0.3,
      fontFace: F.H, fontSize: 13, bold: true,
      color: C.EARTH, charSpacing: -1, margin: 0,
    });
    s.addText(sw_.hex, {
      x, y: sy + 2.0, w: sw, h: 0.3,
      fontFace: F.B, fontSize: 11,
      color: C.MUTED_DARK, margin: 0,
    });
    s.addText(sw_.role, {
      x, y: sy + 2.3, w: sw, h: 0.4,
      fontFace: F.B, fontSize: 10,
      color: C.MUTED_DARK, margin: 0,
    });
  });

  // Type specimens
  const ty = 5.0;
  s.addText("TYPOGRAPHY", {
    x: M, y: ty, w: 6, h: 0.3,
    fontFace: F.H, fontSize: 10, bold: true,
    color: C.RED, charSpacing: 4, margin: 0,
  });
  s.addText("Inter Bold - display", {
    x: M, y: ty + 0.35, w: 8, h: 0.6,
    fontFace: F.H, fontSize: 28, bold: true,
    color: C.EARTH, charSpacing: -1.5, margin: 0,
  });
  s.addText("Inter Regular - body copy. Never italic.", {
    x: M, y: ty + 1.05, w: 8, h: 0.5,
    fontFace: F.B, fontSize: 16,
    color: C.EARTH, margin: 0,
  });

  s.addText("VOICE", {
    x: 8.0, y: ty, w: 4, h: 0.3,
    fontFace: F.H, fontSize: 10, bold: true,
    color: C.RED, charSpacing: 4, margin: 0,
  });
  s.addText("Premium. Modern. Expertise. We are not here to fix you - we help you feel confident in your body again.", {
    x: 8.0, y: ty + 0.35, w: W - 8.0 - M, h: 1.6,
    fontFace: F.B, fontSize: 13,
    color: C.EARTH, margin: 0,
  });

  addLogo(s);
  addFooter(s);
}

pres.writeFile({ fileName: "Goji_Brand_Template.pptx" })
  .then(fn => console.log("Wrote:", fn))
  .catch(e => { console.error(e); process.exit(1); });
