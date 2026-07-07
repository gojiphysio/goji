/**
 * Clinician roster + the service -> clinician skill map that drives booking
 * assignment. Sourced from the team content collection
 * (src/content/team/*.md `specialties`).
 *
 * `services` is which booking services each clinician offers. When a client does
 * not pick a clinician, the clinic assigns one from those who offer the chosen
 * service (Phase 2 backend does the real routing + availability match).
 *
 * NOTE (confirm with clinic): mapping derived from listed specialties —
 * - Cheryl Long: women's/pelvic/paediatric/scoliosis/MSK + Clinical Pilates.
 * - Claire Ng: pelvic/pre & postnatal/women's/lymphoedema/vestibular/MSK. No
 *   paediatric or Pilates listed, so mapped to Physiotherapy only.
 * - Kristy Ng: pelvic/pre & postnatal/paediatric/women's/sports + Clinical Pilates.
 * Mummy & Baby needs paediatric competency (Cheryl, Kristy). Strength &
 * Conditioning mapped to the clinicians with exercise/sports/Pilates focus
 * (Cheryl, Kristy). Adjust here if the clinic's actual coverage differs.
 */
import type { ServiceId } from "./services";

export interface Clinician {
  id: string;
  name: string;
  role: string;
  services: ServiceId[];
}

export const clinicians: Clinician[] = [
  {
    id: "cheryl-long",
    name: "Cheryl Long",
    role: "Clinical Director",
    services: [
      "physiotherapy",
      "mummy-baby",
      "clinical-pilates",
      "strength-conditioning",
    ],
  },
  {
    id: "claire-ng",
    name: "Claire Ng",
    role: "Senior Physiotherapist",
    services: ["physiotherapy"],
  },
  {
    id: "kristy-ng",
    name: "Kristy Ng",
    role: "Senior Physiotherapist",
    services: [
      "physiotherapy",
      "mummy-baby",
      "clinical-pilates",
      "strength-conditioning",
    ],
  },
];

/** Clinicians who offer a given service (drives the optional clinician picker). */
export function cliniciansForService(serviceId: ServiceId): Clinician[] {
  return clinicians.filter((c) => c.services.includes(serviceId));
}
