"use client";

import { cn } from "@/lib/utils";

/** Numbered citation marker shaped like a Korean name seal (도장). */
export function Seal({
  n,
  active,
  onClick,
  label,
  className,
}: {
  n: number;
  active?: boolean;
  onClick?: () => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={cn("seal", className)}
      data-active={active ? "true" : undefined}
      onClick={onClick}
      aria-label={label ?? `Source ${n}`}
    >
      {n}
    </button>
  );
}

/** The HanRAG mark: 한 inside a seal. */
export function HanMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-[5px] border-2 border-seal font-serif text-[17px] font-bold text-seal",
        className,
      )}
    >
      한
    </span>
  );
}
