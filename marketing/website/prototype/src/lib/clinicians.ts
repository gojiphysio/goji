/**
 * Clinician roster + the service -> clinician skill map that drives booking
 * assignment. Sourced from the team content collection
 * (src/content/team/*.md `specialties`).
 *
 * `services` is which booking services each clinician offers. When a client does
 * not pick a clinician, the clinic assigns one from those who offer the chosen
 * service (Phase 2 backend does the real routing + availability match).
 *
 * Coverage is the SOURCE OF TRUTH FROM PLATO's live online-booking config
 * (GET /onlineapptbooking/list, 2026-07-07), per each website card's mapped
 * Plato calendar:
 * - Physiotherapy -> Women's/Pelvic calendar: Cheryl, Kristy, Claire.
 * - Mummy & Baby  -> Paediatric calendar:     Cheryl, Kristy.
 * - Clinical Pilates -> Pilates 1:1 calendar: Cheryl, Claire.
 * - Strength & Conditioning -> S&C calendar:  Kristy, Claire.
 * calendarId is the Plato booking calendar `color` used when creating the
 * appointment; doctorCode is the Plato doctor code. Keep this in sync with
 * Plato — do not hand-edit coverage without checking onlineapptbooking/list.
 */
import type { ServiceId } from "./services";

export interface Clinician {
  id: string;
  name: string;
  role: string;
  services: ServiceId[];
  /** Plato booking calendar `color` (used as the appointment calendar id). */
  calendarId: string;
  /** Plato doctor code. */
  doctorCode: string;
}

export const clinicians: Clinician[] = [
  {
    id: "cheryl-long",
    name: "Cheryl Long",
    role: "Senior Physiotherapist",
    services: ["physiotherapy", "mummy-baby", "clinical-pilates"],
    calendarId: "blue",
    doctorCode: "PCL",
  },
  {
    id: "claire-ng",
    name: "Claire Ng",
    role: "Senior Physiotherapist",
    services: ["physiotherapy", "clinical-pilates", "strength-conditioning"],
    calendarId: "6hpO",
    doctorCode: "PCN",
  },
  {
    id: "kristy-ng",
    name: "Kristy Ng",
    role: "Senior Physiotherapist",
    services: ["physiotherapy", "mummy-baby", "strength-conditioning"],
    calendarId: "green",
    doctorCode: "PKN",
  },
];

/** Clinicians who offer a given service (drives the optional clinician picker). */
export function cliniciansForService(serviceId: ServiceId): Clinician[] {
  return clinicians.filter((c) => c.services.includes(serviceId));
}

/**
 * Home visits are offered by one clinician only (mirrors the booking backend's
 * HOME_VISIT_CLINICIAN). When "Home visit" is selected the picker is restricted
 * to this clinician.
 */
export const HOME_VISIT_CLINICIAN_ID = "cheryl-long";
