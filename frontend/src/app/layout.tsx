import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Venture/Lab — Startup Research Studio",
  description:
    "Validate your startup idea and turn it into a researched, investor-ready business plan.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
