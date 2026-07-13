"use client";

import { Suspense } from "react";
import { GammaExposureDesk } from "@/components/gamma/GammaExposureDesk";

export const dynamic = "force-dynamic";

export default function GammaPage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <div className="td-panel p-3">Loading gamma desk…</div>
        </div>
      }
    >
      <GammaExposureDesk />
    </Suspense>
  );
}
