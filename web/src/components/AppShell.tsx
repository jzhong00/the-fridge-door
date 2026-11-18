import type { LucideIcon } from "lucide-react";
import { UtensilsCrossed } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";

import { carriedSearch, navigate, useSearch } from "@/lib/location";

export interface NavPage {
  id: string;
  path: string;
  label: string;
  icon: LucideIcon;
}

/**
 * The frame every page sits in, after FloorSync's: a sidebar with the brand,
 * the pages and, at its foot, the account and theme; beside it, the page.
 *
 * One structure for every screen size. On a phone the sidebar becomes a top
 * bar and its page links a tab bar along the bottom, where a thumb reaches
 * them. Rendering the account controls once, rather than once per layout,
 * keeps a single copy of each button for keyboards and screen readers.
 */
export function AppShell({
  pages,
  current,
  footer,
  children,
}: {
  pages: readonly NavPage[];
  current: string;
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="flex items-center gap-3 border-b bg-sidebar px-4 py-3 text-sidebar-foreground lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:items-stretch lg:gap-0 lg:border-r lg:border-b-0 lg:p-4">
        <Brand />

        <nav
          aria-label="Pages"
          className="fixed inset-x-0 bottom-0 z-30 border-t bg-sidebar/95 px-2 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] backdrop-blur lg:static lg:mt-8 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none"
        >
          <p className="mb-2 hidden px-3 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase lg:block">
            Planning
          </p>
          <ul className="grid grid-flow-col auto-cols-fr gap-1 lg:flex lg:flex-col">
            {pages.map((page) => (
              <li key={page.id}>
                <NavLink page={page} active={page.id === current} />
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-2 lg:mt-auto lg:ml-0 lg:flex-col lg:items-stretch lg:gap-4 lg:border-t lg:pt-4">
          {footer}
        </div>
      </aside>

      {/* Room at the bottom on a phone, so the tab bar never covers content. */}
      <div className="min-w-0 pb-24 lg:pb-0">{children}</div>
    </div>
  );
}

function Brand() {
  return (
    <a
      href="/"
      onClick={followInApp("/")}
      className="flex shrink-0 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring lg:px-1"
    >
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
        <UtensilsCrossed className="size-4" aria-hidden />
      </span>
      <span className="hidden text-[15px] font-semibold tracking-tight sm:inline">
        Meal Planner
      </span>
    </a>
  );
}

function NavLink({ page, active }: { page: NavPage; active: boolean }) {
  const search = useSearch();
  const Icon = page.icon;
  return (
    <a
      href={page.path + carriedSearch(search)}
      onClick={followInApp(page.path)}
      aria-current={active ? "page" : undefined}
      className="flex flex-col items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-[current=page]:bg-primary-subtle aria-[current=page]:text-primary-subtle-foreground lg:flex-row lg:gap-3 lg:py-2 lg:text-sm"
    >
      <Icon className="size-5 lg:size-4" aria-hidden />
      {page.label}
    </a>
  );
}

/**
 * A plain click changes page without reloading; a click meant for a new
 * tab or window (modifier keys, middle button) is left to the browser,
 * which is why these are real links with real addresses.
 */
function followInApp(path: string) {
  return (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(path);
  };
}
