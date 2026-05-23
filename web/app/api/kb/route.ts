// Returns the seed knowledge base so the dashboard can show the starting
// lessons before any request. Read only; the dashboard never writes shared/.

import { readSeedLessons } from "@/lib/kb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const lessons = await readSeedLessons();
  return new Response(JSON.stringify({ lessons }), {
    headers: { "Content-Type": "application/json" },
  });
}
