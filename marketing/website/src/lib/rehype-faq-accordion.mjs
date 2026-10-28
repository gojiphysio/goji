/**
 * Rehype plugin: render a Markdown FAQ as the site's FAQ accordion.
 *
 * Condition and blog bodies write FAQs as `## Frequently asked questions`
 * followed by `### <question>` blocks (the format src/lib/faq.ts parses for
 * FAQPage JSON-LD). This rewrites each question block into the same
 * `details.faq-list__item` markup as components/FaqList.astro, so every FAQ on
 * the site looks the same while the Markdown stays the single source of truth.
 * Answers keep their full HTML (links, lists), unlike the plain-text schema.
 *
 * Works on the flat top-level node list Markdown produces and leaves the tree
 * untouched when there is no FAQ heading.
 */

const isEl = (node, tag) => node.type === "element" && node.tagName === tag;
const text = (node) =>
  node.type === "text" ? node.value : (node.children ?? []).map(text).join("");
const el = (tagName, className, children = []) => ({
  type: "element",
  tagName,
  properties: className ? { className: [className] } : {},
  children,
});

export default function rehypeFaqAccordion() {
  return (tree) => {
    const nodes = tree.children;
    const start = nodes.findIndex(
      (n) => isEl(n, "h2") && /^frequently asked questions$/i.test(text(n).trim()),
    );
    if (start === -1) return;
    let end = nodes.findIndex((n, i) => i > start && isEl(n, "h2"));
    if (end === -1) end = nodes.length;

    const lead = []; // anything between the heading and the first question
    const items = [];
    let current = null;
    for (const node of nodes.slice(start + 1, end)) {
      if (isEl(node, "h3")) {
        const toggle = el("span", "faq-list__toggle");
        toggle.properties.ariaHidden = "true";
        current = el("div", "faq-list__a");
        items.push(
          el("details", "faq-list__item", [
            el("summary", "faq-list__q", [...node.children, toggle]),
            current,
          ]),
        );
      } else if (!(node.type === "text" && !node.value.trim())) {
        (current ? current.children : lead).push(node);
      }
    }
    if (!items.length) return;

    nodes.splice(start + 1, end - start - 1, ...lead, el("div", "faq-list", items));
  };
}
