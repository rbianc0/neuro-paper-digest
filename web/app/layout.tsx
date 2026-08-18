import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Neurofeed",
  description: "A finite weekly neuroscience literature digest shaped by your research profile and Bluesky scientific network.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
