// Shared building blocks for the generated-tool fixtures. These tools are real,
// working, single-file HTML pages that inherit the Oneline design system from
// shared/base.css: dark base, exactly one accent, one hero value, the fixed
// type scale, spacing on the 8px grid, primary action in the bottom third.
//
// They serve three roles for the dashboard:
//   1. candidate previews in the three columns,
//   2. the winning tool rendered instantly in the phone mockup,
//   3. the pre-built fallback tool when a live build is unavailable.
//
// Rule: no em dashes anywhere. The inner tool script
// never uses backticks or template placeholders, so the outer template literal
// only ever interpolates the accent.

// A faithful, compact subset of shared/base.css. The accent is injected per
// tool. Source of truth for the values is shared/base.css.
export const BASE_CSS = `
:root{
  --bg:#0A0A0B;--surface:#141416;--surface-2:#1C1C1F;--border:#2A2A2E;
  --text:#F5F5F7;--text-muted:#9A9AA2;--text-faint:#5C5C64;
  --accent:#5B8DEF;--accent-ink:#0A0A0B;
  --positive:#3FB950;--warning:#D29922;--danger:#F85149;
  --radius:12px;--radius-pill:999px;--unit:8px;
  --space-1:8px;--space-2:16px;--space-3:24px;--space-4:32px;--space-6:48px;
  --content-max:480px;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif;
  --font-mono:"SF Mono","JetBrains Mono",ui-monospace,monospace;
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;min-height:100dvh;background:var(--bg);color:var(--text);
  font-family:var(--font);font-size:16px;line-height:1.5;text-align:left;
  -webkit-font-smoothing:antialiased;-webkit-tap-highlight-color:transparent}
.ol-app{width:100%;max-width:var(--content-max);margin:0 auto;min-height:100dvh;
  display:flex;flex-direction:column;
  padding:calc(env(safe-area-inset-top) + var(--space-3)) var(--space-3)
    calc(env(safe-area-inset-bottom) + var(--space-3))}
.ol-top{display:flex;flex-direction:column;gap:var(--space-1)}
.ol-title{font-size:24px;font-weight:600;line-height:1.2;margin:0;color:var(--text)}
.ol-label{font-size:13px;font-weight:500;color:var(--text-muted);margin:0}
.ol-mid{flex:1;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:var(--space-3);min-height:0}
.ol-hero{font-family:var(--font-mono);font-size:48px;font-weight:700;line-height:1;
  text-align:center;font-variant-numeric:tabular-nums;letter-spacing:-0.02em;color:var(--text)}
.ol-hero.accent{color:var(--accent)}
.ol-chips{display:flex;flex-wrap:wrap;gap:var(--space-1);justify-content:center}
.ol-chip{display:inline-flex;align-items:center;min-height:32px;padding:0 var(--space-2);
  background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-pill);
  color:var(--text-muted);font-size:13px;font-weight:500}
.ol-chip.active{border-color:var(--accent);color:var(--text)}
.ol-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:var(--space-2);width:100%}
.ol-row{display:flex;align-items:center;gap:var(--space-2);background:var(--surface-2);
  border:1px solid var(--border);border-radius:var(--radius);padding:var(--space-2);
  min-height:52px;transition:opacity .12s ease,color .12s ease}
.ol-row.done{color:var(--text-muted);opacity:.6}
.ol-list{display:flex;flex-direction:column;gap:var(--space-1);width:100%;overflow:auto}
.ol-input{width:100%;height:48px;padding:0 var(--space-2);background:var(--surface-2);
  border:1px solid var(--border);border-radius:var(--radius);color:var(--text);
  font-family:var(--font);font-size:16px;outline:none;-webkit-appearance:none;appearance:none;
  transition:border-color .12s ease}
.ol-input::placeholder{color:var(--text-faint)}
.ol-input:focus{border-color:var(--accent)}
.ol-dock{position:sticky;bottom:0;margin-top:auto;padding-top:var(--space-2);
  display:flex;flex-direction:column;gap:var(--space-1);
  padding-bottom:env(safe-area-inset-bottom)}
.ol-btn{display:inline-flex;align-items:center;justify-content:center;gap:var(--space-1);
  width:100%;min-height:56px;padding:0 var(--space-3);border:0;border-radius:var(--radius);
  font-family:var(--font);font-size:16px;font-weight:600;line-height:1;cursor:pointer;
  user-select:none;transition:transform .08s ease,background-color .12s ease,opacity .12s ease}
.ol-btn:active{transform:scale(.98)}
.ol-btn-primary{background:var(--accent);color:var(--accent-ink)}
.ol-btn-secondary{background:transparent;border:1px solid var(--border);color:var(--text)}
.ol-btn-secondary:active{background:var(--surface-2)}
.ol-progress{width:100%;height:6px;border-radius:var(--radius-pill);background:var(--surface-2);
  overflow:hidden}
.ol-progress > i{display:block;height:100%;width:0;background:var(--accent);
  border-radius:var(--radius-pill);transition:width .2s ease}
.ol-fade{transition:opacity .15s ease}
.ol-checkbox{flex:0 0 auto;width:24px;height:24px;border-radius:6px;border:2px solid var(--border);
  display:inline-flex;align-items:center;justify-content:center}
.ol-checkbox.on{border-color:var(--accent);background:var(--accent)}
.ol-checkbox.on::after{content:"";width:10px;height:6px;border-left:2px solid var(--accent-ink);
  border-bottom:2px solid var(--accent-ink);transform:rotate(-45deg) translateY(-1px)}
@media (prefers-reduced-motion: reduce){*,*::before,*::after{transition-duration:.001ms !important}}
`;

export function htmlShell(opts: {
  title: string;
  accent: string;
  bodyHtml: string;
  script: string;
}): string {
  const { title, accent, bodyHtml, script } = opts;
  return (
    "<!doctype html>\n" +
    '<html lang="en">\n<head>\n<meta charset="utf-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n' +
    "<title>" +
    title +
    "</title>\n<style>" +
    BASE_CSS +
    "\n:root{--accent:" +
    accent +
    "}\n</style>\n</head>\n<body>\n" +
    bodyHtml +
    "\n<script>\n" +
    script +
    "\n</script>\n</body>\n</html>\n"
  );
}
