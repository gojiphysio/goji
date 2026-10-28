/** Date helpers shared by the blog and press surfaces. */

/** Human date for bylines and cards, e.g. "21 July 2026". */
export function formatDate(date: Date): string {
  return date.toLocaleDateString("en-SG", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** ISO yyyy-mm-dd for <time datetime> and JSON-LD date fields. */
export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}
