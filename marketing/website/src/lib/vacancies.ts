/**
 * Vacancies: the single source of truth for /careers.
 *
 * Every open (or recently closed) role is one entry in VACANCIES. The careers
 * landing page, each /careers/<slug>/ page, the JobPosting JSON-LD, the
 * application form's role list and /careers/vacancies.json (which the
 * goji-careers backend reads to check a role is still open) all derive from
 * this file, so management changes a role here and nothing else.
 *
 * How to add, change or close a role: website/CAREERS.md.
 *
 * Content rules (from the recruitment brief, 2026-11):
 * - The approved job description is the Google Doc "Senior Physiotherapist -
 *   Job Posting". Keep its wording; only format it for the web.
 * - Never publish salary figures, commission percentages or thresholds,
 *   projected earnings, sign-on incentives, salary reviews, differences in pay
 *   between seniority levels, or unapproved benefits. Never call Goji
 *   "boutique".
 * - Keep employment terms flexible (owner's amendment, 2026-11-26): no
 *   incentive or bonus mechanism or payout frequency, no number of leave days,
 *   no development allowance amount, no weekly hours or fixed schedule, and no
 *   named future clinic locations or expansion timelines.
 * - British English, regular dashes, no emojis.
 */

export type EmploymentType = "FULL_TIME" | "PART_TIME";

/** Which extra questions the application form asks for this role. */
export type FormKind = "physio" | "general";

export interface Vacancy {
  /** Stable job ID. Written to the tracker and the backend allowlist; never
   *  rename a published one (old applications reference it). */
  id: string;
  /** URL slug: /careers/<slug>/ */
  slug: string;
  title: string;
  department: string;
  location: string;
  employmentTypes: EmploymentType[];
  /** Plain-language minimum working commitment, shown on the card and page. */
  minCommitment: string;
  /** Minimum part-time days per week, used by the form's notice. */
  minDaysPerWeek?: number;
  /** Minimum years of post-qualification experience (for JSON-LD). */
  minYearsExperience: number;
  experience: string;
  clinicalFocus: { primary: string; secondary?: string };
  shortDescription: string;
  /** "About the role" paragraphs. */
  about: string[];
  /** Core responsibilities from the approved job description. */
  responsibilities: string[];
  /** Seniority-specific responsibilities, shown after the core ones. */
  additionalResponsibilities?: { heading: string; items: string[]; note?: string };
  requirements: string[];
  preferred: { intro: string; items: string[] };
  /** "Compensation & Benefits" in the doc. */
  benefits: string[];
  /** "Clinical & Career Development" in the doc. */
  development: string[];
  workingArrangements: string[];
  /** Paragraph shown after the working-arrangements list. */
  workingArrangementsNote?: string;
  /** ISO date the role was first published (JobPosting datePosted). */
  datePosted: string;
  /** ISO date applications close, if there is one (JobPosting validThrough). */
  closingDate?: string;
  /** Inactive roles drop off the list, lose their form and JobPosting, and
   *  show an "applications closed" notice instead. */
  active: boolean;
  featured: boolean;
  /** Sort order on /careers (lower first). */
  order: number;
  seo: { title: string; description: string };
  form: FormKind;
  /** Other roles a candidate can ask to be considered for in the same
   *  application (e.g. Physiotherapist <-> Senior Physiotherapist). */
  alsoConsiderFor?: string[];
  /** Drive sub-folder the applications for this role are filed under. */
  driveFolder: string;
}

// ---- Shared physiotherapist content (both seniority levels) ---------------
// Kept once so the two physiotherapist roles can't drift. Role-specific text
// (title, minimum experience, introduction, senior responsibilities) lives on
// each entry below.

/** Core responsibilities, verbatim from the approved job description
 *  (Google Doc 1ydDEFBnjAtjUA7ku7YQmkdigynp8JiEtmoC7vpdi-TE, text supplied by
 *  the owner 2026-11-24). Shared by both seniority levels. */
const PHYSIO_RESPONSIBILITIES: string[] = [
  "Conduct comprehensive physiotherapy assessments and deliver individualised, evidence-based treatment and rehabilitation programmes.",
  "Independently manage and develop a patient caseload, with a primary focus on musculoskeletal conditions.",
  "Deliver patient education, manual therapy, exercise prescription and other appropriate treatment modalities.",
  "Conduct home visits where clinically appropriate.",
  "Maintain accurate and timely clinical documentation.",
  "Collaborate with fellow clinicians, referring doctors and other healthcare professionals to optimise patient outcomes.",
  "Participate in regular clinical discussions, case reviews and knowledge-sharing sessions.",
  "Contribute to the growth of the practice through service development, professional networking, educational workshops and community initiatives.",
  "Uphold high standards of clinical care, professionalism and patient experience.",
];

/** The doc says "Minimum 3-5 years"; the amendment splits it by level. */
const physioRequirements = (minYears: number): string[] => [
  "BSc/Masters qualification in Physiotherapy.",
  "Full registration with the Allied Health Professions Council (AHPC), Singapore, and a valid Practising Certificate.",
  `Minimum ${minYears} years of post-qualification clinical physiotherapy experience.`,
  "Strong clinical competency in musculoskeletal assessment, treatment and rehabilitation.",
  "Ability to independently manage and develop a patient caseload.",
  "Excellent communication and interpersonal skills.",
  "A collaborative, proactive and patient-centred approach to care.",
  "Commitment to continuous professional development.",
];

const PHYSIO_PREFERRED = {
  intro: "The following would be advantageous but are not mandatory:",
  items: [
    "Clinical experience or a keen interest in women's health, including pre- and post-natal rehabilitation and pelvic health.",
    "Training or certification in Clinical Pilates, mat or reformer Pilates.",
    "Training and experience in dry needling.",
    "Training in strength and conditioning or sports rehabilitation.",
    "Previous experience in private practice.",
  ],
};

/** Kept deliberately non-specific (owner's amendment, 2026-11-26): no pay
 *  structure, incentive mechanism or payout frequency, no leave days, no
 *  development allowance amount. Individual terms are set in the offer. */
const PHYSIO_BENEFITS = [
  "Competitive remuneration package with performance-based incentives.",
  "Attractive annual leave entitlement.",
  "Professional development and continuing education support.",
  "Company-sponsored professional liability insurance.",
];

const PHYSIO_DEVELOPMENT = [
  "Clinical autonomy and opportunities to develop your areas of specialisation.",
  "A collaborative clinical environment with regular case discussions and peer learning.",
  "Well-equipped facilities with private treatment rooms, Pilates equipment and a dedicated rehabilitation and exercise space.",
  "Opportunities to contribute to new clinical services, corporate programmes and community initiatives.",
  "Opportunities for career progression and leadership responsibilities as the practice expands.",
];

/** No weekly hours or fixed schedule (owner's amendment, 2026-11-26), and no
 *  named future locations or timelines. The clinic's opening hours live on the
 *  patient-facing pages, not here. */
const PHYSIO_WORKING = [
  "Full-time positions with rostered working hours, including weekend commitments.",
  "Part-time positions with a minimum commitment of three days per week.",
  "Working arrangements are subject to mutual agreement and operational requirements.",
  "Currently based at our Lentor Modern clinic, conveniently connected to Lentor MRT.",
];

const PHYSIO_WORKING_NOTE =
  "As Goji continues to grow, there may be opportunities to work across future clinic locations. The designated workplace may be subject to change in line with business expansion and operational requirements.";

const LOCATION = "Singapore (currently based at Lentor Modern)";

export const VACANCIES: Vacancy[] = [
  {
    id: "physiotherapist",
    slug: "physiotherapist",
    title: "Physiotherapist",
    department: "Clinical",
    location: LOCATION,
    employmentTypes: ["FULL_TIME", "PART_TIME"],
    minCommitment: "Part-time from 3 days per week",
    minDaysPerWeek: 3,
    minYearsExperience: 3,
    experience: "At least 3 years post-qualification",
    clinicalFocus: { primary: "Musculoskeletal physiotherapy", secondary: "Women's health" },
    shortDescription:
      "Join our growing clinical team and further develop your expertise in musculoskeletal rehabilitation and women's health. We're looking for a confident, collaborative physiotherapist who is passionate about delivering evidence-based, patient-centred care.",
    about: [
      "We are seeking a Physiotherapist with a minimum of three years of post-qualification clinical experience and a strong foundation in musculoskeletal physiotherapy.",
      "The ideal candidate is a confident, independent clinician with strong clinical reasoning, a patient-centred approach and an interest in further developing their expertise in women's health.",
      "We welcome candidates seeking either full-time or part-time commitments.",
    ],
    responsibilities: PHYSIO_RESPONSIBILITIES,
    requirements: physioRequirements(3),
    preferred: PHYSIO_PREFERRED,
    benefits: PHYSIO_BENEFITS,
    development: PHYSIO_DEVELOPMENT,
    workingArrangements: PHYSIO_WORKING,
    workingArrangementsNote: PHYSIO_WORKING_NOTE,
    // Set to the real go-live date when the page is published.
    datePosted: "2026-11-24",
    active: true,
    featured: true,
    order: 1,
    seo: {
      title: "Physiotherapist Jobs Singapore | Goji",
      description:
        "Join Goji Physiotherapy in Singapore, currently at Lentor Modern. Full-time and part-time physiotherapist role for MSK clinicians with an interest in women's health.",
    },
    form: "physio",
    alsoConsiderFor: ["senior-physiotherapist"],
    driveFolder: "Physiotherapist",
  },
  {
    id: "senior-physiotherapist",
    slug: "senior-physiotherapist",
    title: "Senior Physiotherapist",
    department: "Clinical",
    location: LOCATION,
    employmentTypes: ["FULL_TIME", "PART_TIME"],
    minCommitment: "Part-time from 3 days per week",
    minDaysPerWeek: 3,
    minYearsExperience: 5,
    experience: "At least 5 years post-qualification",
    clinicalFocus: { primary: "Musculoskeletal physiotherapy", secondary: "Women's health" },
    shortDescription:
      "Bring your clinical expertise to a growing practice, develop your areas of specialisation and help shape the future of Goji. We're looking for an experienced physiotherapist who values clinical excellence, collaboration and professional growth.",
    about: [
      "We are seeking a Senior Physiotherapist with a minimum of five years of post-qualification clinical experience and a strong foundation in musculoskeletal physiotherapy.",
      "The ideal candidate is a confident and independent clinician with excellent clinical reasoning, a patient-centred approach and an interest in women's health. Beyond delivering high-quality patient care, the candidate should be excited to contribute to the clinical and professional development of our growing practice.",
      "We welcome candidates seeking either full-time or part-time commitments.",
    ],
    responsibilities: PHYSIO_RESPONSIBILITIES,
    additionalResponsibilities: {
      heading: "Additional responsibilities as a Senior Physiotherapist",
      items: [
        "Contribute to clinical mentorship, peer learning and knowledge sharing where appropriate.",
        "Take an active role in clinical service development and quality improvement.",
        "Support the development of professional referral relationships and partnerships.",
        "Explore opportunities for clinical leadership as the practice expands.",
      ],
      note: "Prior formal management or leadership experience is not required.",
    },
    requirements: physioRequirements(5),
    preferred: PHYSIO_PREFERRED,
    benefits: PHYSIO_BENEFITS,
    development: PHYSIO_DEVELOPMENT,
    workingArrangements: PHYSIO_WORKING,
    workingArrangementsNote: PHYSIO_WORKING_NOTE,
    // Set to the real go-live date when the page is published.
    datePosted: "2026-11-24",
    active: true,
    featured: true,
    order: 2,
    seo: {
      title: "Senior Physiotherapist Jobs Singapore | Goji",
      description:
        "Senior physiotherapist role at Goji Physiotherapy in Singapore, currently at Lentor Modern. Full-time or part-time, for experienced MSK clinicians with an interest in women's health.",
    },
    form: "physio",
    alsoConsiderFor: ["physiotherapist"],
    driveFolder: "Senior Physiotherapist",
  },
];

/** The pseudo-role for general expressions of interest. Not a vacancy: it
 *  never appears in the list and never gets JobPosting data. */
export const GENERAL_INTEREST = {
  id: "general",
  title: "General expression of interest",
  driveFolder: "General Expressions of Interest",
} as const;

/** Areas a general expression of interest can name (the future roles in the
 *  recruitment brief). Shown as a select on the expression-of-interest form. */
export const INTEREST_AREAS = [
  "Physiotherapy",
  "Women's health physiotherapy",
  "Clinical leadership",
  "Pilates instruction",
  "Clinic operations",
  "Administration and patient care",
  "Something else",
] as const;

/** Training options on the form (multi-select). Kept in sync with
 *  TRAINING_OPTIONS in business-intelligence/scripts/careers/config.py. */
export const TRAINING_OPTIONS = [
  "Clinical Pilates",
  "Mat or reformer Pilates",
  "Dry needling",
  "Women's health / Pelvic health",
  "Pre- and post-natal rehabilitation",
  "Strength and conditioning",
  "Sports rehabilitation",
  "Other",
] as const;

export const AHPC_OPTIONS = [
  "Fully registered",
  "Conditionally registered",
  "Registration pending",
  "Not currently registered",
] as const;

export const HEARD_ABOUT_OPTIONS = [
  "LinkedIn",
  "JobStreet",
  "Instagram",
  "Goji website",
  "Someone I know at Goji",
  "Other",
] as const;

export const WORKING_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;

/** A role is open when it is active and its closing date (if any) has not
 *  passed in Singapore time. Evaluated at build time; a closing date also
 *  needs a rebuild (any deploy) to take the page down, and the backend checks
 *  it again on every submission. */
export function isOpen(v: Vacancy, now = new Date()): boolean {
  if (!v.active) return false;
  if (!v.closingDate) return true;
  const sgToday = new Date(now.getTime() + 8 * 3600_000).toISOString().slice(0, 10);
  return sgToday <= v.closingDate;
}

export function openVacancies(now = new Date()): Vacancy[] {
  return VACANCIES.filter((v) => isOpen(v, now)).sort((a, b) => a.order - b.order);
}

export function vacancyById(id: string): Vacancy | undefined {
  return VACANCIES.find((v) => v.id === id);
}

export function employmentLabel(types: EmploymentType[]): string {
  const map: Record<EmploymentType, string> = { FULL_TIME: "Full-time", PART_TIME: "Part-time" };
  return types.map((t) => map[t]).join(" / ");
}
