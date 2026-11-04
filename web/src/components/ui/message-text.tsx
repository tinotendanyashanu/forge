import { CodeBlock, InlineText } from "@/components/ui/rich-text";

type Block = { kind: "code"; lang: string | null; code: string } | { kind: "text"; text: string };

function parse(source: string): Block[] {
  const blocks: Block[] = [];
  const fence = /```([\w+-]*)\n([\s\S]*?)```/g;
  let last = 0;
  for (let m = fence.exec(source); m; m = fence.exec(source)) {
    if (m.index > last) blocks.push({ kind: "text", text: source.slice(last, m.index) });
    blocks.push({ kind: "code", lang: m[1] || null, code: m[2].replace(/\n$/, "") });
    last = m.index + m[0].length;
  }
  if (last < source.length) blocks.push({ kind: "text", text: source.slice(last) });
  return blocks;
}

/**
 * Renders chat text: paragraphs, `inline code` and fenced code blocks.
 * Content is always treated as text, never as HTML.
 */
export function MessageText({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-3">
      {parse(text).map((block, i) =>
        block.kind === "code" ? (
          <CodeBlock key={i} code={block.code} language={block.lang} />
        ) : (
          block.text
            .split(/\n{2,}/)
            .map((p) => p.trim())
            .filter(Boolean)
            .map((p, j) => (
              <p key={`${i}-${j}`} className="whitespace-pre-wrap">
                <InlineText text={p} />
              </p>
            ))
        ),
      )}
    </div>
  );
}
