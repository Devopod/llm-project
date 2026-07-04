import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AstraDev - Autonomous AI Software Engineer",
  description: "Build software autonomously with AI agents that plan, code, test, and deploy.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-gray-950 text-white min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
