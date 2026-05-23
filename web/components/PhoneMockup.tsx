"use client";

// The phone mockup. A realistic portrait device (9 to 19.5) that keeps its
// aspect ratio, scaled to fit the panel height with margin, centered, never
// stretched. The iframe renders the winning tool at a true 390px logical width,
// scaled to the device, so the preview matches what a real phone shows. This is
// instant from the HTML string and never waits on Cloud Run.

import { useEffect, useRef, useState } from "react";

const LOGICAL_WIDTH = 390;

export default function PhoneMockup({ html }: { html?: string }) {
  const screenRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [logicalHeight, setLogicalHeight] = useState(845);

  useEffect(() => {
    const el = screenRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w <= 0 || h <= 0) return;
      const s = w / LOGICAL_WIDTH;
      setScale(s);
      // Logical height so the scaled iframe exactly fills the screen height.
      setLogicalHeight(h / s);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="db-phone-wrap">
      <div className="db-device">
        <div className="db-device-screen" ref={screenRef}>
          {html ? (
            <iframe
              className="db-device-iframe"
              title="Winning tool preview"
              sandbox="allow-scripts allow-forms allow-pointer-lock"
              srcDoc={html}
              style={{
                width: LOGICAL_WIDTH + "px",
                height: logicalHeight + "px",
                transform: "scale(" + scale + ")",
                transformOrigin: "top left",
              }}
            />
          ) : (
            <div className="db-device-idle">Winner preview appears here</div>
          )}
        </div>
      </div>
    </div>
  );
}
