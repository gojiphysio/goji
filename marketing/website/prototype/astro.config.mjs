// @ts-check
import fs from "node:fs";
import { defineConfig } from "astro/config";
import icon from "astro-icon";
import sitemap from "@astrojs/sitemap";

// While the blog has no published posts, /blog renders a `noindex` "Coming
// soon" placeholder (see src/pages/blog/index.astro). Listing a noindexed URL
// in the sitemap sends Search Console conflicting signals, so drop it until a
// post exists. `astro:content` isn't available inside this config, hence the
// filesystem check; it self-corrects the moment a .md lands in the collection.
const BLOG_DIR = new URL("./src/content/blog/", import.meta.url);
const blogHasPosts =
  fs.existsSync(BLOG_DIR) &&
  fs.readdirSync(BLOG_DIR).some((f) => f.endsWith(".md"));

// Static output (the default). Cloudflare Pages serves the contents of `dist/`.
// When SSR / Pages Functions are needed later (e.g. the enquiry-form handler),
// add `@astrojs/cloudflare` as an adapter here.
export default defineConfig({
  // Set to the production origin when we cut over from Squarespace.
  site: "https://www.gojiphysio.com",
  output: "static",
  integrations: [
    icon(),
    // Generates /sitemap-index.xml; keep the internal styleguide and the
    // noindexed /search results page out of it.
    sitemap({
      filter: (page) =>
        !page.includes("/styleguide") &&
        !page.includes("/search") &&
        (blogHasPosts || !page.includes("/blog")),
    }),
  ],
});
