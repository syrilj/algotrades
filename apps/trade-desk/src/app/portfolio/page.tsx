import Link from "next/link";

import { PortfolioDesk } from "@/components/portfolio/PortfolioDesk";

export default function PortfolioPage() {
  return (
    <>
      <div className="td-page pb-0">
        <Link href="/positions?view=portfolio" className="td-btn td-btn-ghost">
          Back to Positions · Portfolio tab
        </Link>
      </div>
      <PortfolioDesk />
    </>
  );
}
