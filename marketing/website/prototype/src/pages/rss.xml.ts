/**
 * /rss.xml — the blog feed.
 *
 * Free distribution surface: readers, aggregators and several AI crawlers pick
 * posts up from a feed sooner than from a sitemap. Blog only; press entries
 * point at other people's articles and do not belong in our feed.
 */
import rss from "@astrojs/rss";
import { getCollection } from "astro:content";
import type { APIContext } from "astro";
import { SITE } from "../lib/site.ts";

export async function GET(context: APIContext) {
  const posts = (await getCollection("blog", ({ data }) => !data.draft)).sort(
    (a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf(),
  );

  return rss({
    title: `${SITE.name} | Blog`,
    description:
      "Plain-language physiotherapy education for women and families from the team at Goji, Lentor MRT Singapore.",
    site: context.site ?? "https://www.gojiphysio.com",
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: `/blog/${post.slug}/`,
      categories: [post.data.category, ...post.data.tags],
      author: post.data.author.name,
    })),
    customData: "<language>en-sg</language>",
  });
}
