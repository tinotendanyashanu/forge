"use client";

import { Menu, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

import { Brand } from "./brand";
import { SidebarNav } from "./nav";

function SidebarFooter({ collapsed }: { collapsed: boolean }) {
  if (collapsed) return null;
  return (
    <p className="px-2.5 text-xs leading-relaxed text-fg-subtle">
      FORGE 1.0 · local single-user build
    </p>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);
  const closeMobile = useCallback(() => {
    setMobileOpen(false);
    menuButtonRef.current?.focus();
  }, []);

  // ⌘B / Ctrl+B toggles the desktop sidebar.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleCollapsed();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleCollapsed]);

  // Mobile drawer: focus the close button, close on Escape, lock page scroll.
  useEffect(() => {
    if (!mobileOpen) return;
    closeButtonRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        closeMobile();
        return;
      }
      // Keep Tab focus inside the drawer while it is open.
      if (e.key !== "Tab" || !drawerRef.current) return;
      const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
        "a[href], button:not([disabled])",
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileOpen, closeMobile]);

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-[100] rounded-lg bg-fg px-3 py-2 text-sm font-medium text-canvas focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside
        aria-label="Sidebar"
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line-subtle bg-canvas py-3 transition-[width] duration-200 ease-out md:flex",
          collapsed ? "w-[60px] px-2.5" : "w-[244px] px-3",
        )}
      >
        <div
          className={cn(
            "mb-6 flex items-center",
            collapsed ? "flex-col gap-2" : "justify-between",
          )}
        >
          <Brand collapsed={collapsed} />
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            aria-keyshortcuts="Meta+B Control+B"
            title={collapsed ? "Expand sidebar (⌘B)" : "Collapse sidebar (⌘B)"}
            className="flex size-8 items-center justify-center rounded-lg text-fg-subtle transition-colors hover:bg-surface hover:text-fg"
          >
            {collapsed ? (
              <PanelLeftOpen className="size-[18px]" aria-hidden="true" />
            ) : (
              <PanelLeftClose className="size-[18px]" aria-hidden="true" />
            )}
          </button>
        </div>
        <div className="flex-1">
          <SidebarNav collapsed={collapsed} />
        </div>
        <SidebarFooter collapsed={collapsed} />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line-subtle bg-canvas px-3 md:hidden">
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
            className="flex size-10 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-surface hover:text-fg"
          >
            <Menu className="size-5" aria-hidden="true" />
          </button>
          <Brand />
        </header>

        <main id="main" tabIndex={-1} className="flex-1 outline-none">
          {children}
        </main>
      </div>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/70 animate-fade-in"
            onClick={closeMobile}
            aria-hidden="true"
          />
          <div
            ref={drawerRef}
            id="mobile-nav"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 left-0 flex w-[280px] max-w-[85vw] flex-col border-r border-line bg-canvas px-3 py-3 animate-slide-in"
          >
            <div className="mb-6 flex items-center justify-between">
              <Brand onNavigate={closeMobile} />
              <button
                ref={closeButtonRef}
                type="button"
                onClick={closeMobile}
                aria-label="Close navigation"
                className="flex size-10 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-surface hover:text-fg"
              >
                <X className="size-5" aria-hidden="true" />
              </button>
            </div>
            <div className="flex-1">
              <SidebarNav onNavigate={closeMobile} />
            </div>
            <SidebarFooter collapsed={false} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
