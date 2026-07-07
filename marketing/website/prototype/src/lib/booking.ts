/**
 * Booking data contract + the API seam the booking form talks to.
 *
 * PHASE 1 (now): `bookingApi` is a client-side MOCK so the whole flow is
 * reviewable on the static site with no backend and no Plato key.
 *
 * PHASE 2 (next): replace the two method bodies with `fetch` calls to the
 * `goji-booking` backend — `GET /api/availability` and `POST /api/book` — which
 * hold the write-capable Plato key server-side and create the appointment via
 * Plato `POST /{db}/appointment`. The form UI depends only on this interface, so
 * nothing above this file changes.
 */
import type { ServiceId } from "./services";

export type BookingFormat = "clinic" | "home";

export interface BookingDraft {
  service: ServiceId | null;
  format: BookingFormat;
  address: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM (24h)
  /** "" means no preference — the clinic assigns a matching specialist. */
  clinicianId: string;
  name: string;
  phone: string;
  email: string;
}

export interface AvailabilityQuery {
  service: ServiceId;
  clinicianId: string;
  date: string;
}

export interface BookingResult {
  ok: boolean;
  reference?: string;
  error?: string;
}

export interface BookingApi {
  getAvailability(query: AvailabilityQuery): Promise<string[]>;
  createBooking(draft: BookingDraft): Promise<BookingResult>;
}

/** Deterministic 0..1 pseudo-random from a string, so mock slots are stable per date. */
function seededUnit(seed: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 1000;
}

const MOCK_LATENCY_MS = 450;

/**
 * Phase 1 mock. Availability: 30-min slots across clinic hours, with a stable,
 * date-dependent subset marked open. Sundays return no slots (clinic closed).
 */
export const bookingApi: BookingApi = {
  async getAvailability({ service, clinicianId, date }) {
    await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS));
    if (!date) return [];
    const day = new Date(`${date}T00:00:00`).getDay(); // 0 = Sunday
    if (day === 0) return [];
    const open: string[] = [];
    const key = `${service}|${clinicianId}|${date}`;
    // 09:00 to 16:30 in 30-min steps.
    for (let i = 0; i < 16; i++) {
      const mins = 9 * 60 + i * 30;
      const hh = String(Math.floor(mins / 60)).padStart(2, "0");
      const mm = String(mins % 60).padStart(2, "0");
      if (seededUnit(key, i) > 0.45) open.push(`${hh}:${mm}`);
    }
    return open;
  },

  async createBooking(draft) {
    await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS));
    if (!draft.service || !draft.date || !draft.time || !draft.name) {
      return { ok: false, error: "Missing required booking details." };
    }
    const ref =
      "GOJI-" +
      Math.abs(
        Math.floor(seededUnit(JSON.stringify(draft), 7) * 1e6),
      )
        .toString(36)
        .toUpperCase()
        .padStart(4, "0");
    return { ok: true, reference: ref };
  },
};
