"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { preprocessAssistantMarkdown } from "@/lib/latex";

// ── Component ────────────────────────────────────────────────────────

const baseComponents = {
  h1: ({ node, ...props }: any) => (
    <h1 className="mb-4 mt-7 text-[24px] font-semibold tracking-tight first:mt-0" {...props} />
  ),
  h2: ({ node, ...props }: any) => (
    <h2 className="mb-3 mt-7 text-[20px] font-semibold tracking-tight first:mt-0" {...props} />
  ),
  h3: ({ node, ...props }: any) => (
    <h3 className="mb-2 mt-5 text-[17px] font-semibold tracking-tight first:mt-0" {...props} />
  ),
  p: ({ node, ...props }: any) => <p className="mb-4 last:mb-0" {...props} />,
  ul: ({ node, ...props }: any) => <ul className="mb-4 ml-5 list-disc space-y-2" {...props} />,
  ol: ({ node, ...props }: any) => <ol className="mb-4 ml-5 list-decimal space-y-2" {...props} />,
  li: ({ node, ...props }: any) => <li className="pl-1" {...props} />,
  blockquote: ({ node, ...props }: any) => (
    <blockquote className="mb-5 border-l-2 border-[var(--border)] pl-5 italic text-[var(--muted-foreground)]" {...props} />
  ),
  hr: ({ node, ...props }: any) => <hr className="my-6 border-[var(--border)]/70" {...props} />,
  code: ({ node, className, children, ...props }: any) => {
    const isBlock = String(className || "").includes("language-");
    if (isBlock) {
      return <code className={`${className || ""} text-[13px] leading-6`} {...props}>{children}</code>;
    }
    return <code className="rounded-lg bg-[var(--secondary)] px-1.5 py-1 text-[0.9em]" {...props}>{children}</code>;
  },
  pre: ({ node, ...props }: any) => (
    <pre className="mb-4 overflow-x-auto rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-[13px] leading-6 shadow-sm" {...props} />
  ),
  table: ({ node, ...props }: any) => (
    <div className="mb-5 overflow-x-auto rounded-2xl border border-[var(--border)]">
      <table className="min-w-full border-collapse text-left text-[14px] leading-6" {...props} />
    </div>
  ),
  thead: ({ node, ...props }: any) => <thead className="bg-[var(--secondary)]/60" {...props} />,
  th: ({ node, ...props }: any) => <th className="border-b border-[var(--border)] px-4 py-3 font-medium" {...props} />,
  td: ({ node, ...props }: any) => <td className="border-b border-[var(--border)]/70 px-4 py-3 align-top" {...props} />,
  a: ({ node, ...props }: any) => <a className="underline underline-offset-4" target="_blank" rel="noreferrer" {...props} />,
  strong: ({ node, ...props }: any) => <strong className="font-semibold" {...props} />,
};

export function AssistantMarkdown({ content }: { content: string }) {
  const processedContent = useMemo(() => preprocessAssistantMarkdown(content), [content]);

  return (
    <div className="assistant-markdown text-[15px] leading-7 text-[var(--foreground)]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={baseComponents}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}
