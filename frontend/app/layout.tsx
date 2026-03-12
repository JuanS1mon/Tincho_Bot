import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tincho Bot — Dashboard",
  description: "Dashboard del agente autónomo de trading",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
