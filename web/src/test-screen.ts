import { WIDE_SCREEN } from "./screen";

// jsdom has no `matchMedia`, so tests choose the screen width: wide unless set.
let width = 1024;
const listeners = new Set<() => void>();

export function setScreenWidth(pixels: number) {
  width = pixels;
  for (const listener of listeners) listener();
}

export function installScreen() {
  width = 1024;
  window.matchMedia = (query: string) =>
    ({
      media: query,
      get matches() {
        return query === WIDE_SCREEN && width >= 768;
      },
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    }) as unknown as MediaQueryList;
}
