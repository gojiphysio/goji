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
 *   Job Posting". Keep its wording; only format it for the web. The Freelance
 *   Pilates Instructor copy is the owner's brief of 2026-11-26, kept verbatim.
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

/** schema.org JobPosting employmentType values. CONTRACTOR = freelance. */
export type EmploymentType = "FULL_TIME" | "PART_TIME" | "CONTRACTOR";

/** Which question set the application form asks for this role. */
export type FormKind = "physio" | "pilates" | "general";

/** Section headings on the role page (and in the JobPosting description).
 *  Anything left out uses the physiotherapist wording. `benefits: ""` drops
 *  the sub-heading, for a role whose offer is one list. */
export interface VacancyHeadings {
  requirements?: string;
  preferred?: string;
  offer?: string;
  benefits?: string;
  development?: string;
  working?: string;
}

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
  /** Minimum years of post-qualification experience (for JSON-LD; 0 = none
   *  stated, and the JobPosting leaves experienceRequirements out). */
  minYearsExperience: number;
  experience: string;
  clinicalFocus: { primary: string; secondary?: string };
  /** Label for clinicalFocus on the card and page; default "clinical focus".
   *  A non-clinical role must set it (Private Pilates is not clinical care). */
  focusLabel?: string;
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
  /** "Clinical & Career Development" in the doc (empty = no such section). */
  development: string[];
  headings?: VacancyHeadings;
  /** The first "How to apply" paragraph; default is the physiotherapist one. */
  howToApply?: string;
  /** JobPosting fields that differ by profession. */
  schema?: { occupationalCategory: string; credentialCategory: string };
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
        "Physiotherapist role at Goji, Singapore (currently at Lentor Modern). Full-time or part-time, for MSK clinicians with an interest in women's health.",
    },
    form: "physio",
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
        "Senior physiotherapist at Goji, Singapore (currently Lentor Modern). Full-time or part-time, for experienced MSK clinicians with an interest in women's health.",
    },
    form: "physio",
    driveFolder: "Senior Physiotherapist",
  },
  {
    id: "pilates-instructor",
    slug: "pilates-instructor",
    title: "Freelance Pilates Instructor",
    department: "Pilates",
    location: LOCATION,
    employmentTypes: ["CONTRACTOR"],
    minCommitment: "Flexible, by mutual agreement",
    minYearsExperience: 0,
    experience: "Experience teaching personalised Pilates",
    clinicalFocus: { primary: "Private Pilates (1:1 and 2:1)" },
    focusLabel: "focus",
    // Copy supplied by the owner, 2026-11-26. Freelance: no employee benefits,
    // no fees, earnings, booking minimums or contract terms (CAREERS.md).
    shortDescription:
      "Deliver personalised Pilates sessions in a supportive, physiotherapy-led environment. Help clients build strength, improve movement and develop confidence in their bodies.",
    about: [
      "We're looking for a passionate and personable Pilates Instructor who enjoys delivering thoughtful, individualised movement experiences.",
      "Our Private Pilates offering focuses on 1:1 and 2:1 sessions, allowing instructors to develop meaningful client relationships and tailor each session to individual needs, abilities and goals.",
      "Work alongside our team of physiotherapists in a collaborative environment, supporting clients across different life stages, from pregnancy and postpartum recovery to healthy ageing and active lifestyles.",
      "This is an instructor-led Private Pilates role, offered as a freelance engagement. Clinical Pilates at Goji is a separate service led by our AHPC-registered physiotherapists, and is not part of this role.",
    ],
    responsibilities: [
      "Deliver safe, engaging and personalised 1:1 and 2:1 Pilates sessions.",
      "Adapt exercises to individual client needs, abilities and goals.",
      "Support client progression and continuity of care.",
      "Collaborate with Goji's physiotherapists while maintaining appropriate professional boundaries.",
      "Maintain accurate and timely session documentation.",
      "Uphold high standards of professionalism, client care, confidentiality, safety and studio hygiene.",
      "Opportunities to participate in workshops, community activations and marketing initiatives.",
    ],
    requirements: [
      "Recognised Pilates instructor certification, with training in Mat and Reformer Pilates.",
      "Experience delivering personalised Pilates instruction.",
      "Strong understanding of movement principles, exercise programming and safe exercise progression.",
      "Excellent interpersonal and communication skills.",
      "Ability to work independently and collaboratively within a multidisciplinary environment.",
    ],
    preferred: {
      intro: "The following would be advantageous but are not mandatory:",
      items: [
        "Comprehensive Pilates certification or training across additional apparatus.",
        "Prenatal and postnatal Pilates experience.",
        "Experience adapting exercises for clients with specific movement needs.",
        "Additional qualifications in fitness, movement or strength and conditioning.",
        "Interest in women's health.",
      ],
    },
    benefits: [
      "Competitive remuneration.",
      "Flexible availability and mutually agreed booking arrangements.",
      "Access to a well-equipped Pilates studio within a physiotherapy-led practice.",
      "Opportunities for professional collaboration and knowledge sharing.",
      "Opportunities for additional paid workshops, corporate engagements and community events.",
    ],
    development: [],
    workingArrangements: [
      "Regular weekly availability is preferred.",
      "Weekend availability would be advantageous.",
      "Currently based at our Lentor Modern clinic, conveniently connected to Lentor MRT.",
    ],
    workingArrangementsNote:
      "As Goji continues to grow, there may be opportunities to provide services across future clinic locations, subject to mutually agreed engagement arrangements.",
    headings: {
      requirements: "Qualifications and requirements",
      offer: "Remuneration and engagement arrangements",
      benefits: "",
      working: "Availability and location",
    },
    howToApply:
      "If you enjoy teaching Pilates one-to-one and would like to work alongside a team of physiotherapists, we would love to hear from you.",
    schema: { occupationalCategory: "Pilates Instructor", credentialCategory: "professional certificate" },
    datePosted: "2026-11-26",
    active: true,
    featured: true,
    order: 3,
    seo: {
      title: "Freelance Pilates Instructor Jobs Singapore | Goji",
      description:
        "Freelance Pilates instructor role at Goji, Singapore (currently Lentor Modern). Private 1:1 and 2:1 mat and reformer sessions in a physiotherapy-led practice.",
    },
    form: "pilates",
    driveFolder: "Pilates Instructor",
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

// ---- Pilates instructor form options ------------------------------------
// Kept in sync with the PILATES_* lists in
// business-intelligence/scripts/careers/config.py (the backend drops any
// value not on its list).

export const WORK_ELIGIBILITY_OPTIONS = [
  "Singapore Citizen or Permanent Resident",
  "I hold a pass that allows me to work in Singapore",
  "I would need a pass to work in Singapore",
] as const;

export const APPARATUS_OPTIONS = ["Mat", "Reformer", "Cadillac / Trapeze Table", "Chair", "Barrels", "Others"] as const;

export const TEACHING_YEARS_OPTIONS = [
  "Less than 1 year",
  "1 to 2 years",
  "3 to 5 years",
  "6 to 10 years",
  "More than 10 years",
] as const;

export const TEACHING_EXPERIENCE_OPTIONS = [
  "Private 1:1",
  "Duet 2:1",
  "Group Pilates",
  "Prenatal",
  "Postnatal",
  "Others",
] as const;

export const ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

export const TIME_WINDOWS = ["Morning", "Afternoon", "Evening"] as const;

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
  const map: Record<EmploymentType, string> = { FULL_TIME: "Full-time", PART_TIME: "Part-time", CONTRACTOR: "Freelance" };
  return types.map((t) => map[t]).join(" / ");
}
