"use client";

import { ArrowRight, BookOpen } from "lucide-react";
import Link from "next/link";
import { useId, useRef, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/cn";
import type { CurriculumSkill } from "@/lib/types";

const TRACKS = [
  { id: "backend", title: "Python & Backend", skills: ["programming-fundamentals", "python", "fastapi", "http"] },
  { id: "frontend", title: "Frontend Engineering", skills: ["typescript", "react"] },
  { id: "databases", title: "Databases", skills: ["sql"] },
  { id: "architecture", title: "Architecture & System Design", skills: ["system-design", "distributed-systems"] },
  { id: "operations", title: "DevOps & Security", skills: ["devops", "security"] },
  { id: "tooling", title: "Git & Linux", skills: ["git", "linux"] },
  { id: "senior", title: "Senior Engineering Skills", skills: ["testing", "senior-practices"] },
];

export function TrackExplorer({ skills }: { skills: CurriculumSkill[] }) {
  const tracks = TRACKS.filter((track) => skills.some((skill) => track.skills.includes(skill.slug)));
  const [selected, setSelected] = useState(tracks[0]?.id);
  const tabsRef = useRef<Array<HTMLButtonElement | null>>([]);
  const id = useId();
  const active = tracks.find((track) => track.id === selected) ?? tracks[0];

  if (!active) return null;

  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    switch (event.key) {
      case "ArrowRight": next = (index + 1) % tracks.length; break;
      case "ArrowLeft": next = (index - 1 + tracks.length) % tracks.length; break;
      case "Home": next = 0; break;
      case "End": next = tracks.length - 1; break;
      default: return;
    }
    event.preventDefault();
    setSelected(tracks[next].id);
    tabsRef.current[next]?.focus();
  }

  return (
    <div className="rounded-2xl border border-line p-5 sm:p-7">
      <div role="tablist" aria-label="Learning tracks" className="flex flex-wrap gap-2">
        {tracks.map((track, index) => (
          <button
            key={track.id}
            ref={(element) => { tabsRef.current[index] = element; }}
            type="button"
            role="tab"
            id={`${id}-tab-${track.id}`}
            aria-controls={`${id}-panel-${track.id}`}
            aria-selected={track.id === active.id}
            tabIndex={track.id === active.id ? 0 : -1}
            onClick={() => setSelected(track.id)}
            onKeyDown={(event) => navigate(event, index)}
            className={cn(
              "min-h-11 rounded-full border px-4 py-2 text-sm transition-colors",
              track.id === active.id
                ? "border-fg bg-fg font-medium text-canvas"
                : "border-line text-fg-muted hover:border-fg-subtle hover:bg-surface hover:text-fg",
            )}
          >
            {track.title}
          </button>
        ))}
      </div>
      {tracks.map((track) => (
        <div
          key={track.id}
          role="tabpanel"
          id={`${id}-panel-${track.id}`}
          aria-labelledby={`${id}-tab-${track.id}`}
          tabIndex={0}
          hidden={track.id !== active.id}
          className="mt-7 border-t border-line-subtle pt-7"
        >
          <h3 className="text-2xl font-semibold tracking-tight text-fg">{track.title}</h3>
          <p className="mt-2 text-sm leading-6 text-fg-muted">
            Explore a skill to see its topics, levels, and available practice.
          </p>
          <ul className="mt-5 flex flex-col gap-1">
            {skills.filter((skill) => track.skills.includes(skill.slug)).map((skill) => (
              <li key={skill.slug}>
                <Link
                  href={`/tracks/${skill.slug}`}
                  className="group -mx-2 flex items-start gap-3 rounded-xl px-2 py-3 transition-colors hover:bg-surface sm:items-center"
                >
                  <BookOpen className="mt-0.5 size-5 shrink-0 text-fg-muted sm:mt-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-medium text-fg">{skill.title}</span>
                    <span className="mt-1 block text-sm leading-6 text-fg-muted">{skill.summary}</span>
                  </span>
                  <ArrowRight className="mt-0.5 size-4 shrink-0 text-fg-subtle transition-colors group-hover:text-fg sm:mt-0" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
