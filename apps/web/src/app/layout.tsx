import type { Metadata } from "next";
import { Bodoni_Moda, Geist_Mono, Outfit } from "next/font/google";
import { PRODUCT_NAME } from "@/lib/brand";
import "./globals.css";

// The owner's saved references: an elegant high-contrast serif for the logo and big headlines
// (Maison Salome / Runiga look-alike) and a clean geometric sans for interface text.
const display = Bodoni_Moda({
  variable: "--font-display",
  subsets: ["latin"],
  axes: ["opsz"],
});

const ui = Outfit({
  variable: "--font-ui",
  subsets: ["latin"],
});

const mono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: `${PRODUCT_NAME} - pull request reviews`,
  description:
    "Lyvern reviews pull requests with inline comments, change requests and merge-conflict help, and approves only when nothing is left to fix.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${ui.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <div className="silk" aria-hidden />
        {children}
      </body>
    </html>
  );
}
