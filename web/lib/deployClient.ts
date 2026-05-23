// The deploy client, server side. Pushes the winning tool to the next pre-warmed
// Cloud Run service in the pool and returns the live URL. The phone mockup
// preview never waits on this; the deploy runs in parallel and the dashboard
// renders the QR when it returns.
//
// Two paths:
//   - real: spawn the canonical Python deployer (deployer.py) which runs the
//     verified gcloud recipe and rotates services oneline-demo-1..5.
//   - simulate: a fast, offline-safe stand in so the dashboard always works
//     offline, even without gcloud. Enable the real path with
//     ONELINE_DEPLOY_REAL=1.
//
// Either way the call resolves to a usable Deployment, so the demo never stalls.

import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { Deployment } from "./types";

const POOL = [
  "oneline-demo-1",
  "oneline-demo-2",
  "oneline-demo-3",
  "oneline-demo-4",
  "oneline-demo-5",
];

// Rotation cursor for the simulate path. The real path keeps its own rotation
// state in deployer.py so service choice is consistent across processes.
let cursor = 0;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function nowTs(): number {
  return Math.floor(Date.now() / 1000);
}

function fallbackUrl(): string {
  return (
    process.env.ONELINE_FALLBACK_URL ||
    "https://oneline-demo-1-uc.a.run.app"
  );
}

async function simulate(): Promise<Deployment> {
  const service = POOL[cursor % POOL.length];
  cursor += 1;
  // A realistic but short delay so the deploy phase reads as live without
  // waiting on the network.
  await sleep(2600 + Math.floor(Math.random() * 1400));
  return {
    url: "https://" + service + "-uc.a.run.app",
    service,
    ts: nowTs(),
  };
}

function runPython(html: string, timeoutMs: number): Promise<Deployment> {
  return new Promise(async (resolve, reject) => {
    let tmpFile = "";
    try {
      const dir = await mkdtemp(path.join(os.tmpdir(), "oneline-deploy-"));
      tmpFile = path.join(dir, "index.html");
      await writeFile(tmpFile, html, { encoding: "utf-8" });
    } catch (e) {
      reject(new Error("could not stage html: " + String(e)));
      return;
    }

    const python = process.env.PYTHON || "python";
    const script = path.join(process.cwd(), "deployer.py");
    const child = spawn(python, [script, tmpFile, "--json"], {
      cwd: process.cwd(),
      env: process.env,
    });

    let out = "";
    let err = "";
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("deploy timed out after " + timeoutMs + "ms"));
    }, timeoutMs);

    child.stdout.on("data", (d) => (out += d.toString()));
    child.stderr.on("data", (d) => (err += d.toString()));
    child.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error("deployer exited " + code + ": " + err.slice(0, 400)));
        return;
      }
      // Parse the last JSON object printed on stdout.
      const line = out
        .trim()
        .split("\n")
        .reverse()
        .find((l) => l.trim().startsWith("{"));
      if (!line) {
        reject(new Error("no json from deployer: " + out.slice(0, 400)));
        return;
      }
      try {
        const parsed = JSON.parse(line);
        resolve({
          url: parsed.url,
          service: parsed.service,
          ts: parsed.ts,
          fallback: parsed.fallback === true,
          error: parsed.error,
        });
      } catch (e) {
        reject(new Error("bad json from deployer: " + String(e)));
      }
    });
  });
}

export async function deployWinner(html: string): Promise<Deployment> {
  if (process.env.ONELINE_DEPLOY_REAL === "1") {
    try {
      return await runPython(html, 150000);
    } catch (e) {
      // Resilient failure path: the iframe preview already shows the result, so
      // the QR falls back to a pre-deployed URL rather than stalling the demo.
      return {
        url: fallbackUrl(),
        service: "fallback",
        ts: nowTs(),
        fallback: true,
        error: String(e),
      };
    }
  }
  return simulate();
}
