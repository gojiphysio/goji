/**
 * Site search — a thin wrapper over the Pagefind runtime.
 *
 * Pagefind builds its index from `dist/` AFTER `astro build` (see the `build`
 * script and `pagefind.yml`), so `/pagefind/pagefind.js` does not exist under
 * `astro dev`. Every entry point here returns `null` instead of throwing when
 * the runtime is missing, and callers show a "available in the production
 * build" note. To exercise search locally: `npm run build && npm run preview`.
 *
 * The module is only ever loaded on demand (first keystroke / first dialog
 * open), so a visitor who never searches downloads none of it. That matters:
 * most of our traffic is on a phone.
 */

/**
 * Result buckets. Each page declares one via BaseLayout's `searchType` prop,
 * which becomes `data-pagefind-filter="type:…"` on <main>.
 */
export type SearchType =
  | "Service"
  | "Condition"
  | "Article"
  | "Press"
  | "Team"
  | "Page";

export interface SearchHit {
  url: string;
  title: string;
  /** Pagefind's HTML excerpt, with <mark> around the matched terms. */
  excerpt: string;
  /** Result bucket, from the `data-pagefind-filter="type:…"` on <main>. */
  type: string;
}

type PagefindModule = {
  options: (o: Record<string, unknown>) => Promise<void>;
  search: (q: string) => Promise<{ results: { data: () => Promise<any> }[] }>;
};

let runtime: PagefindModule | null = null;
let unavailable = false;

/** Load (once) and memoise the Pagefind runtime. Null when it isn't built. */
export async function loadPagefind(): Promise<PagefindModule | null> {
  if (runtime) return runtime;
  if (unavailable) return null;
  try {
    // Held in a variable so Vite does not try to resolve this at build time —
    // the file is produced by the Pagefind CLI after Astro has finished.
    const path = "/pagefind/pagefind.js";
    const mod = (await import(/* @vite-ignore */ path)) as PagefindModule;
    await mod.options({ excerptLength: 24 });
    runtime = mod;
    return runtime;
  } catch {
    unavailable = true;
    return null;
  }
}

/**
 * Run a query. Returns [] for no matches and `null` when search itself is
 * unavailable — the caller must tell those two apart, because "no results"
 * shows the WhatsApp fallback and "unavailable" shows a dev note.
 */
export async function runSearch(
  query: string,
  limit = 12,
): Promise<SearchHit[] | null> {
  const pagefind = await loadPagefind();
  if (!pagefind) return null;

  const trimmed = query.trim();
  if (!trimmed) return [];

  const { results } = await pagefind.search(trimmed);
  const top = await Promise.all(results.slice(0, limit).map((r) => r.data()));

  return top.map((d) => ({
    url: d.url,
    title: d.meta?.title || d.url,
    excerpt: d.excerpt || "",
    type: d.filters?.type?.[0] || "Page",
  }));
}

/** Display order for the result buckets — clinical intent first. */
const TYPE_ORDER = ["Condition", "Service", "Article", "Press", "Team", "Page"];

/** Group hits by type, preserving relevance order inside each bucket. */
export function groupByType(hits: SearchHit[]): [string, SearchHit[]][] {
  const buckets = new Map<string, SearchHit[]>();
  for (const hit of hits) {
    const list = buckets.get(hit.type);
    if (list) list.push(hit);
    else buckets.set(hit.type, [hit]);
  }
  return [...buckets.entries()].sort(
    (a, b) => TYPE_ORDER.indexOf(a[0]) - TYPE_ORDER.indexOf(b[0]),
  );
}

const escapeHtml = (s: string) =>
  s.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c] as string,
  );

/**
 * Render grouped results into a container. Shared by the header dialog and the
 * standalone /search page so both look and behave identically.
 *
 * `excerpt` is injected as HTML because Pagefind wraps matched terms in
 * <mark>; the text itself comes from our own build-time index, not from user
 * input. Titles are escaped.
 */
export function renderResults(container: HTMLElement, hits: SearchHit[]): void {
  container.innerHTML = groupByType(hits)
    .map(
      ([type, items]) => `
      <li class="search__group">
        <h2 class="search__group-title">${escapeHtml(typeLabel(type))}</h2>
        <ul class="search__group-list">
          ${items
            .map(
              (hit) => `
            <li>
              <a class="search__hit" href="${escapeHtml(hit.url)}">
                <span class="search__hit-title">${escapeHtml(hit.title)}</span>
                <span class="search__hit-excerpt">${hit.excerpt}</span>
              </a>
            </li>`,
            )
            .join("")}
        </ul>
      </li>`,
    )
    .join("");
}

/** Plural label for a result bucket heading. */
export function typeLabel(type: string): string {
  switch (type) {
    case "Condition":
      return "Conditions";
    case "Service":
      return "Services";
    case "Article":
      return "Articles";
    case "Press":
      return "Press";
    case "Team":
      return "Our team";
    default:
      return "Pages";
  }
}
