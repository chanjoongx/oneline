// Server-Sent Events endpoint that drives one request through the pipeline and
// streams each event so the three candidate columns fill in real time.
//
// POST body: { need: string, sessionLessons: Lesson[] }
// Response: text/event-stream of RunEvent objects.

import { runEngine } from "@/lib/demoEngine";
import type { RunEvent } from "@/lib/events";
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
      try {
        for await (const event of runEngine({ need, sessionLessons })) {
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
