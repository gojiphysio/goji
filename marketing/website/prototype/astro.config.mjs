// @ts-check
import { defineConfig } from "astro/config";
import icon from "astro-icon";

// Static output (the default). Cloudflare Pages serves the contents of `dist/`.
// When SSR / Pages Functions are needed later (e.g. the enquiry-form handler),
// add `@astrojs/cloudflare` as an adapter here.
export default defineConfig({
  // Set to the production origin when we cut over from Squarespace.
  site: "https://www.gojiphysio.com",
  output: "static",
  integrations: [icon()],
});
