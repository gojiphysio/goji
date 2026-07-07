/**
 * Services — single source of truth shared by the homepage service cards and the
 * booking form. `price` is the "From $" figure; leave "" to hide the price line.
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
 *   dedicated 90-min calendar should be created in Plato (its interval is 60m).
 */
export type ServiceId =
  | "physiotherapy"
  | "mummy-baby"
  | "clinical-pilates"
  | "strength-conditioning";

export interface Service {
  id: ServiceId;
  icon: string;
  title: string;
  lead: string;
  meta: string[];
  price: string;
  priceNote: string;
  supportsHome: boolean;
  durationMin: number;
  platoCalendarId: string;
  /**
   * Plato "Appointment Type" code (the `code_Bottom` field on POST /appointment).
   * Validated codes: Physiotherapy=hDWW, Pilates=2kV4, S&C=qLbH, Home Visit=sCla.
   * (Confirmed/Unconfirmed live in `code_Left`: YS06 / C22K.)
   * OPEN: Mummy & Baby has no Plato type — using Physiotherapy (hDWW) for now.
   * RULE (decided 2026-07-07): a HOME-VISIT booking is typed Home Visit (`sCla`)
   * regardless of service; the service name goes in the title/description. So the
   * backend uses `format === "home" ? "sCla" : service.platoTypeCode`.
   */
  platoTypeCode: string;
}

export const services: Service[] = [
  {
    id: "physiotherapy",
    icon: "tabler:stretching",
    title: "Physiotherapy",
    lead: "Assessment and treatment for pain, injury, recovery, pelvic health, women's health, paediatric, vestibular, and lymphatic concerns.",
    meta: ["55 min initial consult", "In-clinic & home visits"],
    price: "260",
    priceNote: "Home visits from $330",
    supportsHome: true,
    durationMin: 55,
    platoCalendarId: "dDIjWJp",
    platoTypeCode: "hDWW",
  },
  {
    id: "mummy-baby",
    icon: "tabler:baby-carriage",
    title: "Mummy & Baby Assessment",
    lead: "A joint assessment for postpartum mothers and babies aged 0 to 6 months, supporting recovery, development, and early physical needs.",
    meta: ["90 min", "In-clinic & home visits"],
    price: "330",
    priceNote: "",
    supportsHome: true,
    durationMin: 90,
    platoCalendarId: "z1xE8rP",
    platoTypeCode: "hDWW",
  },
  {
    id: "clinical-pilates",
    icon: "tabler:yoga",
    title: "Clinical Pilates",
    lead: "Physiotherapist-led reformer Pilates for rehabilitation, movement retraining, strength, and a safe return to activity or sport.",
    meta: ["55 min", "1:1 or 2:1 reformer"],
    price: "180",
    priceNote: "",
    supportsHome: false,
    durationMin: 55,
    platoCalendarId: "ne8sgkb",
    platoTypeCode: "2kV4",
  },
  {
    id: "strength-conditioning",
    icon: "tabler:barbell",
    title: "Strength & Conditioning",
    lead: "Build strength and resilience through tailored exercise, with guidance from professionals to sustain your momentum.",
    meta: ["55 min", "1:1 or 2:1 sessions"],
    price: "180",
    priceNote: "",
    supportsHome: false,
    durationMin: 55,
    platoCalendarId: "XV1FDpu",
    platoTypeCode: "qLbH",
  },
];

/** Look up a service by id (returns undefined if not found). */
export function serviceById(id: string): Service | undefined {
  return services.find((s) => s.id === id);
}
