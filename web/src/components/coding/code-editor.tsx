"use client";

import Editor, { loader, type OnMount } from "@monaco-editor/react";
import { Keyboard, Type } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import type { CodeLanguage } from "@/lib/types";

// Monaco is served from this app's origin (scripts/copy-monaco.mjs), not a CDN.
loader.config({ paths: { vs: "/monaco/vs" } });

const PREF_KEY = "forge:plain-editor";

function readPref(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) === "1";
  } catch {
    return false;
  }
}

export function CodeEditor({
  value,
  language,
  onChange,
  onRun,
  onSubmit,
  label,
  height = 460,
  readOnly = false,
}: {
  value: string;
  language: CodeLanguage;
  onChange: (code: string) => void;
  onRun?: () => void;
  onSubmit?: () => void;
  label: string;
  height?: number;
  readOnly?: boolean;
}) {
  const [plain, setPlain] = useState(false);
  const runRef = useRef(onRun);
  const submitRef = useRef(onSubmit);
  useEffect(() => {
    runRef.current = onRun;
    submitRef.current = onSubmit;
  }, [onRun, onSubmit]);

  useEffect(() => {
    // Read the stored preference after mount to avoid a hydration mismatch.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPlain(readPref());
  }, []);

  function togglePlain() {
    setPlain((p) => {
      try {
        localStorage.setItem(PREF_KEY, p ? "0" : "1");
      } catch {
        /* storage unavailable: keep the in-memory choice */
      }
      return !p;
    });
  }

  const onMount: OnMount = (editor, monaco) => {
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => runRef.current?.());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Enter, () => submitRef.current?.());
  };

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-canvas focus-within:border-neutral-500">
      <div className="flex items-center justify-between border-b border-line-subtle px-3 py-1.5">
        <span className="font-mono text-xs text-fg-subtle">{language}</span>
        <button
          type="button"
          onClick={togglePlain}
          aria-pressed={plain}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-fg-muted hover:bg-surface hover:text-fg"
        >
          {plain ? <Keyboard className="size-3.5" aria-hidden="true" /> : <Type className="size-3.5" aria-hidden="true" />}
          {plain ? "Use code editor" : "Use plain text editor"}
        </button>
      </div>
      {plain ? (
        <textarea
          aria-label={label}
          value={value}
          readOnly={readOnly}
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Tab" && !e.shiftKey && !readOnly) {
              // Indent with 4 spaces; Esc then Tab moves focus out, as documented below.
              e.preventDefault();
              const t = e.currentTarget;
              const { selectionStart: s, selectionEnd: end } = t;
              const next = `${value.slice(0, s)}    ${value.slice(end)}`;
              onChange(next);
              requestAnimationFrame(() => t.setSelectionRange(s + 4, s + 4));
            } else if (e.key === "Escape") {
              e.currentTarget.blur();
            } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              if (e.shiftKey) {
                onSubmit?.();
              } else {
                onRun?.();
              }
            }
          }}
          style={{ height }}
          className={cn(
            "block w-full resize-y bg-canvas px-4 py-3 font-mono text-[13px] leading-6 text-fg focus:outline-none",
          )}
        />
      ) : (
        <Editor
          height={height}
          language={language}
          value={value}
          theme="forge"
          onChange={(v) => onChange(v ?? "")}
          onMount={onMount}
          beforeMount={(monaco) => {
            monaco.editor.defineTheme("forge", {
              base: "vs-dark",
              inherit: true,
              rules: [
                { token: "comment", foreground: "737373", fontStyle: "italic" },
                { token: "keyword", foreground: "fafafa", fontStyle: "bold" },
                { token: "string", foreground: "d4d4d4" },
                { token: "number", foreground: "e5e5e5" },
              ],
              colors: {
                "editor.background": "#0a0a0a",
                "editor.foreground": "#fafafa",
                "editorLineNumber.foreground": "#525252",
                "editorLineNumber.activeForeground": "#a3a3a3",
                "editor.lineHighlightBackground": "#171717",
                "editor.selectionBackground": "#404040",
                "editorCursor.foreground": "#fafafa",
                "editorIndentGuide.background1": "#262626",
                "editorWidget.background": "#171717",
                "editorWidget.border": "#303030",
              },
            });
          }}
          loading={<div className="p-4 text-sm text-fg-subtle">Loading editor…</div>}
          options={{
            fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
            fontSize: 13,
            lineHeight: 22,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            tabSize: language === "python" ? 4 : 2,
            insertSpaces: true,
            autoIndent: "full",
            renderLineHighlight: "line",
            padding: { top: 12, bottom: 12 },
            readOnly,
            ariaLabel: label,
            accessibilitySupport: "auto",
            tabFocusMode: false,
            automaticLayout: true,
          }}
        />
      )}
      <p className="border-t border-line-subtle px-3 py-1.5 text-[11px] text-fg-subtle">
        ⌘/Ctrl+Enter run tests · ⌘/Ctrl+Shift+Enter submit ·{" "}
        {plain ? "Esc then Tab leaves the editor" : "Ctrl+M toggles Tab-key focus moving"}
      </p>
    </div>
  );
}
