/**
 * Anonymous usage counting with GoatCounter: page views, and clicks on the AI copy
 * buttons. No cookies, no personal data, no company names. Switched off while the
 * account code below is empty, so nothing is loaded and nothing is sent.
 */
export const GOATCOUNTER_CODE = "";

interface GoatCounter {
  count: (vars: { path: string; title?: string; event?: boolean }) => void;
}

declare global {
  interface Window {
    goatcounter?: GoatCounter & { no_onload?: boolean };
  }
}

export function startCounting(): void {
  if (!GOATCOUNTER_CODE || typeof document === "undefined") return;
  window.goatcounter = { no_onload: true } as Window["goatcounter"];
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://gc.zgo.at/count.js";
  script.dataset.goatcounter = `https://${GOATCOUNTER_CODE}.goatcounter.com/count`;
  document.head.appendChild(script);
}

export function countPage(path: string): void {
  try {
    window.goatcounter?.count?.({ path });
  } catch {
    /* counting must never break the page */
  }
}

/** One of: ai-copy-table, ai-copy-company. */
export function countEvent(name: string): void {
  try {
    window.goatcounter?.count?.({ path: name, title: name, event: true });
  } catch {
    /* counting must never break the page */
  }
}
