import { Fragment, type ReactNode } from "react";

import { CodeBlock } from "@/components/ui/rich-text";

/**
 * Minimal Markdown for project content: headings, paragraphs, lists, tables,
 * fenced code, **bold**, *italic* and `code`. Everything renders as text,
 * never as HTML.
 */
type Block =
  | { kind: "code"; lang: string | null; code: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "para"; text: string };

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

function parse(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^```([\w+-]*)\s*$/);
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push({ kind: "code", lang: fence[1] || null, code: body.join("\n") });
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      i++;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const header = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const bullet = /^\s*[*-]\s+(.*)$/;
    const numbered = /^\s*\d+\.\s+(.*)$/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const re = ordered ? numbered : bullet;
      const items: string[] = [];
      while (i < lines.length && (re.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        const m = lines[i].match(re);
        if (m) items.push(m[1]);
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    if (!line.trim()) {
      i++;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*[*-]\s|\s*\d+\.\s|\s*\|)/.test(lines[i])) {
      para.push(lines[i++].trim());
    }
    if (!para.length) para.push(lines[i++].trim());
    blocks.push({ kind: "para", text: para.join(" ") });
  }
  return blocks;
}

/** Stable id for heading anchors. */
export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function Inline({ text }: { text: string }): ReactNode {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("`") && p.endsWith("`") && p.length > 2) {
          return (
            <code key={i} className="rounded border border-line-subtle bg-surface-raised px-1 py-px font-mono text-[0.88em] text-fg">
              {p.slice(1, -1)}
            </code>
          );
        }
        if (p.startsWith("**") && p.endsWith("**") && p.length > 4) return <strong key={i} className="font-semibold text-fg">{p.slice(2, -2)}</strong>;
        if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>;
        return <Fragment key={i}>{p}</Fragment>;
      })}
    </>
  );
}

/**
 * ``prose`` renders long-form reading (lessons): real h2/h3 headings with
 * anchors and larger body text. Content is still rendered as text only.
 */
export function Markdown({ text, className, prose = false }: { text: string; className?: string; prose?: boolean }) {
  const base = prose
    ? "flex flex-col gap-4 text-[15px] leading-7 text-fg-muted"
    : "flex flex-col gap-3 text-sm leading-relaxed text-fg-muted";
  return (
    <div className={className ?? base}>
      {parse(text).map((b, i) => {
        switch (b.kind) {
          case "code":
            return <CodeBlock key={i} code={b.code} language={b.lang} />;
          case "heading":
            if (prose && b.level <= 3) {
              const Tag = b.level <= 2 ? "h2" : "h3";
              return (
                <Tag
                  key={i}
                  id={slugify(b.text)}
                  className={
                    b.level <= 2
                      ? "mt-8 scroll-mt-24 text-xl font-semibold tracking-tight text-fg first:mt-0"
                      : "mt-4 text-base font-medium text-fg"
                  }
                >
                  <Inline text={b.text} />
                </Tag>
              );
            }
            return (
              <p key={i} className="mt-1 text-[13px] font-medium text-fg">
                <Inline text={b.text} />
              </p>
            );
          case "list": {
            const Tag = b.ordered ? "ol" : "ul";
            return (
              <Tag key={i} className={b.ordered ? "ml-5 list-decimal space-y-1" : "ml-5 list-disc space-y-1"}>
                {b.items.map((it, j) => <li key={j}><Inline text={it} /></li>)}
              </Tag>
            );
          }
          case "table":
            return (
              <div key={i} className="overflow-x-auto rounded-lg border border-line">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-surface-raised text-fg-subtle">
                    <tr>{b.header.map((h, j) => <th key={j} className="px-3 py-2 font-medium"><Inline text={h} /></th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-line-subtle">
                    {b.rows.map((r, j) => (
                      <tr key={j}>{r.map((c, k) => <td key={k} className="px-3 py-2 align-top text-fg-muted"><Inline text={c} /></td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return <p key={i}><Inline text={b.text} /></p>;
        }
      })}
    </div>
  );
}
