import type { Metadata } from "next";
import { DeskShell } from "@/components/shell/DeskShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trade Desk",
  description: "Model processing pipeline and trade verdicts",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <DeskShell>{children}</DeskShell>
      </body>
    </html>
  );
}
