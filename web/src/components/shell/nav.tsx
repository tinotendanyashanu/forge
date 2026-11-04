"use client";

import {
  BookOpen,
  CalendarCheck,
  ChartLine,
  FolderGit2,
  LayoutDashboard,
  Network,
  Siren,
  BriefcaseBusiness,
  MessagesSquare,
  Route,
  SearchCheck,
  SquareCode,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { cn } from "@/lib/cn";

interface NavItem {
  href: "/" | "/learn" | "/tracks" | "/lab" | "/workspace" | "/design" | "/ops" | "/career" | "/interview" | "/review" | "/gaps" | "/progress";
  label: string;
  icon: LucideIcon;
  /** Path prefixes that mark this item active. */
  matches: string[];
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, matches: [] },
  { href: "/learn", label: "Learning path", icon: Route, matches: ["/learn"] },
  {
    href: "/tracks",
    label: "Skills",
    icon: BookOpen,
    matches: ["/tracks", "/assessments"],
  },
  { href: "/lab", label: "Coding lab", icon: SquareCode, matches: ["/lab"] },
  { href: "/workspace", label: "Workspace", icon: FolderGit2, matches: ["/workspace"] },
  { href: "/design", label: "Design lab", icon: Network, matches: ["/design"] },
  { href: "/ops", label: "FORGE OPS", icon: Siren, matches: ["/ops"] },
  { href: "/career", label: "Career", icon: BriefcaseBusiness, matches: ["/career"] },
  { href: "/interview", label: "Interview", icon: MessagesSquare, matches: ["/interview"] },
  { href: "/review", label: "Review", icon: CalendarCheck, matches: ["/review"] },
  { href: "/gaps", label: "Gaps", icon: SearchCheck, matches: ["/gaps"] },
  { href: "/progress", label: "Progress", icon: ChartLine, matches: ["/progress"] },
];

function isActive(item: NavItem, pathname: string | null) {
  if (pathname === null) return false;
  if (item.href === "/") return pathname === "/";
  return item.matches.some((m) => pathname === m || pathname.startsWith(`${m}/`));
}

interface NavListProps {
  collapsed?: boolean;
  onNavigate?: () => void;
}

function NavList({
  collapsed = false,
  onNavigate,
  pathname,
}: NavListProps & { pathname: string | null }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {NAV_ITEMS.map((item) => {
        const active = isActive(item, pathname);
        const Icon = item.icon;
        return (
          <li key={item.href} className="group/nav relative">
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm transition-colors duration-150",
                active
                  ? "bg-surface-hover font-medium text-fg"
                  : "text-fg-muted hover:bg-surface hover:text-fg",
                collapsed && "justify-center px-0",
              )}
            >
              <Icon className="size-[18px] shrink-0" aria-hidden="true" />
              <span className={cn(collapsed && "sr-only")}>{item.label}</span>
            </Link>
            {collapsed ? (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 left-full z-50 ml-3 -translate-y-1/2 rounded-md border border-line bg-surface-raised px-2 py-1 text-xs whitespace-nowrap text-fg opacity-0 shadow-lg shadow-black/40 transition-opacity duration-150 group-hover/nav:opacity-100 group-focus-within/nav:opacity-100"
              >
                {item.label}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function ActiveNavList(props: NavListProps) {
  const pathname = usePathname();
  return <NavList {...props} pathname={pathname} />;
}

/**
 * `usePathname` suspends while prerendering routes with unknown dynamic
 * params, so the active state streams in behind a fallback that renders the
 * same links without highlighting.
 */
export function SidebarNav(props: NavListProps) {
  return (
    <nav aria-label="Primary">
      <Suspense fallback={<NavList {...props} pathname={null} />}>
        <ActiveNavList {...props} />
      </Suspense>
    </nav>
  );
}
