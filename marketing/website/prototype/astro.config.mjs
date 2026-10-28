// @ts-check
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import { defineConfig } from "astro/config";
import icon from "astro-icon";
import sitemap from "@astrojs/sitemap";
import rehypeFaqAccordion from "./src/lib/rehype-faq-accordion.mjs";

// While the blog has no published posts, /blog renders a `noindex` "Coming
// soon" placeholder (see src/pages/blog/index.astro). Listing a noindexed URL
// in the sitemap sends Search Console conflicting signals, so drop it until a
// post exists. `astro:content` isn't available inside this config, hence the
// filesystem check; it self-corrects the moment a .md lands in the collection.
const BLOG_DIR = new URL("./src/content/blog/", import.meta.url);
const blogHasPosts =
  fs.existsSync(BLOG_DIR) &&
  fs.readdirSync(BLOG_DIR).some((f) => f.endsWith(".md"));

// <lastmod> for the sitemap (Bing, which feeds ChatGPT search, uses it): the
// last commit date of the file that holds the page's content. A content
// collection entry (conditions, services, team, press, blog) wins over its
// route template; everything else maps to src/pages/<path>.astro or
// <path>/index.astro. Shared layout/template edits don't bump it on purpose:
// lastmod should mean "this page's content changed". On a shallow clone every
// file would carry the same commit date, which is worse than no date.
// Cloudflare Pages clones shallow, so the build first tries to fetch the full
// history and drops lastmod only if that fails.
const isShallow = () =>
  execFileSync("git", ["rev-parse", "--is-shallow-repository"], {
    encoding: "utf8",
  }).trim() !== "false";
const shallow = (() => {
  try {
    if (!isShallow()) return false;
    execFileSync("git", ["fetch", "--unshallow", "--quiet"], {
      stdio: "ignore",
      timeout: 120_000,
    });
    return isShallow();
  } catch {
    return true;
  }
})();

function lastmodFor(url) {
  if (shallow) return undefined;
  const route = new URL(url).pathname.replace(/^\/|\/$/g, "");
  const [section, slug] = route.split("/");
  const candidates = [
    ...(slug ? [`src/content/${section}/${slug}.md`] : []),
    `src/pages/${route || "index"}.astro`,
    `src/pages/${route}/index.astro`,
  ];
  const file = candidates.find((f) =>
    fs.existsSync(new URL(`./${f}`, import.meta.url)),
  );
  if (!file) return undefined;
  try {
    const iso = execFileSync("git", ["log", "-1", "--format=%cI", "--", file], {
      cwd: new URL(".", import.meta.url),
      encoding: "utf8",
    }).trim();
    return iso || undefined;
  } catch {
    return undefined;
  }
}

// Static output (the default). Cloudflare Pages serves the contents of `dist/`.
// When SSR / Pages Functions are needed later (e.g. the enquiry-form handler),
// add `@astrojs/cloudflare` as an adapter here.
export default defineConfig({
  // Set to the production origin when we cut over from Squarespace.
  site: "https://www.gojiphysio.com",
  output: "static",
  // Our CSS is small (~18 KB across all bundles), so inline it rather than
  // make the first paint wait on separate stylesheet requests (mobile LCP).
  build: { inlineStylesheets: "always" },
  // Markdown FAQ sections render as the site's FAQ accordion.
  markdown: { rehypePlugins: [rehypeFaqAccordion] },
  integrations: [
    icon(),
    // Generates /sitemap-index.xml; keep the internal styleguide and the
    // noindexed /search results page out of it.
    sitemap({
      filter: (page) =>
        !page.includes("/styleguide") &&
        !page.includes("/search") &&
        !page.includes("/links") &&
        (blogHasPosts || !page.includes("/blog")),
      serialize: (item) => {
        const lastmod = lastmodFor(item.url);
        return lastmod ? { ...item, lastmod } : item;
      },
    }),
  ],
});
