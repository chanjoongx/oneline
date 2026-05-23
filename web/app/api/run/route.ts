// Server-Sent Events endpoint that drives one request through the pipeline and
// streams each event so the three candidate columns fill in real time.
//
// POST body: { need: string, sessionLessons: Lesson[] }
// Response: text/event-stream of RunEvent objects.
//
// Source of the events:
//   - ONELINE_LIVE=1: the real core pipeline via the Python live runner
//     (real Gemini Managed Agents build plus real Cloud Run deploy).
//   - otherwise: the offline demoEngine, so rehearsal works with no services.
// Both produce the same RunEvent shape, so the dashboard renders either path
// identically.

import { runEngine } from "@/lib/demoEngine";
import type { RunEvent } from "@/lib/events";
import { runLive } from "@/lib/liveBridge";
import type { Lesson } from "@/lib/types";

// Needs the Node runtime for the deploy client (child_process and fs).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function sseChunk(event: RunEvent): string {
  return "event: " + event.type + "\n" + "data: " + JSON.stringify(event) + "\n\n";
}

export async function POST(req: Request): Promise<Response> {
  let need = "";
  let sessionLessons: Lesson[] = [];
  try {
    const body = await req.json();
    need = typeof body?.need === "string" ? body.need : "";
    sessionLessons = Array.isArray(body?.sessionLessons) ? body.sessionLessons : [];
  } catch {
    // tolerate an empty body; the engine handles an empty need
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: RunEvent) => {
        try {
          controller.enqueue(encoder.encode(sseChunk(event)));
        } catch {
          // controller already closed by a client disconnect
        }
      };
      const live = process.env.ONELINE_LIVE === "1";
      const source = live ? runLive(need) : runEngine({ need, sessionLessons });
      try {
        for await (const event of source) {
          send(event);
        }
      } catch (e) {
        send({ type: "error", message: String(e) });
      } finally {
        try {
          controller.close();
        } catch {
          // already closed
        }
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
