/**
 * /careers/vacancies.json — the machine-readable vacancy list.
 *
 * The goji-careers backend fetches this (cached) to decide whether a job ID is
 * still open before it stores an application, so the website's
 * src/lib/vacancies.ts stays the one place a role is opened or closed.
 * Contains only public facts that are already on the pages.
 */
import type { APIRoute } from "astro";
import { VACANCIES, isOpen } from "../../lib/vacancies.ts";

export const GET: APIRoute = () => {
  const body = {
    generated_at: new Date().toISOString(),
    vacancies: VACANCIES.map((v) => ({
      id: v.id,
      title: v.title,
      open: isOpen(v),
      form: v.form,
      min_days_per_week: v.minDaysPerWeek ?? null,
      closing_date: v.closingDate ?? null,
      drive_folder: v.driveFolder,
    })),
  };
  return new Response(JSON.stringify(body, null, 2), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
