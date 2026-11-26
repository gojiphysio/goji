/**
 * Careers: vacancy helpers, the application form's option lists, the backend
 * seam and the (non-identifying) analytics helper.
 *
 * The option lists mirror `business-intelligence/scripts/careers/config.py`;
 * keep them in sync (the backend rejects any value it doesn't list).
 * Vacancies live in `src/content/careers/*.yaml` (how-to: ../../CAREERS.md).
 */
import type { CollectionEntry } from "astro:content";
import { SITE } from "./site.ts";

export type Vacancy = CollectionEntry<"careers">;

/** The careers backend (goji-careers on Cloud Run). The form is inert
 *  (explains how to apply by email instead) until this is set in the
 *  Cloudflare Pages build env, so a build without it can't half-submit. */
export const CAREERS_API = (import.meta.env.PUBLIC_CAREERS_API as string | undefined) || "";

/** Bump with the backend's PRIVACY_NOTICE_VERSION whenever the notice changes. */
export const PRIVACY_NOTICE_VERSION = "2026-11-v1";

export const CAREERS_EMAIL = SITE.email;
export const MAX_CV_MB = 10;
export const CV_ACCEPT =
  ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

type Options = ReadonlyArray<readonly [string, string]>;

export const CAREERS_OPTIONS = {
  employment: [
    ["full_time", "Full-time"],
    ["part_time", "Part-time"],
    ["either", "Open to both"],
  ],
  years: [
    ["0-2", "Less than 3 years"],
    ["3-5", "3-5 years"],
    ["6-10", "6-10 years"],
    ["10+", "More than 10 years"],
  ],
  ahpc: [
    ["full", "Fully registered"],
    ["conditional", "Conditionally registered"],
    ["pending", "Registration pending"],
    ["none", "Not currently registered"],
  ],
  clinicalAreas: [
    ["msk", "Musculoskeletal / orthopaedic"],
    ["sports", "Sports injuries"],
    ["womens_health", "Women's health / pelvic health"],
    ["antenatal_postnatal", "Pregnancy and postnatal"],
    ["paediatrics", "Paediatrics"],
    ["neuro", "Neurological"],
    ["cardioresp", "Cardiorespiratory"],
    ["older_adults", "Older adults / falls"],
    ["vestibular", "Vestibular"],
    ["post_surgical", "Post-surgical rehabilitation"],
    ["other", "Other"],
  ],
  certifications: [
    ["clinical_pilates", "Clinical Pilates"],
    ["mat_reformer_pilates", "Mat or reformer Pilates"],
    ["dry_needling", "Dry needling"],
    ["womens_pelvic", "Women's health / Pelvic health"],
    ["pre_post_natal", "Pre- and post-natal rehabilitation"],
    ["strength_conditioning", "Strength and conditioning"],
    ["sports_rehab", "Sports rehabilitation"],
    ["other", "Other"],
  ],
  days: [
    ["mon", "Mon"],
    ["tue", "Tue"],
    ["wed", "Wed"],
    ["thu", "Thu"],
    ["fri", "Fri"],
    ["sat", "Sat"],
  ],
  heard: [
    ["linkedin", "LinkedIn"],
    ["jobstreet", "JobStreet"],
    ["instagram", "Instagram"],
    ["website", "Goji website"],
    ["referral", "Friend or colleague"],
    ["other", "Other"],
  ],
  roleCategories: [
    ["physiotherapy", "Physiotherapy"],
    ["pilates", "Pilates instruction"],
    ["operations", "Clinic operations"],
    ["patient_care", "Administration and patient care"],
    ["other", "Other"],
  ],
} satisfies Record<string, Options>;

/** Open roles first by `featured`, then newest. */
export function sortVacancies(list: Vacancy[]): Vacancy[] {
  return [...list].sort(
    (a, b) =>
      Number(b.data.featured) - Number(a.data.featured) ||
      b.data.datePublished.getTime() - a.data.datePublished.getTime(),
  );
}

export function isOpen(v: Vacancy, now = new Date()): boolean {
  if (v.data.status !== "open") return false;
  // A role past its closing date closes itself at the next build.
  return !v.data.closingDate || v.data.closingDate.getTime() >= startOfToday(now);
}

function startOfToday(now: Date): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** The visible job description as HTML, for JobPosting.description. Built
 *  from the same `sections` the page renders, so the schema never says more
 *  than the page does. */
export function descriptionHtml(v: Vacancy): string {
  const parts = [`<p>${esc(v.data.shortDescription)}</p>`];
  for (const s of v.data.sections) {
    parts.push(`<h2>${esc(s.heading)}</h2>`);
    for (const p of s.paragraphs) parts.push(`<p>${esc(p)}</p>`);
    if (s.items.length) parts.push(`<ul>${s.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`);
  }
  return parts.join("");
}

const isoDate = (d: Date) => d.toISOString().slice(0, 10);

/** JobPosting JSON-LD for an open role (never emitted for closed ones, never
 *  on the /careers listing). No salary: none is approved for publication. */
export function jobPostingSchema(v: Vacancy, pageUrl: string, origin: string) {
  const d = v.data;
  return {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: d.title,
    description: descriptionHtml(v),
    identifier: { "@type": "PropertyValue", name: SITE.fullName, value: d.jobId },
    datePosted: isoDate(d.datePublished),
    ...(d.closingDate ? { validThrough: `${isoDate(d.closingDate)}T23:59:59+08:00` } : {}),
    employmentType: d.employmentTypes,
    hiringOrganization: {
      "@type": "Organization",
      name: SITE.fullName,
      sameAs: origin,
      logo: new URL("/brand/logo_main_transparent.png", origin).href,
    },
    jobLocation: {
      "@type": "Place",
      address: {
        "@type": "PostalAddress",
        streetAddress: SITE.address.line1,
        addressRegion: "Singapore",
        addressLocality: "Singapore",
        postalCode: "788887",
        addressCountry: "SG",
      },
    },
    ...(d.experienceMonths
      ? {
          experienceRequirements: {
            "@type": "OccupationalExperienceRequirements",
            monthsOfExperience: d.experienceMonths,
          },
        }
      : {}),
    ...(d.form === "physio"
      ? {
          educationRequirements: {
            "@type": "EducationalOccupationalCredential",
            credentialCategory: "bachelor degree",
          },
        }
      : {}),
    industry: "Healthcare",
    occupationalCategory: "29-1123.00 Physical Therapists",
    directApply: true,
    url: pageUrl,
  };
}

/** GA4 events for the recruitment funnel. Only the event name, the job id and
 *  an error code ever leave the page: never names, contact details, answers,
 *  CV filenames or introduction text. GA4 attaches campaign (utm_*) itself. */
export type CareersEvent =
  | "careers_page_view"
  | "job_detail_view"
  | "apply_now_clicked"
  | "application_started"
  | "application_submitted"
  | "expression_of_interest_submitted"
  | "application_error";

export function careersEvent(
  name: CareersEvent,
  params: { job_id?: string; error_code?: string } = {},
): void {
  try {
    const gtag = (window as unknown as { gtag?: (...a: unknown[]) => void }).gtag;
    if (!gtag) return;
    const safe: Record<string, string> = {};
    if (params.job_id) safe.job_id = params.job_id.slice(0, 40);
    if (params.error_code) safe.error_code = params.error_code.slice(0, 40);
    gtag("event", name, safe);
  } catch {
    /* analytics never breaks the page */
  }
}

/** Campaign tags for the application record (LinkedIn / JobStreet / Instagram
 *  job posts): this visit's utm_* first, else the first-touch ones the landing
 *  beacon stored. Non-identifying. */
export function campaignTags(): Record<string, string> {
  const out: Record<string, string> = {};
  const keys = ["utm_source", "utm_medium", "utm_campaign", "utm_content"];
  try {
    const q = new URLSearchParams(location.search);
    for (const k of keys) if (q.get(k)) out[k] = q.get(k)!.slice(0, 100);
    if (Object.keys(out).length) return out;
    const a = JSON.parse(localStorage.getItem("goji_attr") || "{}") as Record<string, unknown>;
    for (const k of keys) if (a[k]) out[k] = String(a[k]).slice(0, 100);
  } catch {
    /* best-effort */
  }
  return out;
}
