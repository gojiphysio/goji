/* Goji watercolour engine. Vendored unchanged from the Goji design system
   (components/bundle.js in https://claude.ai/artifact/GGKPrziiY9GdwFqYLbW51t);
   the same file as marketing/assets/watercolor-studio/goji-watercolor.js.
   Re-copy rather than edit here. Without React it exposes only the engine:
   Goji.paint / veil / grow / breathe / enhance. */
/* @ds-bundle: {"format":4,"namespace":"Goji","components":[{"name":"Button"},{"name":"Eyebrow"},{"name":"SectionHeading"},{"name":"PaintedUnderline"},{"name":"BerryList"},{"name":"StatBlock"},{"name":"CareCard"},{"name":"ImageTextSplit"},{"name":"PractitionerCard"},{"name":"QuoteSurface"},{"name":"ContactBlock"},{"name":"FormField"},{"name":"SiteHeader"},{"name":"LogoLockup"},{"name":"WatercolorBloom"},{"name":"WatercolorWash"},{"name":"PaintedImage"},{"name":"Reveal"},{"name":"GrowthPath"},{"name":"BreathingBloom"}]} */
(function () {
  "use strict";
  var W = window, D = document;

  /* Brand asset URLs. On the Astro site, override with Goji.assets = { logoMain: "/brand/logo_main_transparent.webp", ... }. */
  var assets = {
    logoMain: "/_blob/50b629a42062b6a1d6ffd43dde475cc6",
    logoLight: "/_blob/8d8a86efce7d397bf08db552d8de3730",
    logoMark: "/_blob/e59797692e50706130e4cc65fcf64ea3",
    logoTagline: "/_blob/224873e68844d00fb81f5f600556fa41"
  };

  D.documentElement.classList.add("gj-js");

  /* ================================================================
     Utilities
     ================================================================ */
  function rng(seed) {
    var a = (seed >>> 0) || 1;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gauss(r) {
    var u = 0, v = 0;
    while (!u) u = r();
    while (!v) v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  function clamp01(t) { return t < 0 ? 0 : t > 1 ? 1 : t; }
  function easeOut(t) { return 1 - Math.pow(1 - t, 4); }
  function reducedMotion() { return !!(W.matchMedia && W.matchMedia("(prefers-reduced-motion: reduce)").matches); }
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(" "); }

  var FALLBACK = {
    goji: "#c8372d", "deep-red": "#91171d", burgundy: "#5e1016", blush: "#f1dcd2", clay: "#d69a8a",
    lilac: "#b7a3d0", sage: "#7f9168", ochre: "#d4a64a", linen: "#f7f2e0", "bg-page": "#f7f2e0"
  };
  function tokenColor(el, name) {
    var v = getComputedStyle(el).getPropertyValue("--" + name).trim();
    if (!v || v.indexOf("var(") === 0) {
      v = getComputedStyle(D.documentElement).getPropertyValue("--" + name).trim();
    }
    return v && v.indexOf("var(") !== 0 ? v : FALLBACK[name] || "#91171d";
  }

  /* Shared IntersectionObserver: run cb once, when el is at least `ratio` visible. */
  function onVisible(el, cb, ratio) {
    if (!("IntersectionObserver" in W)) { cb(el); return function () {}; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { io.disconnect(); cb(el); }
      });
    }, { threshold: ratio == null ? 0.2 : ratio, rootMargin: "0px 0px -6% 0px" });
    io.observe(el);
    return function () { io.disconnect(); };
  }

  /* ================================================================
     Watercolour engine
     Pigment is painted procedurally in the style of layered,
     deformed polygons (each layer ~5% opacity), then revealed through
     an organically-edged, soft mask that spreads from a touch point,
     the way wet pigment blooms into damp paper. Paper grain erodes
     the dried pigment. Nothing is hand-drawn frame by frame.
     ================================================================ */
  function deform(pts, depth, amt, r) {
    for (var d = 0; d < depth; d++) {
      var out = [], n = pts.length;
      for (var i = 0; i < n; i++) {
        var a = pts[i], b = pts[(i + 1) % n];
        out.push(a);
        var dx = b[0] - a[0], dy = b[1] - a[1];
        var len = Math.sqrt(dx * dx + dy * dy), v = (a[2] + b[2]) / 2;
        out.push([
          (a[0] + b[0]) / 2 + gauss(r) * len * amt * v,
          (a[1] + b[1]) / 2 + gauss(r) * len * amt * v,
          v * (0.85 + r() * 0.3)
        ]);
      }
      pts = out;
    }
    return pts;
  }
  function tracePoly(ctx, pts, k, ox, oy) {
    k = k || 1; ox = ox || 0; oy = oy || 0;
    ctx.beginPath();
    ctx.moveTo(ox + pts[0][0] * k, oy + pts[0][1] * k);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(ox + pts[i][0] * k, oy + pts[i][1] * k);
    ctx.closePath();
  }

  /* Shapes, in px relative to the stroke centre. U = the composition unit in px. */
  var SHAPES = {
    circle: function (st, U) {
      var pts = [], n = 14;
      for (var i = 0; i < n; i++) {
        var a = (i / n) * Math.PI * 2;
        pts.push([Math.cos(a) * st.rx * U, Math.sin(a) * (st.ry || st.rx) * U]);
      }
      return pts;
    },
    berry: function (st, U) {
      var pts = [], n = 20;
      for (var i = 0; i < n; i++) {
        var t = (i / n) * Math.PI * 2, c = Math.cos(t);
        pts.push([
          st.rx * U * Math.sin(t) * (0.9 - 0.1 * c),
          -st.ry * U * c + 0.1 * st.ry * U * Math.pow(Math.max(0, -c), 8)
        ]);
      }
      return pts;
    },
    /* petal and leaf run from the centre outward along `rot` */
    petal: function (st, U) { return blade(st, U, function (u) { return Math.pow(Math.sin(Math.PI * Math.pow(u, 0.72)), 0.75); }); },
    leaf: function (st, U) { return blade(st, U, function (u) { return Math.pow(Math.sin(Math.PI * u), 1.15); }); },
    /* stem: a tapered ribbon along a quadratic curve; p0, p1, p2 in composition units */
    stem: function (st, U) {
      var top = [], bot = [], n = 16, w = st.w * U;
      for (var i = 0; i <= n; i++) {
        var t = i / n, m = 1 - t;
        var x = m * m * st.p0[0] + 2 * m * t * st.p1[0] + t * t * st.p2[0];
        var y = m * m * st.p0[1] + 2 * m * t * st.p1[1] + t * t * st.p2[1];
        var tx = 2 * m * (st.p1[0] - st.p0[0]) + 2 * t * (st.p2[0] - st.p1[0]);
        var ty = 2 * m * (st.p1[1] - st.p0[1]) + 2 * t * (st.p2[1] - st.p1[1]);
        var l = Math.sqrt(tx * tx + ty * ty) || 1, half = (w / 2) * (1 - 0.45 * t);
        x = (x - st.x) * U; y = (y - st.y) * U;
        top.push([x - (ty / l) * half, y + (tx / l) * half]);
        bot.unshift([x + (ty / l) * half, y - (tx / l) * half]);
      }
      return top.concat(bot);
    }
  };
  /* ribbon: a tapered band along a polyline of px points (st.pts), for long vines */
  SHAPES.ribbon = function (st) {
    var top = [], bot = [], P = st.pts, n = P.length - 1;
    for (var i = 0; i <= n; i++) {
      var a = P[Math.max(0, i - 1)], b = P[Math.min(n, i + 1)];
      var tx = b[0] - a[0], ty = b[1] - a[1], l = Math.sqrt(tx * tx + ty * ty) || 1;
      var half = (st.w / 2) * (1 - (st.taper || 0) * (i / n));
      top.push([P[i][0] - st.x - (ty / l) * half, P[i][1] - st.y + (tx / l) * half]);
      bot.unshift([P[i][0] - st.x + (ty / l) * half, P[i][1] - st.y - (tx / l) * half]);
    }
    return top.concat(bot);
  };
  function blade(st, U, f) {
    var top = [], bot = [], n = 9, L = st.len * U, Wd = st.w * U;
    for (var i = 0; i <= n; i++) {
      var u = i / n;
      top.push([u * L, (Wd / 2) * f(u)]);
      if (i > 0 && i < n) bot.unshift([u * L, -(Wd / 2) * f(u)]);
    }
    return top.concat(bot);
  }

  var grainPattern = null;
  function grain(ctx) {
    if (!grainPattern) {
      var c = D.createElement("canvas"); c.width = c.height = 160;
      var g = c.getContext("2d"), img = g.createImageData(160, 160), r = rng(7);
      for (var i = 0; i < img.data.length; i += 4) {
        var v = r(), a = v > 0.55 ? Math.pow((v - 0.55) / 0.45, 2) * 255 : 0;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = 0; img.data[i + 3] = a;
      }
      g.putImageData(img, 0, 0);
      grainPattern = c;
    }
    return ctx.createPattern(grainPattern, "repeat");
  }

  /* Paint one stroke's pigment into its own offscreen canvas. */
  function paintStroke(st, place, dpr, color) {
    var r = rng(st.seed);
    var raw = SHAPES[st.shape](st, place.U);
    var rot = st.rot || 0, cs = Math.cos(rot), sn = Math.sin(rot);
    var pts = raw.map(function (p) { return [p[0] * cs - p[1] * sn, p[0] * sn + p[1] * cs, 0.5 + r()]; });
    var base = deform(pts, st.shape === "stem" || st.shape === "ribbon" ? 1 : 2, st.rough == null ? 0.14 : st.rough, r);

    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    base.forEach(function (p) {
      if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
      if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
    });
    var pad = st.pad != null ? st.pad : (0.14 + (st.spread == null ? 0.13 : st.spread) * 1.3) * Math.max(maxX - minX, maxY - minY) + 8;
    var w = maxX - minX + pad * 2, h = maxY - minY + pad * 2;
    var c = D.createElement("canvas");
    c.width = Math.max(1, Math.ceil(w * dpr)); c.height = Math.max(1, Math.ceil(h * dpr));
    var g = c.getContext("2d");
    var tx = (pad - minX), ty = (pad - minY);
    g.setTransform(dpr, 0, 0, dpr, tx * dpr, ty * dpr);
    g.fillStyle = color;

    var layers = st.layers || 30, alpha = st.alpha || 0.055, spread = st.spread == null ? 0.13 : st.spread;
    for (var i = 0; i < layers; i++) {
      g.globalAlpha = alpha * (0.7 + r() * 0.6);
      tracePoly(g, deform(base, 3, spread, r));
      g.fill();
    }
    /* mottling: pigment settles unevenly, leaving lighter blooms inside the shape */
    if (st.mottle !== 0) {
      g.globalCompositeOperation = "destination-out";
      var span = Math.max(maxX - minX, maxY - minY);
      for (var m = 0; m < 7; m++) {
        var mx = minX + r() * (maxX - minX), my = minY + r() * (maxY - minY), mr0 = span * (0.12 + r() * 0.25);
        var mg = g.createRadialGradient(mx, my, 0, mx, my, mr0);
        mg.addColorStop(0, "rgba(0,0,0," + (0.18 + r() * 0.2) * (st.mottle || 1) + ")"); mg.addColorStop(1, "rgba(0,0,0,0)");
        g.globalAlpha = 1; g.fillStyle = mg; g.fillRect(mx - mr0, my - mr0, mr0 * 2, mr0 * 2);
      }
      g.globalCompositeOperation = "source-over"; g.fillStyle = color;
    }
    /* the wet edge: pigment pools where the water stopped */
    if (st.edge !== 0) {
      g.strokeStyle = color; g.lineJoin = "round";
      for (var e = 0; e < 3; e++) {
        g.globalAlpha = (st.edge || 0.14) * (e ? 0.6 : 1); g.lineWidth = e ? 2.4 : 1.1;
        tracePoly(g, deform(base, 2, 0.05, r));
        g.stroke();
      }
    }
    /* granulation: the paper's tooth shows through */
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = "destination-out";
    g.globalAlpha = st.grain == null ? 0.3 : st.grain;
    g.fillStyle = grain(g);
    g.fillRect(0, 0, c.width, c.height);

    /* the spreading mask: a rough circle, never dipping below 0.9 */
    var mr = rng(st.seed * 7 + 3), ring = [];
    for (var k = 0; k < 12; k++) {
      var a = (k / 12) * Math.PI * 2;
      ring.push([Math.cos(a), Math.sin(a), 0.6 + mr()]);
    }
    var mask = deform(ring, 4, 0.2, mr).map(function (p) {
      var d = Math.sqrt(p[0] * p[0] + p[1] * p[1]) || 1, k2 = Math.max(0.9, d) / d;
      return [p[0] * k2, p[1] * k2];
    });

    var cxp = place.x(st.x), cyp = place.y(st.y);
    var o = st.o || [st.x, st.y];
    var ox = place.x(o[0]) - cxp + tx, oy = place.y(o[1]) - cyp + ty;
    var maxR = 0;
    [[0, 0], [w, 0], [0, h], [w, h]].forEach(function (q) {
      maxR = Math.max(maxR, Math.sqrt((q[0] - ox) * (q[0] - ox) + (q[1] - oy) * (q[1] - oy)));
    });
    return {
      st: st, c: c, x: cxp - tx, y: cyp - ty, w: w, h: h, ox: ox, oy: oy, maxR: maxR,
      mask: mask, color: color, dpr: dpr, tmp: null, phase: r() * Math.PI * 2
    };
  }

  function drawStroke(ctx, b, p, alpha, wet, breath) {
    if (p <= 0 || alpha <= 0.002) return;
    ctx.globalCompositeOperation = b.st.mode === "lift" ? "destination-out" : "source-over";
    ctx.globalAlpha = alpha;
    if (p >= 1) {
      var k = breath || 1, ccx = b.x + b.ox, ccy = b.y + b.oy;
      ctx.drawImage(b.c, ccx - (ccx - b.x) * k, ccy - (ccy - b.y) * k, b.w * k, b.h * k);
      return;
    }
    if (!b.tmp) { b.tmp = D.createElement("canvas"); b.tmp.width = b.c.width; b.tmp.height = b.c.height; }
    var t = b.tmp.getContext("2d"), dpr = b.dpr, R = b.maxR * 1.2 * easeOut(p);
    t.setTransform(1, 0, 0, 1, 0, 0);
    t.globalCompositeOperation = "source-over"; t.globalAlpha = 1;
    t.clearRect(0, 0, b.tmp.width, b.tmp.height);
    t.setTransform(dpr, 0, 0, dpr, 0, 0);
    var grad = t.createRadialGradient(b.ox, b.oy, 0, b.ox, b.oy, R);
    grad.addColorStop(0, "rgba(0,0,0,1)"); grad.addColorStop(0.86, "rgba(0,0,0,1)"); grad.addColorStop(1, "rgba(0,0,0,0)");
    t.fillStyle = grad;
    tracePoly(t, b.mask, R, b.ox, b.oy); t.fill();
    t.globalCompositeOperation = "source-in";
    t.setTransform(1, 0, 0, 1, 0, 0);
    t.drawImage(b.c, 0, 0);
    if (wet > 0 && b.st.mode !== "lift") {
      /* a darker bead of pigment rides the spreading front while it is wet */
      t.globalCompositeOperation = "source-atop";
      t.setTransform(dpr, 0, 0, dpr, 0, 0);
      t.globalAlpha = 0.22 * wet; t.strokeStyle = b.color; t.lineWidth = 3;
      tracePoly(t, b.mask, R * 0.84, b.ox, b.oy); t.stroke();
    }
    ctx.drawImage(b.tmp, b.x, b.y, b.w, b.h);
  }

  /* ---------- Compositions ---------- */
  function range(n, f) { var a = []; for (var i = 0; i < n; i++) a.push(f(i)); return a; }

  function flowerStrokes(r, c, t0, span, fade) {
    var out = [];
    range(5, function (k) {
      var a = -Math.PI / 2 + (k * 2 * Math.PI) / 5 + (r() - 0.5) * 0.2;
      out.push({ shape: "petal", color: "lilac", x: c[0], y: c[1], rot: a, len: 0.26 + r() * 0.03, w: 0.19, layers: 28, alpha: 0.06, start: t0 + k * 0.05 * span, dur: 0.42 * span, fade: fade });
    });
    range(5, function (k) {
      var a = -Math.PI / 2 + (k * 2 * Math.PI) / 5 + 0.1;
      out.push({ shape: "petal", color: "clay", x: c[0], y: c[1], rot: a, len: 0.1, w: 0.08, layers: 16, alpha: 0.045, edge: 0, start: t0 + 0.3 * span, dur: 0.3 * span, fade: fade });
    });
    range(8, function (k) {
      var a = (k / 8) * Math.PI * 2 + r() * 0.4, d = 0.035 + r() * 0.03;
      out.push({ shape: "circle", color: "ochre", x: c[0] + Math.cos(a) * d, y: c[1] + Math.sin(a) * d, rx: 0.011, layers: 8, alpha: 0.22, edge: 0, grain: 0.15, start: t0 + (0.55 + k * 0.02) * span, dur: 0.12 * span, fade: fade });
    });
    return out;
  }
  function berryStrokes(r, c, s, t0, span) {
    return [
      { shape: "berry", color: "goji", x: c[0], y: c[1], rx: 0.15 * s, ry: 0.25 * s, o: [c[0], c[1] - 0.22 * s], layers: 30, alpha: 0.05, rough: 0.12, start: t0, dur: 0.5 * span },
      { shape: "berry", color: "deep-red", x: c[0] + 0.035 * s, y: c[1] + 0.04 * s, rx: 0.1 * s, ry: 0.19 * s, o: [c[0] + 0.05 * s, c[1] + 0.14 * s], layers: 24, alpha: 0.045, start: t0 + 0.22 * span, dur: 0.45 * span },
      { shape: "berry", color: "goji", x: c[0] - 0.03 * s, y: c[1] - 0.02 * s, rx: 0.08 * s, ry: 0.15 * s, layers: 16, alpha: 0.035, edge: 0, start: t0 + 0.35 * span, dur: 0.4 * span },
      { shape: "berry", mode: "lift", color: "goji", x: c[0] - 0.055 * s, y: c[1] - 0.09 * s, rot: -0.25, rx: 0.026 * s, ry: 0.075 * s, layers: 14, alpha: 0.6, edge: 0, grain: 0, start: t0 + 0.68 * span, dur: 0.3 * span },
      { shape: "leaf", color: "sage", x: c[0], y: c[1] - 0.245 * s, rot: 0.55, len: 0.1 * s, w: 0.042 * s, layers: 18, alpha: 0.08, start: t0 + 0.55 * span, dur: 0.25 * span },
      { shape: "leaf", color: "sage", x: c[0], y: c[1] - 0.245 * s, rot: Math.PI - 0.55, len: 0.1 * s, w: 0.042 * s, layers: 18, alpha: 0.08, start: t0 + 0.58 * span, dur: 0.25 * span },
      { shape: "leaf", color: "sage", x: c[0], y: c[1] - 0.25 * s, rot: 1.3, len: 0.075 * s, w: 0.034 * s, layers: 16, alpha: 0.08, start: t0 + 0.62 * span, dur: 0.25 * span },
      { shape: "leaf", color: "sage", x: c[0], y: c[1] - 0.25 * s, rot: Math.PI - 1.3, len: 0.075 * s, w: 0.034 * s, layers: 16, alpha: 0.08, start: t0 + 0.64 * span, dur: 0.25 * span }
    ];
  }
  function stem(p0, p1, p2, w, start, dur) {
    return { shape: "stem", color: "sage", p0: p0, p1: p1, p2: p2, x: p1[0], y: p1[1], o: p0, w: w, layers: 20, alpha: 0.07, rough: 0.05, spread: 0.12, start: start, dur: dur };
  }

  var PRESETS = {
    /* bud to flower to ripe berry: "care that grows with you" */
    ripen: function (r) {
      var c = [0.5, 0.45];
      return { fit: "contain", dur: 6400, strokes: [stem([0.58, 0.0], [0.45, 0.14], [0.5, 0.34], 0.02, 0, 0.16)]
        .concat(flowerStrokes(r, c, 0.06, 0.45, [0.5, 0.68]))
        .concat(berryStrokes(r, [0.5, 0.62], 1, 0.52, 0.48)) };
    },
    berry: function (r) {
      return { fit: "contain", dur: 3400, strokes: [stem([0.56, 0.0], [0.46, 0.18], [0.5, 0.37], 0.022, 0, 0.3)].concat(berryStrokes(r, [0.5, 0.62], 1, 0.12, 0.88)) };
    },
    flower: function (r) {
      return { fit: "contain", dur: 3400, strokes: [stem([0.5, 1.0], [0.56, 0.78], [0.5, 0.52], 0.022, 0, 0.3)].concat(flowerStrokes(r, [0.5, 0.45], 0.12, 0.88, null)) };
    },
    /* a hanging sprig: divider and footer ornament */
    sprig: function (r) {
      var s = [stem([0.04, 0.26], [0.42, -0.02], [0.96, 0.34], 0.011, 0, 0.35)];
      s.push({ shape: "leaf", color: "sage", x: 0.24, y: 0.17, rot: -2.5, len: 0.16, w: 0.06, layers: 18, alpha: 0.07, start: 0.2, dur: 0.3 });
      s.push({ shape: "leaf", color: "sage", x: 0.65, y: 0.18, rot: -0.6, len: 0.15, w: 0.055, layers: 18, alpha: 0.07, start: 0.3, dur: 0.3 });
      [[0.32, 0.13, 0.62], [0.52, 0.13, 0.7], [0.74, 0.17, 0.6]].forEach(function (b, i) {
        s.push(stem([b[0], b[1]], [b[0] + 0.01, b[1] + 0.06], [b[0], b[1] + 0.13], 0.01, 0.25 + i * 0.08, 0.2));
        s = s.concat(berryStrokes(r, [b[0], b[1] + 0.13 + 0.25 * b[2] * 0.85], b[2] * 0.85, 0.35 + i * 0.1, 0.55).map(function (q, j) { q.seed = 50 + i * 10 + j; return q; }));
      });
      return { fit: "contain", dur: 3600, strokes: s };
    },
    /* nodes for GrowthPath: no stem of their own, they sit on the vine */
    "node-bud": function (r) {
      var s = [];
      [[-0.32, 0], [0.3, 0.08], [0, 0.16]].forEach(function (q, k) {
        s.push({ shape: "petal", color: "lilac", x: 0.5, y: 0.66, rot: -Math.PI / 2 + q[0] * 0.55, len: 0.36 - q[1] * 0.3, w: 0.15, layers: 26, alpha: 0.06, start: 0.05 + k * 0.12, dur: 0.5 });
      });
      s.push({ shape: "petal", color: "clay", x: 0.5, y: 0.66, rot: -Math.PI / 2, len: 0.16, w: 0.08, layers: 14, alpha: 0.05, edge: 0, start: 0.4, dur: 0.4 });
      [-2.2, -0.95].forEach(function (a, k) {
        s.push({ shape: "leaf", color: "sage", x: 0.5, y: 0.68, rot: a, len: 0.15, w: 0.06, layers: 18, alpha: 0.08, start: 0.5 + k * 0.08, dur: 0.35 });
      });
      return { fit: "contain", dur: 2600, strokes: s };
    },
    "node-flower": function (r) { return { fit: "contain", dur: 3000, strokes: flowerStrokes(r, [0.5, 0.5], 0, 1, null) }; },
    "node-berry": function (r) { return { fit: "contain", dur: 3000, strokes: berryStrokes(r, [0.5, 0.56], 1, 0, 1) }; },
    /* ambient washes behind content */
    dawn: function (r) {
      var s = [
        { shape: "circle", color: "blush", x: 0.06, y: 0.12, rx: 0.4, ry: 0.32, layers: 26, alpha: 0.05, rough: 0.26, spread: 0.26, grain: 0.22, start: 0, dur: 0.75 },
        { shape: "circle", color: "clay", x: 0.96, y: 0.28, rx: 0.22, ry: 0.19, layers: 24, alpha: 0.035, rough: 0.26, spread: 0.26, start: 0.12, dur: 0.75 },
        { shape: "circle", color: "lilac", x: 0.8, y: 0.98, rx: 0.28, ry: 0.17, layers: 24, alpha: 0.03, rough: 0.26, spread: 0.26, start: 0.2, dur: 0.75 },
        { shape: "circle", color: "blush", x: 0.36, y: 1.02, rx: 0.26, ry: 0.12, layers: 22, alpha: 0.04, rough: 0.26, spread: 0.26, start: 0.25, dur: 0.75 }
      ];
      range(6, function (k) {
        s.push({ shape: "circle", color: k % 3 ? "clay" : "goji", x: 0.86 + r() * 0.1, y: 0.42 + r() * 0.16, rx: 0.002 + r() * 0.005, layers: 6, alpha: 0.18, edge: 0, grain: 0.1, start: 0.55 + k * 0.03, dur: 0.1 });
      });
      return { fit: "cover", dur: 3200, breathe: true, strokes: s };
    },
    dusk: function () {
      return { fit: "cover", dur: 3200, breathe: true, strokes: [
        { shape: "circle", color: "deep-red", x: 0.92, y: 0.08, rx: 0.36, ry: 0.3, layers: 26, alpha: 0.07, rough: 0.26, spread: 0.26, start: 0, dur: 0.8 },
        { shape: "circle", color: "goji", x: 0.04, y: 0.98, rx: 0.26, ry: 0.2, layers: 24, alpha: 0.035, rough: 0.26, spread: 0.26, start: 0.15, dur: 0.8 },
        { shape: "circle", color: "goji", x: 0.72, y: 1.0, rx: 0.16, ry: 0.1, layers: 20, alpha: 0.05, rough: 0.26, spread: 0.26, start: 0.25, dur: 0.75 }
      ] };
    }
  };

  /* ---------- A painting: one canvas, one composition ---------- */
  function paint(el, opts) {
    opts = opts || {};
    var seed = opts.seed == null ? 3 : opts.seed;
    var comp = (PRESETS[opts.preset] || PRESETS.ripen)(rng(seed * 31 + 1));
    comp.strokes.forEach(function (s, i) { if (s.seed == null) s.seed = seed * 101 + i * 13 + 1; });
    var canvas = D.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    el.appendChild(canvas);
    var ctx = canvas.getContext("2d");
    var blots = [], w = 0, h = 0, dpr = 1, raf = 0, t0 = 0, state = "idle", visible = true, lastDraw = 0;
    var breathe = opts.breathe !== false && (comp.breathe || opts.breathe === true);
    var dur = comp.dur * (opts.speed ? 1 / opts.speed : 1);

    function build() {
      w = el.clientWidth; h = el.clientHeight;
      if (!w || !h) return false;
      dpr = opts.dpr || Math.min(W.devicePixelRatio || 1, comp.fit === "cover" ? 1 : 2);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      var S = Math.min(w, h), ox = (w - S) / 2, oy = (h - S) / 2;
      var place = comp.fit === "cover"
        ? { U: Math.max(w, h), x: function (v) { return v * w; }, y: function (v) { return v * h; } }
        : { U: S, x: function (v) { return ox + v * S; }, y: function (v) { return oy + v * S; } };
      blots = comp.strokes.map(function (st) { return paintStroke(st, place, dpr, tokenColor(el, st.color)); });
      return true;
    }
    function frame(T, now) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var f = T / dur;
      for (var i = 0; i < blots.length; i++) {
        var b = blots[i], st = b.st;
        var p = clamp01((f - st.start) / st.dur);
        var alpha = 1 - 0.1 * clamp01((f - st.start - st.dur) / 0.2); /* watercolour dries lighter */
        if (st.mode === "lift") alpha = st.alpha * clamp01(p * 1.4);
        if (st.fade) alpha *= 1 - clamp01((f - st.fade[0]) / (st.fade[1] - st.fade[0]));
        var breath = (breathe && f >= 1) ? 1 + 0.012 * Math.sin((now / 9000) * Math.PI * 2 + b.phase) : 1;
        drawStroke(ctx, b, p, alpha, 1 - p, breath);
      }
    }
    function tick(now) {
      raf = 0;
      if (!t0) t0 = now;
      var T = now - t0;
      if (state === "playing") {
        frame(Math.min(T, dur), now);
        if (T >= dur) {
          if (opts.loop) { state = "holding"; t0 = now; }
          else state = breathe ? "breathing" : "done";
        }
      } else if (state === "holding") {
        if (T > 3200) {
          var k = clamp01((T - 3200) / 900);
          canvas.style.opacity = String(1 - k);
          if (k >= 1) { canvas.style.opacity = "1"; state = "playing"; t0 = now; }
        }
      } else if (state === "breathing") {
        if (now - lastDraw > 33) { frame(dur, now); lastDraw = now; }
      }
      if ((state === "playing" || state === "holding" || state === "breathing") && visible && !D.hidden) raf = requestAnimationFrame(tick);
    }
    function kick() { if (!raf) raf = requestAnimationFrame(tick); }
    function finish() { if (!blots.length && !build()) return; frame(dur, performance.now()); state = breathe && !reducedMotion() ? "breathing" : "done"; }

    var stopVisible = function () {}, io = null, ro = null, mo = null, rt = 0, pending = false;
    function start() {
      /* no size yet (stylesheet still loading): wait for the ResizeObserver */
      if (!build()) { pending = true; return; }
      pending = false;
      if (reducedMotion()) { finish(); return; }
      if (opts.manual) return; /* waits for replay() */
      setTimeout(function () { state = "playing"; t0 = 0; kick(); }, opts.delay || 0);
    }
    if (opts.immediate) start(); else stopVisible = onVisible(el, start, 0.25);

    if ("IntersectionObserver" in W) {
      io = new IntersectionObserver(function (e) { visible = e[0].isIntersecting; if (visible && state !== "idle" && state !== "done") kick(); });
      io.observe(el);
    }
    if ("ResizeObserver" in W) {
      ro = new ResizeObserver(function () {
        clearTimeout(rt);
        rt = setTimeout(function () {
          if (pending) { start(); return; }
          if (Math.abs(el.clientWidth - w) < 2 && Math.abs(el.clientHeight - h) < 2) return;
          if (state === "idle") return;
          build();
          if (state === "done" || state === "breathing") frame(dur, performance.now());
        }, 160);
      });
      ro.observe(el);
    }
    /* repaint in the new theme's pigments when the theme flips */
    mo = new MutationObserver(function () { if (state !== "idle") { build(); if (state === "done" || state === "breathing") frame(dur, performance.now()); } });
    mo.observe(D.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    D.addEventListener("visibilitychange", kick);

    return {
      duration: dur, canvas: canvas,
      replay: function () {
        if (reducedMotion()) { finish(); return; }
        canvas.style.opacity = "1"; if (!blots.length && !build()) return;
        setTimeout(function () { state = "playing"; t0 = 0; kick(); }, opts.manual ? (opts.delay || 0) : 0);
      },
      finish: finish,
      destroy: function () {
        cancelAnimationFrame(raf); stopVisible(); clearTimeout(rt);
        if (io) io.disconnect(); if (ro) ro.disconnect(); if (mo) mo.disconnect();
        D.removeEventListener("visibilitychange", kick);
        if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      }
    };
  }

  /* ---------- Photo reveal: the image is painted in through wet washes ---------- */
  function veil(frameEl, opts) {
    opts = opts || {};
    if (reducedMotion()) return function () {};
    var img = frameEl.querySelector("img"), canvas = null, raf = 0, dead = false;
    /* hidden until it scrolls in, so no first-paint flash of the bare photo */
    if (img) { img.style.opacity = "0"; img.style.transform = "scale(1.06)"; }
    function run() {
      if (dead) return;
      var w = frameEl.clientWidth, h = frameEl.clientHeight;
      if (!w || !h) { if (img) img.style.opacity = ""; return; }
      var dpr = Math.min(W.devicePixelRatio || 1, 1.5), r = rng(opts.seed || 11), t0 = 0, dur = opts.dur || 1900;
      canvas = D.createElement("canvas");
      canvas.className = "gj-veil"; canvas.setAttribute("aria-hidden", "true");
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      frameEl.appendChild(canvas);
      var ctx = canvas.getContext("2d"), fill = tokenColor(frameEl, "blush");
      var seeds = [[0.28, 0.72, 0], [0.74, 0.3, 0.14], [0.55, 0.55, 0.26]].map(function (s) {
        var ring = range(10, function (k) { var a = (k / 10) * Math.PI * 2; return [Math.cos(a), Math.sin(a), 0.6 + r()]; });
        var m = deform(ring, 4, 0.22, r).map(function (p) { var d = Math.sqrt(p[0] * p[0] + p[1] * p[1]) || 1, k = Math.max(0.85, d) / d; return [p[0] * k, p[1] * k]; });
        return { x: s[0] * w, y: s[1] * h, start: s[2], mask: m };
      });
      var reach = Math.sqrt(w * w + h * h) * 1.05;
      function draw(f) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
        ctx.fillStyle = fill; ctx.fillRect(0, 0, w, h);
        ctx.globalCompositeOperation = "destination-out";
        seeds.forEach(function (s) {
          var p = clamp01((f - s.start) / 0.74); if (p <= 0) return;
          var R = reach * easeOut(p);
          var g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, R);
          g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(0.8, "rgba(0,0,0,1)"); g.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = g; tracePoly(ctx, s.mask, R, s.x, s.y); ctx.fill();
        });
      }
      draw(0);
      if (img) {
        img.style.opacity = "";
        img.style.transition = "transform 2400ms cubic-bezier(.22,1,.36,1)";
        requestAnimationFrame(function () { img.style.transform = "scale(1)"; });
      }
      function tick(now) {
        if (!t0) t0 = now;
        var f = (now - t0) / dur;
        draw(f);
        if (f < 1) raf = requestAnimationFrame(tick);
        else if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      }
      raf = requestAnimationFrame(tick);
    }
    var stop = onVisible(frameEl, function () { setTimeout(run, opts.delay || 0); }, 0.3);
    return function () {
      dead = true; stop(); cancelAnimationFrame(raf);
      if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
      if (img) { img.style.opacity = ""; img.style.transform = ""; }
    };
  }

  /* ---------- Growth vine: a stem that grows down a page as the reader scrolls ----------
     el: a positioned box spanning the steps; nodes: [{ y, preset, size }] in px from el's top.
     Growth only moves forward, follows the scroll with a soft lag, and blooms each node
     as the tip reaches it. Never scroll-jacks: it only reads the scroll position. */
  function grow(el, opts) {
    opts = opts || {};
    var canvas = D.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%";
    el.appendChild(canvas);
    var ctx = canvas.getContext("2d"), stem = null, w = 0, h = 0, dpr = 1, cur = 0, target = 0, raf = 0;
    var nodes = [], seed = opts.seed || 13, stemW = 0, reduced = reducedMotion(), tipFade = 0;
    function vx(y) { return w / 2 + Math.sin(y / 190 + 0.8) * w * 0.1 + Math.sin(y / 61) * w * 0.025; }

    function build() {
      w = el.clientWidth; h = el.clientHeight;
      if (!w || !h) return false;
      dpr = Math.min(W.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      stemW = Math.max(4, Math.min(9, w * 0.05));
      var pts = [];
      for (var y = -4; y <= h + 4; y += 16) pts.push([vx(y), y]);
      var place = { U: 1, x: function (v) { return v; }, y: function (v) { return v; } };
      var sage = tokenColor(el, "sage");
      var strokes = [{ shape: "ribbon", pts: pts, x: 0, y: 0, w: stemW, taper: 0.3, pad: 24, layers: 16, alpha: 0.1, rough: 0.035, spread: 0.05, edge: 0.12, mottle: 0.4, seed: seed }];
      /* leaves sprout between nodes, alternating sides */
      var ys = (opts.nodes || []).map(function (n) { return n.y; }).concat([h]);
      var prev = 0, side = 1, r = rng(seed + 5);
      ys.forEach(function (ny) {
        for (var ly = prev + 70; ly < ny - 70; ly += 150 + r() * 60) {
          strokes.push({ shape: "leaf", x: vx(ly), y: ly, rot: -Math.PI / 2 + side * (0.95 + r() * 0.35), len: w * (0.26 + r() * 0.08), w: w * 0.1, pad: 14, layers: 16, alpha: 0.08, seed: seed + Math.round(ly) });
          side = -side;
        }
        prev = ny;
      });
      stem = D.createElement("canvas"); stem.width = canvas.width; stem.height = canvas.height;
      var sc = stem.getContext("2d");
      strokes.forEach(function (st) {
        var b = paintStroke(st, place, dpr, sage);
        sc.drawImage(b.c, Math.round(b.x * dpr), Math.round(b.y * dpr));
      });
      /* nodes */
      nodes.forEach(function (n) { n.p.destroy(); if (n.el.parentNode) n.el.parentNode.removeChild(n.el); });
      nodes = (opts.nodes || []).map(function (n, i) {
        var size = n.size || w * 1.1, d = D.createElement("div");
        d.className = "gj-wc gj-wc--multiply";
        d.style.cssText = "position:absolute;width:" + size + "px;height:" + size + "px;left:" + (vx(n.y) - size / 2) + "px;top:" + (n.y - size / 2) + "px";
        el.appendChild(d);
        var p = paint(d, { preset: n.preset || "node-flower", seed: seed + i * 7, manual: true, immediate: true, breathe: false });
        var fired = cur >= n.y;
        if (fired) p.finish();
        return { y: n.y, el: d, p: p, fired: fired };
      });
      return true;
    }
    function draw() {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!stem || cur <= 0) return;
      var band = 36, solid = Math.max(0, cur - band);
      if (solid > 0) ctx.drawImage(stem, 0, 0, canvas.width, solid * dpr, 0, 0, canvas.width, solid * dpr);
      /* the growing tip fades out, like pigment thinning at the end of a stroke */
      for (var k = 0; k < 9; k++) {
        var y0 = solid + (k * band) / 9, y1 = Math.min(h, solid + ((k + 1) * band) / 9);
        if (y0 >= h || y1 <= y0) break;
        ctx.globalAlpha = 1 - (k + 0.5) / 9;
        ctx.drawImage(stem, 0, y0 * dpr, canvas.width, (y1 - y0) * dpr, 0, y0 * dpr, canvas.width, (y1 - y0) * dpr);
      }
      ctx.globalAlpha = 1;
      if (tipFade > 0.01 && cur < h) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.globalAlpha = 0.28 * tipFade; ctx.fillStyle = tokenColor(el, "sage");
        ctx.beginPath(); ctx.arc(vx(cur - band * 0.6), cur - band * 0.6, stemW * 0.75, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
      }
    }
    /* the nearest scrolling ancestor, else the window */
    var scroller = (function () {
      for (var n = el.parentElement; n && n !== D.body && n !== D.documentElement; n = n.parentElement) {
        var oy = getComputedStyle(n).overflowY;
        if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 1) return n;
      }
      return null;
    })();
    var scrollTarget = scroller || W;
    function measure() {
      var rect = el.getBoundingClientRect(), vh = W.innerHeight || 800;
      if (scroller) { var sr = scroller.getBoundingClientRect(); rect = { top: rect.top - sr.top }; vh = sr.height; }
      target = Math.max(target, Math.min(h, Math.max(0, vh * 0.62 - rect.top)));
    }
    function tick() {
      raf = 0;
      var d = target - cur;
      cur += Math.abs(d) < 0.6 ? d : Math.max(-40, Math.min(40, d * 0.085));
      tipFade += ((Math.abs(d) > 1 ? 1 : 0) - tipFade) * 0.08;
      nodes.forEach(function (n) { if (!n.fired && cur >= n.y - 6) { n.fired = true; n.p.replay(); } });
      draw();
      if (Math.abs(target - cur) > 0.3 || tipFade > 0.01) raf = requestAnimationFrame(tick);
    }
    function onScroll() { measure(); if (!raf) raf = requestAnimationFrame(tick); }

    var ro = null, rt = 0;
    function init() {
      if (!build()) return false;
      if (reduced) { cur = target = h; nodes.forEach(function (n) { n.fired = true; n.p.finish(); }); draw(); return true; }
      scrollTarget.addEventListener("scroll", onScroll, { passive: true });
      W.addEventListener("resize", onScroll);
      onScroll();
      return true;
    }
    var ready = init();
    if ("ResizeObserver" in W) {
      ro = new ResizeObserver(function () {
        clearTimeout(rt);
        rt = setTimeout(function () {
          if (!ready) { ready = init(); return; }
          if (Math.abs(el.clientWidth - w) < 2 && Math.abs(el.clientHeight - h) < 2) return;
          build(); if (reduced) cur = target = h; draw(); onScroll();
        }, 160);
      });
      ro.observe(el);
    }
    return {
      /* call when the steps move (fonts load, content changes) */
      layout: function (newNodes) { opts.nodes = newNodes; if (!ready) { ready = init(); return; } if (build()) { if (reduced) cur = target = h; draw(); onScroll(); } },
      destroy: function () {
        cancelAnimationFrame(raf); clearTimeout(rt); if (ro) ro.disconnect();
        scrollTarget.removeEventListener("scroll", onScroll); W.removeEventListener("resize", onScroll);
        nodes.forEach(function (n) { n.p.destroy(); if (n.el.parentNode) n.el.parentNode.removeChild(n.el); });
        if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      }
    };
  }

  /* ---------- Breathing wash: pigment spreads as you breathe in, draws back as you breathe out ---------- */
  function breathe(el, opts) {
    opts = opts || {};
    var inhale = opts.inhale || 4000, hold = opts.hold || 0, exhale = opts.exhale || 6000, cycles = opts.cycles || 6;
    var canvas = D.createElement("canvas"); canvas.setAttribute("aria-hidden", "true");
    el.appendChild(canvas);
    var ctx = canvas.getContext("2d"), blots = [], w = 0, h = 0, dpr = 1, raf = 0, running = false, t0 = 0, elapsed = 0, phase = "ready", cycle = 0;
    var REST = 0.58, reduced = reducedMotion();
    function build() {
      w = el.clientWidth; h = el.clientHeight;
      if (!w || !h) return false;
      dpr = opts.dpr || Math.min(W.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      var S = Math.min(w, h), ox = (w - S) / 2, oy = (h - S) / 2;
      var place = { U: S, x: function (v) { return ox + v * S; }, y: function (v) { return oy + v * S; } };
      var seed = opts.seed || 21;
      blots = [
        { shape: "circle", color: "blush", x: 0.5, y: 0.5, rx: 0.4, ry: 0.38, layers: 28, alpha: 0.06, rough: 0.2, spread: 0.18, lag: 0.12 },
        { shape: "circle", color: "clay", x: 0.5, y: 0.5, rx: 0.27, ry: 0.26, layers: 24, alpha: 0.05, rough: 0.2, spread: 0.18, lag: 0.06 },
        { shape: "circle", color: "goji", x: 0.5, y: 0.5, rx: 0.13, ry: 0.13, layers: 20, alpha: 0.045, rough: 0.2, spread: 0.18, lag: 0 }
      ].map(function (st, i) { st.seed = seed + i * 17; var b = paintStroke(st, place, dpr, tokenColor(el, st.color)); b.lag = st.lag; return b; });
      return true;
    }
    function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
    /* level 0..1 of the breath at time t within a cycle */
    function level(t) {
      var c = inhale + hold + exhale; t = ((t % c) + c) % c;
      if (t < inhale) return ease(t / inhale);
      if (t < inhale + hold) return 1;
      return 1 - ease((t - inhale - hold) / exhale);
    }
    function phaseAt(t) {
      var c = inhale + hold + exhale, u = t % c;
      return u < inhale ? "in" : u < inhale + hold ? "hold" : "out";
    }
    function draw(t) {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      blots.forEach(function (b) {
        var L = t == null ? 0 : Math.max(0, level(t - b.lag * inhale) * (t < b.lag * inhale ? 0 : 1));
        if (reduced) drawStroke(ctx, b, 1, 0.55 + 0.45 * L, 0);
        /* the dried wash itself swells and settles, so its ragged edges hold at every size */
        else drawStroke(ctx, b, 1, 0.78 + 0.22 * L, 0, REST + (1 - REST) * L);
      });
    }
    function tick(now) {
      raf = 0;
      if (!running) return;
      if (!t0) t0 = now - elapsed;
      elapsed = now - t0;
      var c = inhale + hold + exhale, ci = Math.floor(elapsed / c);
      if (ci >= cycles) { running = false; elapsed = 0; t0 = 0; phase = "done"; draw(null); if (opts.onPhase) opts.onPhase("done", cycles); return; }
      var ph = phaseAt(elapsed);
      if (ph !== phase || ci !== cycle) { phase = ph; cycle = ci; if (opts.onPhase) opts.onPhase(ph, ci); }
      draw(elapsed);
      raf = requestAnimationFrame(tick);
    }
    var ro = null;
    if (build()) draw(null);
    if ("ResizeObserver" in W) {
      ro = new ResizeObserver(function () { if (Math.abs(el.clientWidth - w) > 1 || Math.abs(el.clientHeight - h) > 1) { if (build()) draw(running ? elapsed : null); } });
      ro.observe(el);
    }
    return {
      canvas: canvas, cycleMs: inhale + hold + exhale,
      start: function () { if (!blots.length && !build()) return; if (phase === "done") { phase = "ready"; cycle = 0; } running = true; t0 = 0; if (!raf) raf = requestAnimationFrame(tick); },
      pause: function () { running = false; t0 = 0; cancelAnimationFrame(raf); raf = 0; if (opts.onPhase) opts.onPhase("paused", cycle); },
      reset: function () { running = false; t0 = 0; elapsed = 0; cycle = 0; phase = "ready"; cancelAnimationFrame(raf); raf = 0; draw(null); },
      destroy: function () { running = false; cancelAnimationFrame(raf); if (ro) ro.disconnect(); if (canvas.parentNode) canvas.parentNode.removeChild(canvas); }
    };
  }

  /* ---------- Non-React pages (Astro): <div data-gj-bloom="ripen">, data-gj-wash, data-gj-veil, data-gj-reveal, .gj-mark ---------- */
  function enhance(root) {
    root = root || D;
    root.querySelectorAll("[data-gj-bloom]").forEach(function (el) { paint(el, { preset: el.getAttribute("data-gj-bloom") || "ripen", seed: +el.getAttribute("data-seed") || 3, loop: el.hasAttribute("data-loop"), delay: +el.getAttribute("data-delay") || 0 }); });
    root.querySelectorAll("[data-gj-wash]").forEach(function (el) { paint(el, { preset: el.getAttribute("data-gj-wash") || "dawn", seed: +el.getAttribute("data-seed") || 5 }); });
    root.querySelectorAll("[data-gj-veil]").forEach(function (el) { veil(el); });
    root.querySelectorAll("[data-gj-reveal], .gj-reveal, .gj-mark").forEach(function (el) { onVisible(el, function () { el.classList.add("is-in"); }, 0.15); });
  }

  /* ================================================================
     React components
     ================================================================ */
  var api = { assets: assets, paint: paint, veil: veil, grow: grow, breathe: breathe, enhance: enhance, presets: Object.keys(PRESETS) };
  var React = W.React;
  if (React) {
    var h = React.createElement, useRef = React.useRef, useEffect = React.useEffect, useState = React.useState;
    var ICONS = {
      whatsapp: ["M3 21l1.65 -3.8a9 9 0 1 1 3.4 2.9l-5.05 .9", "M9 10a.5 .5 0 0 0 1 0v-1a.5 .5 0 0 0 -1 0v1a5 5 0 0 0 5 5h1a.5 .5 0 0 0 0 -1h-1a.5 .5 0 0 0 0 1"],
      arrow: ["M5 12l14 0", "M13 18l6 -6", "M13 6l6 6"],
      arrowUpRight: ["M17 7l-10 10", "M8 7l9 0l0 9"],
      calendar: ["M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12z", "M16 3v4", "M8 3v4", "M4 11h16"],
      menu: ["M4 8l16 0", "M4 16l16 0"]
    };
    var Icon = function (name, cls) {
      return h("svg", { key: name, className: cls, viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" },
        ICONS[name].map(function (d, i) { return h("path", { key: i, d: d }); }));
    };
    var omit = function (o, keys) { var r = {}; for (var k in o) if (keys.indexOf(k) < 0) r[k] = o[k]; return r; };

    var Button = function (p) {
      var v = p.variant || "primary", icon = p.icon;
      var cls = cx("gj-btn", "gj-btn--" + v, p.size === "sm" && "gj-btn--sm", p.className);
      var kids = [
        icon === "whatsapp" && Icon("whatsapp"),
        icon === "calendar" && Icon("calendar"),
        h("span", { key: "l" }, p.children),
        icon === "arrow" && Icon("arrow", "gj-btn__arrow"),
        icon === "arrowUpRight" && Icon("arrowUpRight", "gj-btn__arrow")
      ];
      var rest = omit(p, ["variant", "icon", "size", "className", "children"]);
      return p.href ? h("a", Object.assign(rest, { className: cls }), kids) : h("button", Object.assign({ type: "button" }, rest, { className: cls }), kids);
    };

    var Eyebrow = function (p) { return h("span", { className: cx("gj-eyebrow", p.className) }, p.children); };

    var markSeq = 0;
    var PaintedUnderline = function (p) {
      var ref = useRef(null), id = useRef("gjm" + ++markSeq + Math.floor(Math.random() * 1e4));
      useEffect(function () { return onVisible(ref.current, function (el) { el.classList.add("is-in"); }, 0.6); }, []);
      var f = "url(#" + id.current + ")";
      return h("span", { ref: ref, className: cx("gj-mark", p.className) }, p.children,
        h("svg", { className: "gj-mark__svg", viewBox: "0 0 200 20", preserveAspectRatio: "none", "aria-hidden": "true", focusable: "false", style: { transitionDelay: (p.delay || 300) + "ms" } },
          h("defs", null, h("filter", { id: id.current, x: "-5%", y: "-80%", width: "110%", height: "260%" },
            h("feTurbulence", { type: "fractalNoise", baseFrequency: "0.05 0.35", numOctaves: 2, seed: p.seed || 4 }),
            h("feDisplacementMap", { in: "SourceGraphic", scale: 5 }),
            h("feGaussianBlur", { stdDeviation: 0.35 }))),
          h("path", { className: "gj-mark__bleed", d: "M3 12.5 C 50 7.5, 120 15, 197 9", strokeWidth: 15, pathLength: 1, filter: f, style: { transitionDelay: (p.delay || 300) + "ms" } }),
          h("path", { className: "gj-mark__core", d: "M6 13 C 60 9.5, 130 14, 194 10.5", strokeWidth: 11, pathLength: 1, filter: f, style: { transitionDelay: (p.delay || 300) + 120 + "ms" } })));
    };

    var SectionHeading = function (p) {
      var size = p.size || "h2", Tag = "h" + (p.level || 2), title = p.title, hl = p.highlight, t = title;
      if (hl && typeof title === "string" && title.indexOf(hl) >= 0) {
        var i = title.indexOf(hl);
        t = [title.slice(0, i), h(PaintedUnderline, { key: "m" }, hl), title.slice(i + hl.length)];
      }
      return h("div", { className: cx("gj-heading", p.align === "center" && "gj-heading--center", p.className) },
        p.eyebrow && h(Eyebrow, null, p.eyebrow),
        h(Tag, { className: "gj-" + size }, t),
        p.lead && h("p", { className: "gj-lead" }, p.lead),
        p.children);
    };

    var BerryList = function (p) {
      return h("ul", { className: cx("gj-berries", p.size === "sm" && "gj-berries--sm", p.className) },
        (p.items || []).map(function (it, i) { return h("li", { key: i }, it); }));
    };

    var StatBlock = function (p) {
      return h("div", { className: cx("gj-stats", p.className) }, (p.items || []).map(function (s, i) {
        return h("div", { key: i, className: "gj-stat gj-reveal", style: { "--i": i }, ref: revealRef },
          h("span", { className: "gj-numeral" }, s.value),
          h("span", { className: "gj-stat__label" }, s.label),
          s.caption && h("span", { className: "gj-stat__caption" }, s.caption));
      }));
    };

    function revealRef(el) { if (el && !el.__gj) { el.__gj = 1; onVisible(el, function () { el.classList.add("is-in"); }, 0.15); } }

    var Reveal = function (p) {
      var Tag = p.as || "div";
      return h(Tag, Object.assign(omit(p, ["as", "i", "className", "children"]), { ref: revealRef, className: cx("gj-reveal", p.className), style: Object.assign({ "--i": p.i || 0 }, p.style) }), p.children);
    };

    var CareCard = function (p) {
      var Tag = p.href ? "a" : "div";
      return h(Tag, { href: p.href, className: cx("gj-card", p.className) },
        p.image && h("div", { className: "gj-card__media" }, h("img", { src: p.image, alt: p.alt || "", loading: "lazy" })),
        p.eyebrow && h(Eyebrow, null, p.eyebrow),
        h("h3", { className: "gj-h3" }, p.title),
        p.body && h("p", { className: "gj-small", style: { color: "var(--text-default)" } }, p.body),
        p.points && h(BerryList, { items: p.points, size: "sm" }),
        p.href && h("span", { className: "gj-card__more" }, p.more || "Learn more", Icon("arrowUpRight")));
    };

    var PaintedImage = function (p) {
      var ref = useRef(null);
      useEffect(function () { return p.reveal === false ? undefined : veil(ref.current, { seed: p.seed, delay: p.delay }); }, []);
      return h("div", { ref: ref, className: cx("gj-frame", "gj-frame--" + (p.frame || "petal"), p.flip && "gj-frame--flip", p.className), style: Object.assign({ aspectRatio: p.ratio || undefined }, p.style) },
        h("img", { src: p.src, alt: p.alt || "", style: { objectPosition: p.position || "50% 50%" } }));
    };

    var WatercolorBloom = function (p) {
      var ref = useRef(null);
      var labels = { ripen: "A watercolour goji flower opening and ripening into a red berry", berry: "A watercolour goji berry", flower: "A watercolour goji flower", sprig: "A watercolour sprig of goji berries" };
      useEffect(function () {
        var pt = paint(ref.current, { preset: p.preset || "ripen", seed: p.seed, loop: p.loop, delay: p.delay, immediate: p.immediate });
        return pt.destroy;
      }, [p.preset, p.seed, p.loop]);
      return h("div", { ref: ref, className: cx("gj-wc gj-wc--multiply gj-wc-bloom", p.className), style: Object.assign({ width: p.size }, p.style), role: p.decorative ? undefined : "img", "aria-hidden": p.decorative ? "true" : undefined, "aria-label": p.decorative ? undefined : p.label || labels[p.preset || "ripen"] });
    };

    var Wash = function (p) {
      var ref = useRef(null);
      useEffect(function () { var pt = paint(ref.current, { preset: p.palette || "dawn", seed: p.seed || 5, immediate: p.immediate }); return pt.destroy; }, [p.palette, p.seed]);
      return h("div", { ref: ref, className: cx("gj-wc gj-wc-wash", (p.palette || "dawn") === "dawn" && "gj-wc--multiply"), "aria-hidden": "true" });
    };
    var WatercolorWash = function (p) {
      var Tag = p.as || "div";
      return h(Tag, { className: cx("gj-washed", p.className), style: p.style }, h(Wash, { palette: p.palette, seed: p.seed, immediate: p.immediate }), p.children);
    };

    var ImageTextSplit = function (p) {
      return h("div", { className: cx("gj-split", p.reverse && "gj-split--reverse", p.className) },
        h("div", { className: "gj-split__media" },
          h(PaintedImage, { src: p.image, alt: p.alt, frame: p.frame || "petal", flip: p.reverse, position: p.position }),
          p.bloom && h(WatercolorBloom, { preset: p.bloom, seed: p.seed, decorative: true, delay: 500 })),
        h("div", { className: "gj-split__text" },
          h(SectionHeading, { eyebrow: p.eyebrow, title: p.title, highlight: p.highlight, size: "h2" }),
          p.children));
    };

    var PractitionerCard = function (p) {
      var Tag = p.href ? "a" : "div";
      return h(Tag, { href: p.href, className: cx("gj-person", p.className) },
        h(PaintedImage, { src: p.photo, alt: p.alt || "Portrait of " + p.name, frame: p.frame || "petal", position: p.position, seed: p.seed }),
        h("div", { style: { display: "grid", gap: "8px" } },
          h("span", { className: "gj-person__role" }, p.role),
          h("h3", { className: "gj-person__name" }, p.name),
          p.credentials && h("p", { className: "gj-person__creds" }, p.credentials)),
        p.interest && h("p", { className: "gj-person__interest" }, p.interest));
    };

    var QuoteSurface = function (p) {
      return h("section", { className: cx("gj-quote-surface", p.className) },
        h(Wash, { palette: "dusk", seed: p.seed || 9 }),
        p.logo !== false && h("img", { className: "gj-quote-surface__logo", src: assets.logoLight, alt: "Goji" }),
        h("blockquote", { className: "gj-quote", style: { margin: 0 } }, p.quote),
        p.by && h("p", { className: "gj-quote-surface__by" }, p.by),
        p.children && h("div", { style: { display: "flex", flexWrap: "wrap", gap: "12px" } }, p.children));
    };

    var ContactBlock = function (p) {
      var rows = [
        p.address && ["Visit", p.address.map(function (l, i) { return h("span", { key: i, style: { display: "block" } }, l); })],
        p.hours && ["Hours", p.hours.map(function (r, i) { return h("span", { key: i, style: { display: "block" } }, r.days + ": " + r.time); })],
        p.phone && ["Call", p.phone],
        p.email && ["Email", p.email]
      ].filter(Boolean);
      return h("div", { className: cx("gj-contact", p.className) },
        h("div", { style: { display: "grid", gap: "24px", alignContent: "start" } },
          h(SectionHeading, { eyebrow: p.eyebrow || "Visit us", title: p.title || "Say hello first", size: "h2", lead: p.intro }),
          h("div", { className: "gj-contact__ctas" },
            p.waHref && h(Button, { href: p.waHref, icon: "whatsapp" }, "Message us on WhatsApp"),
            p.bookHref && h(Button, { href: p.bookHref, variant: "secondary", icon: "calendar" }, "Book a visit"))),
        h("dl", { className: "gj-contact__facts" }, rows.map(function (r, i) {
          return h("div", { key: i, className: "gj-contact__row" }, h("dt", null, r[0]), h("dd", null, r[1]));
        })));
    };

    var fieldSeq = 0;
    var FormField = function (p) {
      var id = useRef(p.id || "gjf" + ++fieldSeq).current, hintId = id + "-hint";
      var common = { id: id, className: "gj-field__input", placeholder: p.placeholder, required: p.required, defaultValue: p.defaultValue, "aria-describedby": p.hint || p.error ? hintId : undefined, "aria-invalid": p.error ? "true" : undefined };
      var input = p.as === "textarea" ? h("textarea", common)
        : p.as === "select" ? h("select", common, (p.options || []).map(function (o) { return h("option", { key: o, value: o }, o); }))
        : h("input", Object.assign({ type: p.type || "text" }, common));
      return h("div", { className: cx("gj-field", p.error && "gj-field--error", p.className) },
        h("label", { className: "gj-field__label", htmlFor: id }, p.label, p.optional && h("span", null, " (optional)")),
        input,
        (p.error || p.hint) && h("span", { className: "gj-field__hint", id: hintId }, p.error || p.hint));
    };

    var LogoLockup = function (p) {
      var v = p.variant || "main";
      var src = { main: assets.logoMain, light: assets.logoLight, tagline: assets.logoTagline, mark: assets.logoMark }[v];
      return h("img", { src: src, alt: p.alt || (v === "tagline" ? "Goji Women's and Family Physiotherapy" : "Goji"), className: p.className, style: Object.assign({ height: p.height || 32, width: "auto", display: "block" }, p.style) });
    };

    var SiteHeader = function (p) {
      var ref = useRef(null), s = useState(false), scrolled = s[0], setScrolled = s[1];
      useEffect(function () {
        var f = function () { setScrolled(W.scrollY > 8); };
        W.addEventListener("scroll", f, { passive: true }); f();
        return function () { W.removeEventListener("scroll", f); };
      }, []);
      var links = p.links || [["Services", "/services/"], ["Conditions", "/conditions/"], ["Team", "/team/"], ["Media", "/media/"], ["Getting here", "/getting-here/"]];
      return h("header", { ref: ref, className: cx("gj-header", (scrolled || p.scrolled) && "is-scrolled", p.className) },
        h("div", { className: "gj-header__in" },
          h("a", { className: "gj-header__logo", href: "/", "aria-label": "Goji home" }, h("img", { src: assets.logoMain, alt: "Goji" })),
          h("nav", { className: "gj-header__nav", "aria-label": "Primary" }, links.map(function (l) {
            return h("a", { key: l[1], href: l[1], "aria-current": p.current === l[1] ? "page" : undefined }, l[0]);
          })),
          h("div", { className: "gj-header__cta" }, h(Button, { href: p.waHref || "https://go.gojiphysio.com/web-wa", icon: "whatsapp", size: "sm" }, "WhatsApp us")),
          h("button", { className: "gj-header__menu", type: "button", "aria-label": "Open menu" }, Icon("menu"))));
    };


    var GrowthPath = function (p) {
      var listRef = useRef(null), vineRef = useRef(null), gRef = useRef(null);
      var presets = p.presets || ["node-bud", "node-flower", "node-berry"];
      useEffect(function () {
        var list = listRef.current, vine = vineRef.current;
        function nodes() {
          var size = vine.clientWidth * (W.innerWidth >= 860 ? 1.45 : 1.25);
          return Array.prototype.map.call(list.querySelectorAll(".gj-path__step"), function (li, i) {
            return { y: li.offsetTop + size * 0.32, preset: presets[Math.min(i, presets.length - 1)], size: size };
          });
        }
        var g = gRef.current = grow(vine, { nodes: nodes(), seed: p.seed });
        var ro = null, t = 0;
        if ("ResizeObserver" in W) {
          ro = new ResizeObserver(function () { clearTimeout(t); t = setTimeout(function () { g.layout(nodes()); }, 180); });
          ro.observe(list);
        }
        if (D.fonts && D.fonts.ready) D.fonts.ready.then(function () { g.layout(nodes()); });
        return function () { clearTimeout(t); if (ro) ro.disconnect(); g.destroy(); };
      }, []);
      return h("div", { className: cx("gj-path", p.className) },
        h("div", { ref: vineRef, className: "gj-path__vine", "aria-hidden": "true" }),
        h("ol", { ref: listRef, className: "gj-path__steps" }, (p.steps || []).map(function (st, i) {
          return h("li", { key: i, className: "gj-path__step" },
            st.kicker && h(Eyebrow, null, st.kicker),
            h("h3", { className: "gj-h2" }, st.title),
            st.body && h("p", { className: "gj-body" }, st.body),
            st.children);
        })));
    };

    var BreathingBloom = function (p) {
      var ref = useRef(null), bRef = useRef(null);
      var st = useState({ phase: "ready", cycle: 0 }), state = st[0], setState = st[1];
      var cycles = p.cycles || 6;
      useEffect(function () {
        var b = bRef.current = breathe(ref.current, { inhale: p.inhale, exhale: p.exhale, hold: p.hold, cycles: cycles, seed: p.seed,
          onPhase: function (ph, c) { setState({ phase: ph, cycle: c }); } });
        return b.destroy;
      }, []);
      var words = { ready: p.readyLabel || "Ready when you are", "in": "Breathe in", hold: "Hold", out: "Breathe out", paused: "Paused", done: p.doneLabel || "Well done. Notice how you feel." };
      var running = state.phase === "in" || state.phase === "out" || state.phase === "hold";
      return h("div", { className: cx("gj-breath", p.className) },
        h("div", { className: "gj-breath__stage" },
          h("div", { ref: ref, className: "gj-wc gj-wc--multiply gj-breath__wash", "aria-hidden": "true" }),
          h("p", { className: "gj-breath__word", "aria-live": "polite" }, words[state.phase])),
        h("div", { className: "gj-breath__side" },
          h(SectionHeading, { eyebrow: p.eyebrow || "A moment for you", title: p.title || "Breathe with the bloom", size: "h3", level: 3, lead: p.intro }),
          h("ol", { className: "gj-breath__dots", "aria-label": "Breath " + Math.min(cycles, state.cycle + (running ? 1 : 0)) + " of " + cycles },
            Array.apply(null, Array(cycles)).map(function (_, i) {
              var done = state.phase === "done" || i < state.cycle || (running && i === state.cycle);
              return h("li", { key: i, className: done ? "is-done" : "" });
            })),
          h("div", { style: { display: "flex", gap: "12px", flexWrap: "wrap" } },
            h(Button, { variant: running ? "secondary" : "primary", onClick: function () { running ? bRef.current.pause() : bRef.current.start(); } }, running ? "Pause" : state.phase === "paused" ? "Resume" : state.phase === "done" ? "Again" : "Start"),
            (state.phase === "paused") && h(Button, { variant: "quiet", onClick: function () { bRef.current.reset(); setState({ phase: "ready", cycle: 0 }); } }, "Start over")),
          p.note && h("p", { className: "gj-caption" }, p.note)));
    };
    Object.assign(api, {
      Button: Button, Eyebrow: Eyebrow, SectionHeading: SectionHeading, PaintedUnderline: PaintedUnderline,
      BerryList: BerryList, StatBlock: StatBlock, CareCard: CareCard, ImageTextSplit: ImageTextSplit,
      PractitionerCard: PractitionerCard, QuoteSurface: QuoteSurface, ContactBlock: ContactBlock,
      FormField: FormField, SiteHeader: SiteHeader, LogoLockup: LogoLockup, WatercolorBloom: WatercolorBloom,
      WatercolorWash: WatercolorWash, PaintedImage: PaintedImage, Reveal: Reveal, GrowthPath: GrowthPath, BreathingBloom: BreathingBloom
    });
  }
  W.Goji = api;
})();
