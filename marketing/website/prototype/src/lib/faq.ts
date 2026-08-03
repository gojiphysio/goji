/**
 * FAQPage extraction from Markdown bodies.
 *
 * Shared by the condition and blog templates so the *visible* copy stays the
 * single source of truth for the FAQPage JSON-LD — no duplicated Q&A in
 * frontmatter that can drift from the page.
 *
 * The parser looks for an exact `## Frequently asked questions` heading and
 * reads `### <question>` blocks beneath it, stopping at the next `##`. Other
 * heading levels (e.g. `####`) or bullet-style questions silently emit no
 * FAQPage — that contract is documented in the website AGENTS.md.
 *
 * Defensive by design: any parse miss returns [] rather than throwing, so a
 * malformed post can never break the build.
 */

export interface Faq {
  q: string;
  a: string;
}

export function extractFaqs(body: string): Faq[] {
  try {
    const heading = body.match(/^##\s+Frequently asked questions\s*$/im);
    if (!heading || heading.index === undefined) return [];
    const rest = body.slice(heading.index + heading[0].length);
    const nextH2 = rest.search(/^##\s+/m);
    const section = nextH2 === -1 ? rest : rest.slice(0, nextH2);
    return section
      .split(/^###\s+/m)
      .slice(1)
      .map((block) => {
        const newline = block.indexOf("\n");
        const q = (newline === -1 ? block : block.slice(0, newline)).trim();
        const a = (newline === -1 ? "" : block.slice(newline + 1))
          .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // links → plain text
          .replace(/[*_`]/g, "")
          .replace(/^\s*[-*]\s+/gm, "") // list markers (line starts only)
          .replace(/\s*\n\s*/g, " ")
          .trim();
        return { q, a };
      })
      .filter((f) => f.q && f.a);
  } catch {
    return [];
  }
}

/** Build the FAQPage JSON-LD block, or null when there are no parsable Q&As. */
export function faqSchema(faqs: Faq[]): Record<string, unknown> | null {
  if (!faqs.length) return null;
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };
}
