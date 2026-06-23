import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EduFlowGraph",
  description: "Memory-augmented AI tutoring engine with multi-dimensional learner profiling",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
