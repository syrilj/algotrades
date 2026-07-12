import { PageHeader } from "@/components/shell/PageHeader";
import { ScanDesk } from "@/components/scan/ScanDesk";

export const dynamic = "force-dynamic";

export default function ScanPage() {
  return (
    <div className="td-page">
      <PageHeader
        title="VPA + VWAP Scan"
        description="Coulling effort/result + swing VWAP DNA for the book. Use CALL bias names → Live/Options with WINNER equity (v39b). Research bias only — size via Live adapt + paper ledger."
        meta={
          <span className="td-chip td-chip--warn">scan bias · live sizes</span>
        }
      />
      <ScanDesk />
    </div>
  );
}
