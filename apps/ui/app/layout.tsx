import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "DB4LAW Vault Reader",
  description: "Read-only browser for DB4LAW markdown vault",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
