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
    clinicianIds: ["cheryl-long", "claire-ng", "kristy-ng"],
  },
  {
    id: "paediatrics",
    label: "Paediatrics",
    hint: "Injury, recovery, and developmental concerns for minors (up to 18Y).",
    clinicianIds: ["kristy-ng", "cheryl-long"],
  },
  {
    id: "scoliosis",
    label: "Scoliosis (Schroth Method)",
    hint: "Scoliosis-specific therapy for children and adults.",
    clinicianIds: ["cheryl-long"],
  },
  {
    id: "others",
    label: "Others",
    hint: "Please indicate your conditions / goals in the last booking step.",
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
