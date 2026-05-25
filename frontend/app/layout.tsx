import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Conversational Data Analysis System",
  description: "AI-powered data assistant. Clean, profile, and perform multi-turn queries on your CSV files.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
