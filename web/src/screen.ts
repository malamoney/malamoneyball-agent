import { useSyncExternalStore } from "react";

/** Wide enough to show the sidebar beside the Conversation: Tailwind's `md`. */
export const WIDE_SCREEN = "(min-width: 48rem)";

/** Whether the page is wide enough for the sidebar to stay open, kept up to date. */
export function useWideScreen(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia(WIDE_SCREEN);
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia(WIDE_SCREEN).matches,
  );
}
