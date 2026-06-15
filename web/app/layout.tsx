import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EduFlowGraph 导师系统",
  description: "面向 EduFlowGraph 记忆机制演示的 DeepTutor 风格前端",
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
