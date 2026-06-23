import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "A3 Coach",
  description: "Next.js frontend for A3 coach API",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
