import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import { preprocessAssistantMarkdown } from "./latex.ts";

test("preprocessAssistantMarkdown keeps spaced one-letter inline math renderable", () => {
  const output = preprocessAssistantMarkdown("对于每个 prompt $ q $ 及其 $ G $ 个样本");

  assert.equal(output.includes("`$`"), false);
  assert.match(output, /\$q\$/);
  assert.match(output, /\$G\$/);
});

test("preprocessAssistantMarkdown wraps raw display LaTeX and attaches a trailing tag", () => {
  const input = [
    "目标函数",
    "",
    "\\mathcal{J}_{\\text{GRPO}}(\\theta) = \\mathbb{E}_{q \\sim P(Q)} \\left[ \\frac{1}{G}\\sum_{i=1}^G A_i \\right]",
    "",
    "\\tag{5}",
  ].join("\n");

  const output = preprocessAssistantMarkdown(input);

  assert.match(output, /\$\$\n\\mathcal\{J\}_\{\\text\{GRPO\}\}/);
  assert.match(output, /\\tag\{5\}\n\$\$/);
});

test("preprocessAssistantMarkdown does not rewrite code spans or fences", () => {
  const input = [
    "这里的 `$ q $` 是代码。",
    "",
    "```tex",
    "\\mathcal{J}(\\theta)",
    "```",
  ].join("\n");

  assert.equal(preprocessAssistantMarkdown(input), input);
});

test("preprocessed assistant math renders through KaTeX", () => {
  const input = [
    "对于每个 prompt $ q $ 及其 $ G $ 个样本，GRPO 的损失函数是：",
    "",
    "\\mathcal{J}_{\\text{GRPO}}(\\theta) = \\mathbb{E}_{q \\sim P(Q)} \\left[ \\frac{1}{G}\\sum_{i=1}^G A_i \\right]",
    "",
    "\\tag{5}",
  ].join("\n");

  const html = renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      {
        remarkPlugins: [remarkMath],
        rehypePlugins: [rehypeKatex],
      },
      preprocessAssistantMarkdown(input),
    ),
  );

  assert.match(html, /class="[^"]*katex/);
  assert.match(html, /class="[^"]*katex-display/);
  assert.doesNotMatch(html, /katex-error/);
  assert.doesNotMatch(html, /<code>\$<\/code>/);
});
