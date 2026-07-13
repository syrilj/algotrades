import { Suspense } from "react";
import { ModelsCatalogView } from "@/components/models/ModelsCatalogView";

export const metadata = {
  title: "Models · Trade Desk",
  description: "All discovered model versions (engines + non-engines).",
};

export default function ModelsCatalogPage() {
  return (
    <Suspense
      fallback={
        <div className="td-page">
          <p className="td-muted">Discovering models…</p>
        </div>
      }
    >
      <div className="td-page">
        <ModelsCatalogView showHeader />
      </div>
    </Suspense>
  );
}
