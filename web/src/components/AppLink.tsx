import type { AnchorHTMLAttributes, MouseEvent } from "react";

import { linkTo, navigate, useSearch } from "@/lib/location";

/**
 * A link to another page of the app: a real address, keeping the week, so
 * it can be opened in a new tab, but followed in place on a plain click.
 * `params` is what the page should open on, e.g. `{ day: "Tuesday" }`.
 */
export function AppLink({
  to,
  params,
  onClick,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & {
  to: string;
  params?: Readonly<Record<string, string>>;
}) {
  const search = useSearch();
  return (
    <a
      {...props}
      href={linkTo(to, search, params)}
      onClick={(event) => {
        onClick?.(event);
        if (!meantForThisTab(event)) return;
        event.preventDefault();
        navigate(to, params);
      }}
    />
  );
}

/**
 * A plain click; not one meant for a new tab or window (modifier keys, the
 * middle button), which is left to the browser.
 */
function meantForThisTab(event: MouseEvent<HTMLAnchorElement>): boolean {
  return !(
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  );
}
