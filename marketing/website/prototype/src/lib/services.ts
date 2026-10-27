/**
 * DurationVariant represents an alternative duration and price for a service
 * or physiotherapy sub-type (e.g., paediatric physio offers both 30-min/$160 and
 * 55-min/$260 options).
 */
export interface DurationVariant {
  durationMin: number;
  price: string;
  priceNote?: string;
  description?: string;
}

/**
 * Services — single source of truth shared by the homepage service cards and the
 * booking form. `price` is the base price figure; leave "" to hide the price line.
 * `priceNote` is an optional secondary line.
 *
 * Booking-only fields:
 * - `supportsHome`: whether a home visit is offered (equipment-based sessions are
 *   in-clinic only, so the booking form hides the home-visit option for them).
 * - `durationMin`: session length, used to build the booking slot window.
 * - `platoCalendarId`: the Plato online-booking calendar this card maps to
 *   (from GET /onlineapptbooking/list). Phase 2 queries /onlineapptbooking/slots
 *   with this id for real availability. Note: "Physiotherapy" spans several
 *   Plato condition-calendars; it maps to Women's/Pelvic (all three clinicians)
 *   and the front desk triages the specific condition. "Mummy & Baby" has no
 *   dedicated Plato calendar yet — mapped to Paediatric (Cheryl + Kristy); a
 *   dedicated 85-min calendar should be created in Plato (its interval is 60m).
 *   NOTE: duration/age/price were reconciled to the clinic's service doc on
 *   2026-07-13 (85 min, babies 0–12 months, in-clinic $330 / home $450);
 *   confirm the 85-min Plato calendar exists before launch.
 */
export type ServiceId =
  | "physiotherapy"
  | "mummy-baby"
  | "clinical-pilates"
  | "private-pilates"
  | "strength-conditioning";

export interface Service {
  id: ServiceId;
  icon: string;
  title: string;
  lead: string;
  meta: string[];
  price: string;
  /** Usual (non-promotional) price, shown beside `price` while an introductory price is active. */
  priceUsual?: string;
  priceNote: string;
  supportsHome: boolean;
  durationMin: number;
  platoCalendarId: string;
  /**
   * Plato "Appointment Type" code (the `code_Bottom` field on POST /appointment).
   * Validated codes: Physiotherapy=hDWW, Clinical Pilates=2kV4, S&C=qLbH, Home Visit=sCla,
   * Private Pilates=N1z9 (GET /appointment/codes, 2026-10-23).
   * (`code_Left` = Space Requirement: YS06 Reformer needed / QWGT Reformer 1/2 session;
   * Confirmed/Unconfirmed live in `code_Right`: qK8x / dm1V.)
   * OPEN: Mummy & Baby has no Plato type — using Physiotherapy (hDWW) for now.
   * RULE (decided 2026-07-07): a HOME-VISIT booking is typed Home Visit (`sCla`)
   * regardless of service; the service name goes in the title/description. So the
   * backend uses `format === "home" ? "sCla" : service.platoTypeCode`.
   */
  platoTypeCode: string;
  bookingHidden?: boolean;
}

export const services: Service[] = [
  {
    id: "physiotherapy",
    icon: "tabler:stretching",
    title: "Physiotherapy",
    lead: "Personalised assessment and treatment for pain, injuries, pelvic health, musculoskeletal, vestibular and lymphatic concerns.",
    meta: ["55 min Initial consult", "In-clinic & home visits"],
    price: "260",
    priceNote: "Home visits $380",
    supportsHome: true,
    durationMin: 55,
    platoCalendarId: "dDIjWJp",
    platoTypeCode: "hDWW",
  },
  {
    id: "paediatric-physiotherapy",
    icon: "tabler:stretching",
    title: "Paediatric Physiotherapy",
    lead: "Thoughtful care for babies, children and teens, from early developmental milestones to scoliosis and sports injuries.",
    meta: ["From 30 min", "In-clinic & home visits"],
    price: "160",
    priceNote: "From 30 min. Home visits available on request with parent supervision",
    supportsHome: true,
    durationMin: 30,
    platoCalendarId: "z1xE8rP",
    platoTypeCode: "hDWW",
    bookingHidden: true,
  },
  {
    id: "strength-conditioning",
    icon: "tabler:barbell",
    title: "Strength & Conditioning",
    lead: "Build strength and physical confidence with personalised training guided by our physiotherapists.",
    meta: ["55 min Initial consult", "1:1 or 2:1 sessions"],
    price: "180",
    priceNote: "",
    supportsHome: false,
    durationMin: 55,
    platoCalendarId: "XV1FDpu",
    platoTypeCode: "qLbH",
  },
  {
    id: "clinical-pilates",
    icon: "tabler:yoga",
    title: "Clinical Pilates",
    lead: "Physiotherapist-led Pilates, thoughtfully adapted to your movement goals and physical needs.",
    meta: ["55 min", "1:1 or 2:1 reformer"],
    price: "180",
    priceNote: "",
    supportsHome: false,
    durationMin: 55,
    platoCalendarId: "ne8sgkb",
    platoTypeCode: "2kV4",
  },
  {
    id: "private-pilates",
    icon: "tabler:stretching-2",
    title: "Private Pilates",
    lead: "Personalised mat and reformer Pilates with our STOTT PILATES® certified instructor, in private 1:1 or 2:1 sessions.",
    meta: ["55 min", "1:1 or 2:1 reformer"],
    // Introductory price (active promotion; no end date published). Usual price
    // is shown beside it. Update `priceUsual`/`price` together when it ends.
    price: "149",
    priceUsual: "160",
    priceNote: "",
    supportsHome: false,
    durationMin: 55,
    // Camille's online-booking calendar (rule: pF9S, see clinicians.ts). Keep
    // in sync with online_calendar in the booking service's config.py.
    platoCalendarId: "vXKlwa7",
    platoTypeCode: "N1z9",
  },
  {
    id: "mummy-baby",
    icon: "tabler:baby-carriage",
    title: "Mummy & Baby Assessment",
    lead: "One appointment for two. Supporting your postpartum recovery while assessing your baby's movement and early development.",
    meta: ["85 min Initial consult", "In-clinic & home visits"],
    price: "330",
    priceNote: "Home visits $450",
    supportsHome: true,
    durationMin: 85,
    platoCalendarId: "z1xE8rP",
    platoTypeCode: "hDWW",
  },
];

/** Look up a service by id (returns undefined if not found). */
export function serviceById(id: string): Service | undefined {
  return services.find((s) => s.id === id);
}
