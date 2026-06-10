import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Archon — Nimbus Support",
  description: "Guarded, supervised customer-support agent with human-in-the-loop.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans">{children}</body>
    </html>
  );
}
