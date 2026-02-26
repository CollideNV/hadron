import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

export default function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      <header className="bg-bg/80 backdrop-blur-md border-b border-border-subtle px-6 py-3 flex items-center justify-between sticky top-0 z-40">
        <Link
          to="/"
          className="flex items-center gap-2.5 no-underline text-text"
        >
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="6" fill="#122f32" />
            <path
              d="M8 8h4v4H8V8zm8 0h4v4h-4V8zm-4 4h4v4h-4v-4zm-4 4h4v4H8v-4zm8 0h4v4h-4v-4z"
              fill="#37e284"
              opacity="0.9"
            />
          </svg>
          <span className="text-base font-semibold tracking-tight text-text">
            Hadron
          </span>
          <span className="text-[10px] text-text-dim font-mono ml-1">
            by Collide
          </span>
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          <Link
            to="/"
            className={`no-underline px-3 py-1.5 rounded-md transition-colors ${
              location.pathname === "/"
                ? "bg-accent-dim text-accent"
                : "text-text-muted hover:text-text"
            }`}
          >
            Pipelines
          </Link>
          <Link
            to="/new"
            className="no-underline bg-accent text-bg px-3 py-1.5 rounded-md text-sm font-medium hover:brightness-110 transition-all"
          >
            + New CR
          </Link>
        </nav>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
