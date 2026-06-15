/**
 * LaTeX preprocessing utilities for remark-math compatibility.
 *
 * remark-math only understands $...$ and $$...$$ delimiters.
 * LLMs often output \(...\) and \[...\] which need conversion.
 * LLMs also commonly emit bare display formulas that need wrapping.
 */

type ProtectedContent = {
  text: string;
  restore: (value: string) => string;
};

const DISPLAY_LATEX_PATTERN =
  /\\(?:boxed|begin|end|nabla|frac|dfrac|tfrac|sum|prod|mathbb|mathcal|mathrm|operatorname|text|theta|pi|left|right|log|exp|cdot|tau|sim|tag|int|partial|sqrt|alpha|beta|gamma|delta|lambda|mu|sigma|epsilon|varepsilon|vec|hat|bar|min|max|Big|big|Bigr|biggr)\b/;

function protectMarkdownCode(content: string): ProtectedContent {
  const segments: string[] = [];
  const store = (match: string) => {
    const placeholder = `__AITUTOR_MARKDOWN_CODE_${segments.length}__`;
    segments.push(match);
    return placeholder;
  };

  const text = content
    .replace(/```[\s\S]*?```/g, store)
    .replace(/`[^`\n]*`/g, store);

  return {
    text,
    restore(value: string) {
      return segments.reduce(
        (result, segment, index) =>
          result.split(`__AITUTOR_MARKDOWN_CODE_${index}__`).join(segment),
        value,
      );
    },
  };
}

function protectDisplayMath(content: string): ProtectedContent {
  const segments: string[] = [];
  const text = content.replace(/\$\$[\s\S]*?\$\$/g, (match) => {
    const placeholder = `__AITUTOR_DISPLAY_MATH_${segments.length}__`;
    segments.push(match);
    return placeholder;
  });

  return {
    text,
    restore(value: string) {
      return segments.reduce(
        (result, segment, index) =>
          result.split(`__AITUTOR_DISPLAY_MATH_${index}__`).join(segment),
        value,
      );
    },
  };
}

function looksLikeDelimitedMath(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  if (/^\d+(\.\d+)?$/.test(trimmed)) return false;
  if (/[\u4e00-\u9fff]/.test(trimmed) && !/[\\{}^_=+|<>≤≥≠]/.test(trimmed)) return false;
  if (/^[A-Za-z]$/.test(trimmed)) return true;
  if (/^[A-Za-z][A-Za-z0-9_]*$/.test(trimmed)) {
    return (
      trimmed.length <= 3 ||
      /^(?:theta|alpha|beta|gamma|delta|lambda|sigma|epsilon|omega|pi|mu|tau)$/i.test(trimmed)
    );
  }
  if (/\\[A-Za-z]+/.test(trimmed)) return true;
  if (/[\^_{}]/.test(trimmed)) return true;
  if (/[=<>≤≥≠±×÷∑∏∫√∞∈∉⊂⊃∪∩∧∨¬⇒⇔]/.test(trimmed)) return true;
  if (/\b(?:log|sin|cos|tan|min|max|argmax|argmin|clip|softmax)\b/i.test(trimmed)) return true;
  return false;
}

function normalizeInlineDollarMath(content: string): string {
  const display = protectDisplayMath(content);
  const lines = display.text.split("\n").map((line) => {
    const dollarPositions: number[] = [];
    for (let i = 0; i < line.length; i += 1) {
      if (line[i] === "$" && (i === 0 || line[i - 1] !== "\\")) {
        dollarPositions.push(i);
      }
    }

    if (dollarPositions.length === 0) return line;

    let result = "";
    let cursor = 0;
    let index = 0;
    while (index < dollarPositions.length) {
      const open = dollarPositions[index];
      const close = dollarPositions[index + 1];
      if (close === undefined) {
        result += `${line.slice(cursor, open)}\\$`;
        cursor = open + 1;
        index += 1;
        continue;
      }

      const inner = line.slice(open + 1, close);
      if (looksLikeDelimitedMath(inner)) {
        result += `${line.slice(cursor, open)}$${inner.trim()}$`;
        cursor = close + 1;
        index += 2;
        continue;
      }

      result += `${line.slice(cursor, open)}\\$`;
      cursor = open + 1;
      index += 1;
    }

    return result + line.slice(cursor);
  });

  return display.restore(lines.join("\n"));
}

function normalizeSingleDollarDisplayBlocks(content: string): string {
  return content.replace(
    /(^|\n)[ \t]*\$\s*\n([\s\S]*?)\n[ \t]*\$(?=\s*(?:\n|$))/g,
    (_match, prefix: string, inner: string) => `${prefix}$$\n${inner}\n$$`,
  );
}

function normalizeBracketedDisplayBlocks(content: string): string {
  return content.replace(
    /(^|\n)\s*\[\s*([^\]\n]*(?:\\frac|\\beta|\\alpha|\\times|\\approx|\\text|\\sum|\\int|\\sigma|\\theta|\\sqrt)[^\]\n]*)\s*\]\s*(?=\n|$)/g,
    "$1$$\n$2\n$$",
  );
}

function isLatexTagLine(line: string): boolean {
  return /^\\tag\{[^}]+\}$/.test(line.trim());
}

function looksLikeStandaloneLatexLine(line: string, continuingBlock: boolean): boolean {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("$") || trimmed.startsWith("|")) return false;
  if (isLatexTagLine(trimmed)) return continuingBlock;
  if (trimmed.startsWith("\\") && DISPLAY_LATEX_PATTERN.test(trimmed)) return true;
  if (continuingBlock && DISPLAY_LATEX_PATTERN.test(trimmed)) return true;
  if (continuingBlock && /^[+\-=]?\s*\\/.test(trimmed)) return true;
  return false;
}

function countDisplayDelimiters(line: string): number {
  return (line.match(/(^|[^\\])\$\$/g) || []).length;
}

function wrapStandaloneLatexBlocks(content: string): string {
  const lines = content.split("\n");
  const normalizedLines: string[] = [];
  let pendingMathLines: string[] = [];
  let bufferedBlankLines: string[] = [];
  let inDisplayMath = false;

  const flushMathBlock = () => {
    if (pendingMathLines.length > 0) {
      normalizedLines.push("$$", ...pendingMathLines, "$$");
      pendingMathLines = [];
    }
    if (bufferedBlankLines.length > 0) {
      normalizedLines.push(...bufferedBlankLines);
      bufferedBlankLines = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    const displayDelimiterCount = countDisplayDelimiters(line);

    if (inDisplayMath || displayDelimiterCount > 0) {
      flushMathBlock();
      normalizedLines.push(line);
      if (displayDelimiterCount % 2 === 1) {
        inDisplayMath = !inDisplayMath;
      }
      continue;
    }

    if (!trimmed) {
      if (pendingMathLines.length > 0) {
        bufferedBlankLines.push(line);
      } else {
        normalizedLines.push(line);
      }
      continue;
    }

    const tagOnly = isLatexTagLine(trimmed);
    const latexLine = looksLikeStandaloneLatexLine(trimmed, pendingMathLines.length > 0);
    if (latexLine || (tagOnly && pendingMathLines.length > 0)) {
      if (pendingMathLines.length > 0 && bufferedBlankLines.length > 0 && !tagOnly) {
        flushMathBlock();
      } else if (tagOnly) {
        bufferedBlankLines = [];
      }
      pendingMathLines.push(trimmed);
      continue;
    }

    flushMathBlock();
    normalizedLines.push(line);
  }

  flushMathBlock();
  return normalizedLines.join("\n");
}

function sanitizeMathSegment(segment: string): string {
  return segment.replace(/\|/g, " \\vert ");
}

function protectMathPipes(content: string): string {
  return content
    .replace(/\$\$([\s\S]+?)\$\$/g, (_match, inner: string) => `$$${sanitizeMathSegment(inner)}$$`)
    .replace(/\$([^$\n]+?)\$/g, (_match, inner: string) => `$${sanitizeMathSegment(inner)}$`);
}

/**
 * Convert LaTeX delimiters from \(...\) and \[...\] to $...$ and $$...$$
 * so remark-math can parse them.
 */
export function convertLatexDelimiters(content: string): string {
  if (!content) return content;

  let result = content;

  // Handle $$ wrapped \( ... \) — strip inner delimiters
  result = result.replace(
    /\$\$\s*\\\(([\s\S]*?)\\\)\s*\$\$/g,
    (_match, expr) => `\n$$\n${expr}\n$$\n`,
  );

  // Convert \[...\] to $$...$$ (block math)
  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_match, expr) => {
    return `\n$$\n${expr}\n$$\n`;
  });

  // Convert \(...\) to $...$ (inline math)
  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_match, expr) => {
    return `$${expr}$`;
  });

  result = result.replace(/\n{3,}/g, "\n\n");
  return result;
}

/**
 * Full preprocessing pipeline for assistant markdown with LaTeX support.
 * Apply this before passing content to ReactMarkdown with remark-math.
 */
export function preprocessAssistantMarkdown(content: string): string {
  if (!content) return "";

  const protectedCode = protectMarkdownCode(String(content));
  let result = protectedCode.text;

  result = convertLatexDelimiters(result);
  result = normalizeSingleDollarDisplayBlocks(result);
  result = normalizeBracketedDisplayBlocks(result);
  result = wrapStandaloneLatexBlocks(result);
  result = normalizeInlineDollarMath(result);
  result = protectMathPipes(result);
  result = result.replace(/\n{3,}/g, "\n\n");

  return protectedCode.restore(result);
}

/**
 * Backward-compatible alias used by older renderers.
 */
export function processMarkdownContent(content: string): string {
  return preprocessAssistantMarkdown(content);
}
