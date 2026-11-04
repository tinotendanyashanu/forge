"use client";

import Editor, { loader, type OnMount } from "@monaco-editor/react";
import { Keyboard, Type } from "lucide-react";
import { useEffect, useRef, useState } from "react";

// Monaco is served from this app's origin (scripts/copy-monaco.mjs), not a CDN.
loader.config({ paths: { vs: "/monaco/vs" } });

const PREF_KEY = "forge:plain-editor"; // shared with the coding lab editor

const LANGUAGES: Record<string, string> = {
  py: "python", ts: "typescript", tsx: "typescript", js: "javascript", mjs: "javascript", json: "json",
  md: "markdown", sql: "sql", css: "css", html: "html", yml: "yaml", yaml: "yaml", toml: "ini", ini: "ini", cfg: "ini",
};

export function languageOf(path: string): string {
  return LANGUAGES[path.split(".").pop()?.toLowerCase() ?? ""] ?? "plaintext";
}

export interface EditorCommands {
  save: () => void;
  run: () => void;
  submit: () => void;
}

/**
 * Multi-file Monaco editor. Each path keeps its own model, so undo history
 * survives switching tabs. A plain-text editor is available for screen
 * readers and keyboard-only use.
 */
export function FileEditor({
  path,
  value,
  onChange,
  commands,
  readOnly = false,
  revealLine,
}: {
  path: string;
  value: string;
  onChange: (value: string) => void;
  commands: EditorCommands;
  readOnly?: boolean;
  revealLine?: { line: number; nonce: number } | null;
}) {
  const [plain, setPlain] = useState(false);
  const cmds = useRef(commands);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  useEffect(() => {
    cmds.current = commands;
  }, [commands]);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- read a stored preference after mount
      setPlain(localStorage.getItem(PREF_KEY) === "1");
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    const ed = editorRef.current;
    if (!ed || !revealLine) return;
    ed.revealLineInCenter(revealLine.line);
    ed.setPosition({ lineNumber: revealLine.line, column: 1 });
    ed.focus();
  }, [revealLine, path]);

  function togglePlain() {
    setPlain((p) => {
      try {
        localStorage.setItem(PREF_KEY, p ? "0" : "1");
      } catch {
        /* keep the in-memory choice */
      }
      return !p;
    });
  }

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => cmds.current.save());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => cmds.current.run());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Enter, () => cmds.current.submit());
  };

  const label = `Editing ${path}`;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-line-subtle px-3 py-1">
        <span className="truncate font-mono text-[11px] text-fg-subtle">{languageOf(path)}</span>
        <button
          type="button"
          onClick={togglePlain}
          aria-pressed={plain}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] text-fg-muted hover:bg-surface hover:text-fg"
        >
          {plain ? <Keyboard className="size-3.5" aria-hidden="true" /> : <Type className="size-3.5" aria-hidden="true" />}
          {plain ? "Code editor" : "Plain text editor"}
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {plain ? (
          <textarea
            aria-label={label}
            value={value}
            readOnly={readOnly}
            spellCheck={false}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              const mod = e.metaKey || e.ctrlKey;
              if (e.key === "Tab" && !e.shiftKey && !readOnly) {
                e.preventDefault();
                const t = e.currentTarget;
                const { selectionStart: s, selectionEnd: end } = t;
                onChange(`${value.slice(0, s)}    ${value.slice(end)}`);
                requestAnimationFrame(() => t.setSelectionRange(s + 4, s + 4));
              } else if (e.key === "Escape") {
                e.currentTarget.blur();
              } else if (mod && e.key.toLowerCase() === "s") {
                e.preventDefault();
                cmds.current.save();
              } else if (mod && e.key === "Enter") {
                e.preventDefault();
                if (e.shiftKey) cmds.current.submit();
                else cmds.current.run();
              }
            }}
            className="block h-full w-full resize-none bg-canvas px-4 py-3 font-mono text-[13px] leading-6 text-fg focus:outline-none"
          />
        ) : (
          <Editor
            height="100%"
            path={path}
            language={languageOf(path)}
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
              lineHeight: 21,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              tabSize: path.endsWith(".py") ? 4 : 2,
              insertSpaces: true,
              renderLineHighlight: "line",
              padding: { top: 10, bottom: 10 },
              readOnly,
              ariaLabel: label,
              accessibilitySupport: "auto",
              automaticLayout: true,
            }}
          />
        )}
      </div>
      <p className="border-t border-line-subtle px-3 py-1 text-[10.5px] text-fg-subtle">
        ⌘/Ctrl+S save · ⌘/Ctrl+Enter run tests · ⌘/Ctrl+Shift+Enter submit · {plain ? "Esc then Tab leaves the editor" : "Ctrl+M toggles Tab focus moving"}
      </p>
    </div>
  );
}
