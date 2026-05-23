"use client";

// Left half of the result area: the deployed proof. A large QR rendered with
// qrcode, an open link button, and the live Cloud Run URL in mono as a fallback
// if scanning is slow. The preview on the right does not wait on any of this.

import QRCode from "qrcode";
import { useEffect, useRef } from "react";
import type { Deployment } from "@/lib/types";

export default function QrPanel({
  deployment,
  hasWinner,
}: {
  deployment?: Deployment;
  hasWinner: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!deployment?.url || !canvasRef.current) return;
    QRCode.toCanvas(canvasRef.current, deployment.url, {
      width: 240,
      margin: 1,
      color: { dark: "#0A0A0B", light: "#FFFFFF" },
      errorCorrectionLevel: "M",
    }).catch(() => {
      // canvas not ready; the URL text below is still the fallback
    });
  }, [deployment?.url]);

  if (deployment) {
    return (
      <>
        <div className="db-qr-tile">
          <canvas ref={canvasRef} width={240} height={240} />
        </div>
        <a className="db-open" href={deployment.url} target="_blank" rel="noreferrer">
          Open on this device
        </a>
        <div className="db-url">{deployment.url}</div>
        {deployment.fallback ? (
          <div className="db-deploy-meta warn">
            Live deploy degraded, serving the fallback URL. The preview on the right is the build.
          </div>
        ) : (
          <div className="db-deploy-meta">Deployed to {deployment.service} in the pool</div>
        )}
      </>
    );
  }

  if (hasWinner) {
    return (
      <>
        <div className="db-spinner" />
        <div className="db-waiting">
          <strong>Deploying to Cloud Run.</strong> The tool is already running in the preview
          on the right. The QR and link appear here when the service responds.
        </div>
      </>
    );
  }

  return (
    <div className="db-waiting">
      The QR code, an open link, and the live URL appear here once a winner is selected.
    </div>
  );
}
