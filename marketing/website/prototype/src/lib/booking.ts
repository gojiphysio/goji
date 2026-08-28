/**
 * Booking data contract + the API seam the booking form talks to.
 *
 * The UI depends only on `BookingApi`. Which implementation runs is decided by
 * the `PUBLIC_BOOKING_API` build env var:
 *   - unset  -> MOCK (local dev / preview / the static mock-up; no real writes)
 *   - set    -> REAL fetch to the goji-booking backend
 *              (GET /api/availability, POST /api/book, POST /api/track)
 * So the same static build is safe to preview, and production just sets the var
 * to `https://booking.gojiphysio.com`.
 */
import type { ServiceId } from "./services";
import type { PhysioFocusId } from "./physioCategories";

export type BookingFormat = "clinic" | "home";

export interface BookingDraft {
  service: ServiceId | null;
  /** Physiotherapy sub-type (null for non-physio services). Narrows clinicians
   *  and tells the clinic what the physio session is for. */
  physioFocus: PhysioFocusId | null;
  /** Duration variant (e.g., "30min" or "55min"), when the sub-type offers
   *  multiple durations. Null for services/sub-types without variants. */
  variant: string | null;
  format: BookingFormat;
  address: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM (24h)
  /** "" means no preference — the clinic assigns a matching specialist. */
  clinicianId: string;
  name: string;
  phone: string;
  email: string;
  /** Optional free-text: what the patient wants us to know about their condition. */
  notes: string;
}

export interface AvailabilityQuery {
  service: ServiceId;
  /** Physio sub-type, when the service is physiotherapy. Lets the backend
   *  restrict availability to the mapped clinicians. */
  focus?: PhysioFocusId;
  /** Duration variant (e.g., "30min"), when the sub-type offers variants. */
  variant?: string;
  clinicianId: string;
  date: string;
  home: boolean;
}

export interface AvailableDaysQuery {
  service: ServiceId;
  focus?: PhysioFocusId;
  /** Duration variant (e.g., "30min"), when the sub-type offers variants. */
  variant?: string;
  clinicianId: string;
  /** Calendar month, YYYY-MM. */
  month: string;
  home: boolean;
}

export interface BookingResult {
  ok: boolean;
  reference?: string;
  error?: string;
  code?: string;
}

// Keep in sync with VALID_STAGES in the backend
// (business-intelligence/scripts/booking/app.py) — unknown stages are dropped.
export type FunnelStage =
  | "page_view"
  | "service_selected"
  | "date_picked"
  | "time_selected"
  | "details"
  | "submitted"
  | "validation_error"
  | "availability_error"
  | "clinician_changed";

export interface BookingApi {
  getAvailability(query: AvailabilityQuery): Promise<string[]>;
  /** The dates in a calendar month with at least one bookable slot — powers the
   *  calendar's availability shading and the first-free-date auto-pick. */
  getAvailableDays(query: AvailableDaysQuery): Promise<string[]>;
  createBooking(draft: BookingDraft): Promise<BookingResult>;
  /** Fire-and-forget funnel event; no-op in the mock. `detail` adds context for
   *  stuck events (e.g. which field failed validation). */
  track(stage: FunnelStage, detail?: string): void;
}

const API = import.meta.env.PUBLIC_BOOKING_API as string | undefined;

/** Stable per-session id so the backend can count drop-off by distinct session. */
export function bookingSessionId(): string {
  try {
    const key = "goji_booking_sid";
    let v = sessionStorage.getItem(key);
    if (!v) {
      v = crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2);
      sessionStorage.setItem(key, v);
    }
    return v;
  } catch {
    return "nosession";
  }
}

/** First-party visitor id (localStorage, stable across sessions). Set by the
 *  landing beacon in BaseLayout; read here so booking events carry the same id
 *  and join to marts.web_session_events. No PII. */
export function visitorId(): string {
  try {
    const key = "goji_vid";
    let v = localStorage.getItem(key);
    if (!v) {
      v = crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2);
      localStorage.setItem(key, v);
    }
    return v;
  } catch {
    return "novisitor";
  }
}

/** First-touch arrival attribution the landing beacon stashed in localStorage,
 *  reduced to the subset the booking backend stores (visitor_id + utm/gclid/
 *  go_click_id). {} keys absent if storage is blocked or the visit was direct. */
export function bookingAttribution(): Record<string, string> {
  const attr: Record<string, string> = { visitor_id: visitorId() };
  try {
    const raw = localStorage.getItem("goji_attr");
    if (raw) {
      const a = JSON.parse(raw) as Record<string, unknown>;
      for (const k of ["utm_source", "utm_campaign", "gclid", "go_click_id"]) {
        if (a[k]) attr[k] = String(a[k]);
      }
    }
  } catch {
    /* ignore — attribution is best-effort */
  }
  return attr;
}

// ---- Real backend ----------------------------------------------------------
const realApi: BookingApi = {
  async getAvailability({ service, focus, clinicianId, date, home }) {
    if (!date) return [];
    const p = new URLSearchParams({ service, date });
    if (focus) p.set("focus", focus);
    if (clinicianId) p.set("clinician", clinicianId);
    if (home) p.set("home", "1");
    // session_id lets the backend log its authoritative availability_empty
    // funnel event against this visitor when the chosen date has no slots.
    p.set("session_id", bookingSessionId());
    // Throw on a failed fetch (network / 5xx) so the caller can tell "couldn't
    // load" apart from a genuine "no slots" (200 with an empty list) — a
    // rate-limited request must not read as "no availability".
    const r = await fetch(`${API}/api/availability?${p.toString()}`);
    if (!r.ok) throw new Error(`availability ${r.status}`);
    const d = await r.json();
    return Array.isArray(d.times) ? d.times : [];
  },

  async getAvailableDays({ service, focus, clinicianId, month, home }) {
    const p = new URLSearchParams({ service, month });
    if (focus) p.set("focus", focus);
    if (clinicianId) p.set("clinician", clinicianId);
    if (home) p.set("home", "1");
    const r = await fetch(`${API}/api/availability-summary?${p.toString()}`);
    if (!r.ok) throw new Error(`availability-summary ${r.status}`);
    const d = await r.json();
    return Array.isArray(d.available) ? d.available : [];
  },

  async createBooking(draft) {
    try {
      const r = await fetch(`${API}/api/book`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service: draft.service,
          physio_focus: draft.physioFocus,
          variant: draft.variant,
          date: draft.date,
          time: draft.time,
          format: draft.format,
          name: draft.name,
          phone: draft.phone,
          email: draft.email,
          clinician_id: draft.clinicianId,
          address: draft.address,
          notes: draft.notes,
          session_id: bookingSessionId(),
          attribution: bookingAttribution(),
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok) return { ok: true, reference: d.reference };
      return {
        ok: false,
        error: d.error || "Something went wrong. Please try again or message us.",
        code: d.code,
      };
    } catch {
      return { ok: false, error: "We couldn't reach the booking system. Please message us on WhatsApp." };
    }
  },

  track(stage, detail) {
    try {
      fetch(`${API}/api/track`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage,
          detail,
          session_id: bookingSessionId(),
          attribution: bookingAttribution(),
        }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* never break the flow for a tracking hiccup */
    }
  },
};

// ---- Mock (default) --------------------------------------------------------
function seededUnit(seed: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 1000;
}
const MOCK_LATENCY_MS = 450;

function mockDayTimes(service: string, clinicianId: string, date: string): string[] {
  if (!date) return [];
  const day = new Date(`${date}T00:00:00`);
  if (day.getDay() === 0) return []; // Sunday closed
  const open: string[] = [];
  const key = `${service}|${clinicianId}|${date}`;
  const isSaturday = day.getDay() === 6;
  const step = isSaturday ? 60 : 30; // Saturday: hourly; other days: 30-min
  const maxSlots = isSaturday ? 8 : 16; // Adjust slot count for Saturday hourly
  for (let i = 0; i < maxSlots; i++) {
    const mins = 9 * 60 + i * step; // 09:00 start, varying step size
    const hh = String(Math.floor(mins / 60)).padStart(2, "0");
    const mm = String(mins % 60).padStart(2, "0");
    if (seededUnit(key, i) > 0.45) open.push(`${hh}:${mm}`);
  }
  return open;
}

const mockApi: BookingApi = {
  async getAvailability({ service, clinicianId, date }) {
    await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS));
    return mockDayTimes(service, clinicianId, date);
  },

  async getAvailableDays({ service, clinicianId, month }) {
    await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS));
    // Mirror the real endpoint's window: [tomorrow, +60 days], Sundays closed.
    const [y, m] = month.split("-").map(Number);
    if (!y || !m) return [];
    const min = new Date();
    min.setHours(0, 0, 0, 0);
    min.setDate(min.getDate() + 1);
    const max = new Date(min);
    max.setDate(max.getDate() + 59);
    const out: string[] = [];
    const daysInMonth = new Date(y, m, 0).getDate();
    for (let d = 1; d <= daysInMonth; d++) {
      const day = new Date(y, m - 1, d);
      if (day < min || day > max) continue;
      const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      if (mockDayTimes(service, clinicianId, iso).length) out.push(iso);
    }
    return out;
  },
  async createBooking(draft) {
    await new Promise((r) => setTimeout(r, MOCK_LATENCY_MS));
    if (!draft.service || !draft.date || !draft.time || !draft.name) {
      return { ok: false, error: "Missing required booking details." };
    }
    const ref =
      "GOJI-" +
      Math.abs(Math.floor(seededUnit(JSON.stringify(draft), 7) * 1e6))
        .toString(36)
        .toUpperCase()
        .padStart(4, "0");
    return { ok: true, reference: ref };
  },
  track(_stage, _detail) {
    /* no-op in the mock */
  },
};

export const bookingApi: BookingApi = API ? realApi : mockApi;
