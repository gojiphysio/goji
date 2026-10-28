import type { DurationVariant } from "./services";

/**
 * Physiotherapy sub-types (the "What type of physiotherapy?" step on the booking
 * form) and the clinicians each one opens.
 *
 * "Physiotherapy" is one booking option, but it spans several sub-types that map
 * to different clinicians. Picking one on Step 1 narrows the clinician picker
 * (and, once the backend consumes `physio_focus`, the calendars queried for
 * availability). It also gives the clinic clarity on WHAT people book physio for
 * without lengthening the top-level service list.
 *
 * `clinicianIds` MUST stay consistent with `clinicians.ts` coverage — e.g. Claire
 * does not do paediatrics, and only Cheryl offers Schroth/scoliosis. Do not widen
 * a category beyond who actually offers it in the roster.
 *
 * Some sub-types (e.g., paediatrics) offer multiple duration variants.
 * `variants` maps variant ids to their duration and pricing (e.g., "30min", "55min").
 */

export type PhysioFocusId =
  | "general"
  | "womens-health"
  | "paediatrics"
  | "scoliosis"
  | "others";

export interface PhysioCategory {
  id: PhysioFocusId;
  label: string;
  /** Short helper shown under the label on the booking form. */
  hint: string;
  /** Clinician ids (from clinicians.ts) this sub-type opens. */
  clinicianIds: string[];
  /** Optional: variant durations/prices (e.g., { "30min": {...}, "55min": {...} }). */
  variants?: Record<string, DurationVariant>;
}

export const physioCategories: PhysioCategory[] = [
  {
    id: "general",
    label: "General Musculoskeletal (MSK)",
    hint: "Pain management, post-op rehab, injury, recovery and other MSK concerns.",
    clinicianIds: ["cheryl-long", "claire-ng", "kristy-ng"],
  },
  {
    id: "womens-health",
    label: "Women's Health",
    hint: "Prenatal, postpartum, and pelvic health.",
    clinicianIds: ["claire-ng", "kristy-ng"],
  },
  {
    id: "paediatrics",
    label: "Paediatrics",
    hint: "Neurodevelopmental concerns, congenital conditions, chest physio, pelvic health (bed wetting / constipation) and other injuries.",
    clinicianIds: ["kristy-ng", "cheryl-long"],
    variants: {
      "30min": { durationMin: 30, price: "160", description: "Only if prescribed by physio" },
      "45min": { durationMin: 45, price: "230", description: "Review session" },
      "55min": { durationMin: 55, price: "260", description: "Initial consultation" },
    },
  },
  {
    id: "scoliosis",
    label: "Scoliosis (Schroth Method)",
    hint: "Scoliosis-specific therapy for children and adults.",
    clinicianIds: ["cheryl-long"],
  },
  {
    id: "others",
    label: "Not sure / other",
    hint: "Tell us what's going on in the last step and we'll match you with the right physio.",
    clinicianIds: ["cheryl-long", "claire-ng", "kristy-ng"],
  },
];

const byId = new Map(physioCategories.map((c) => [c.id, c] as const));

/** True if the string is a known physio sub-type id. */
export function isPhysioFocus(id: string): id is PhysioFocusId {
  return byId.has(id as PhysioFocusId);
}

/** Clinician ids a given sub-type opens (empty array for an unknown id). */
export function cliniciansForPhysioFocus(id: string): string[] {
  return byId.get(id as PhysioFocusId)?.clinicianIds ?? [];
}
