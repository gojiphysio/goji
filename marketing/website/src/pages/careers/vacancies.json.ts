/**
 * /careers/vacancies.json — the machine-readable role list the careers backend
 * (business-intelligence/scripts/careers/vacancies.py) reads to decide which
 * roles can be applied for. Built from src/content/careers/*.yaml, so opening
 * or closing a role is one edit there. Drafts are left out entirely; closed
 * roles are listed with active:false so the backend can say "closed".
 * Holds no personal data.
 */
import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
import { isOpen } from "../../lib/careers.ts";

export const GET: APIRoute = async () => {
  const roles = (await getCollection("careers")).filter((v) => v.data.status !== "draft");
  const body = {
    generated: new Date().toISOString(),
    vacancies: roles.map((v) => ({
      id: v.data.jobId,
      slug: v.id,
      title: v.data.title,
      active: isOpen(v),
      form: v.data.form,
      location: v.data.location,
      driveFolder: v.data.driveFolder,
      minDaysPerWeek: v.data.minDaysPerWeek ?? null,
    })),
  };
  return new Response(JSON.stringify(body, null, 2), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
