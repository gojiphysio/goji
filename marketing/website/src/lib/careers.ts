/**
 * Careers client helpers: the API seam for the application form and the
 * recruitment analytics events.
 *
 * The form only goes live when PUBLIC_CAREERS_API is set in the build env
 * (production: https://careers-api.gojiphysio.com). Without it the pages
 * render an email fallback instead of a form, so a preview or a build before
 * the backend exists can never show a form that doesn't store anything.
 */

export const CAREERS_API = (import.meta.env.PUBLIC_CAREERS_API as string | undefined) || "";

export type CareersEvent =
  | "careers_page_view"
  | "job_detail_view"
  | "apply_now_clicked"
  | "application_started"
  | "application_submitted"
  | "expression_of_interest_submitted"
  | "application_error";

/** The only parameters an event may carry. Nothing an applicant typed,
 *  chose or uploaded ever goes to analytics: no name, email, phone, file name,
 *  answers or free text. */
interface EventParams {
  job_id?: string;
  error_code?: string;
}

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content"] as const;

/** Campaign attribution for this visit: the current URL's UTM tags, falling
 *  back to the first-touch tags the landing beacon stored. Non-identifying. */
export function campaignAttribution(): Record<string, string> {
  const out: Record<string, string> = {};
  try {
    const qp = new URLSearchParams(location.search);
    let first: Record<string, string> = {};
    try {
      first = JSON.parse(localStorage.getItem("goji_attr") || "{}");
    } catch {
      /* ignore */
    }
    for (const k of UTM_KEYS) {
      const v = qp.get(k) || first[k];
      if (v) out[k] = String(v).slice(0, 100);
    }
  } catch {
    /* attribution is best-effort */
  }
  return out;
}

/** Send a recruitment event to GA4 when the site's gtag is present (it is
 *  inert until PUBLIC_GA4_ID is set). Never throws. */
export function careersEvent(name: CareersEvent, params: EventParams = {}): void {
  try {
    const gtag = (window as unknown as { gtag?: (...a: unknown[]) => void }).gtag;
    if (typeof gtag !== "function") return;
    const safe: Record<string, string> = { ...campaignAttribution() };
    if (params.job_id) safe.job_id = params.job_id.slice(0, 64);
    if (params.error_code) safe.error_code = params.error_code.slice(0, 64);
    gtag("event", name, safe);
  } catch {
    /* never break the page for analytics */
  }
}
