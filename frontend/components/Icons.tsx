// Small inline SVG icons (no icon dependency). All use `currentColor` so they inherit text
// color, and accept a className for sizing.

export function SparkIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M12 2l1.7 5.1a5 5 0 0 0 3.2 3.2L22 12l-5.1 1.7a5 5 0 0 0-3.2 3.2L12 22l-1.7-5.1a5 5 0 0 0-3.2-3.2L2 12l5.1-1.7a5 5 0 0 0 3.2-3.2L12 2z" />
    </svg>
  );
}

export function ArrowUpIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M12 19V5M6 11l6-6 6 6" />
    </svg>
  );
}

export function PlusIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function HeadsetIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M4 13a8 8 0 0 1 16 0M4 13v3a2 2 0 0 0 2 2h1v-5H6a2 2 0 0 0-2 2zm16 0v3a2 2 0 0 1-2 2h-1v-5h1a2 2 0 0 1 2 2z" />
    </svg>
  );
}

export function ThumbUpIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M7 10v11M2 13v6a2 2 0 0 0 2 2h12.5a2 2 0 0 0 2-1.6l1.3-7A2 2 0 0 0 17.8 10H14V5a2.5 2.5 0 0 0-2.5-2.5L7 10z" />
    </svg>
  );
}

export function ThumbDownIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M17 14V3M22 11V5a2 2 0 0 0-2-2H7.5a2 2 0 0 0-2 1.6l-1.3 7A2 2 0 0 0 6.2 14H10v5a2.5 2.5 0 0 0 2.5 2.5L17 14z" />
    </svg>
  );
}
