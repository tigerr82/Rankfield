import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { encodeSharedHoldings, parseSharedHoldings } from "../lib/portfolio";
import { useApp } from "../state/AppState";

export const SHARE_PARAM = "p";

/**
 * A portfolio arriving in the link.
 *
 * The log records when each position was actually opened, because applying
 * today's holdings to past months would credit the reader with gains they never
 * captured. A shared link cannot know which of two things it is - the same
 * person opening their own portfolio on a second device, or someone else's
 * portfolio arriving - and the difference decides whether the original dates may
 * be kept. So the question is asked rather than guessed, and "sent to me" is
 * the safe default: it starts the record today.
 */
export function SharedPortfolioBanner() {
  const [params, setParams] = useSearchParams();
  const { importHoldings, holdings } = useApp();
  const [done, setDone] = useState<string | null>(null);
  const shared = useMemo(() => parseSharedHoldings(params.get(SHARE_PARAM)), [params]);

  useEffect(() => {
    if (done) {
      const timer = window.setTimeout(() => setDone(null), 6000);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [done]);

  if (!shared.length) return done ? <p className="sharebanner">{done}</p> : null;

  const fresh = shared.filter((s) => !holdings.includes(s.ticker));
  const clear = () => {
    const next = new URLSearchParams(params);
    next.delete(SHARE_PARAM);
    setParams(next, { replace: true });
  };
  const accept = (keepDates: boolean) => {
    importHoldings(shared, keepDates);
    setDone(
      `Added ${fresh.length} holding${fresh.length === 1 ? "" : "s"}` +
        (keepDates ? ", keeping the original start dates." : ", starting from today.") +
        (fresh.length < shared.length
          ? ` ${shared.length - fresh.length} of them were already in your portfolio.`
          : ""),
    );
    clear();
  };

  return (
    <div className="sharebanner" role="status">
      <b>A portfolio arrived in this link:</b>{" "}
      {shared.map((s) => s.ticker).join(", ")}
      <span className="sharehint">
        {fresh.length === shared.length
          ? `${shared.length} holding${shared.length === 1 ? "" : "s"}`
          : `${fresh.length} new, ${shared.length - fresh.length} already held`}
      </span>
      <button type="button" className="linkbtn" onClick={() => accept(false)}>
        Someone sent it to me — start today
      </button>
      <button
        type="button"
        className="linkbtn"
        title="Keeps the day each position was opened, so the measured record stays true. Only correct if this is your own portfolio."
        onClick={() => accept(true)}
      >
        It is mine — keep the dates
      </button>
      <button type="button" className="linkbtn" onClick={clear}>
        Ignore
      </button>
    </div>
  );
}

/** Copies a link carrying the portfolio. No account, no server, no password. */
export function SharePortfolioButton() {
  const { watchEvents } = useApp();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") return undefined;
    const timer = window.setTimeout(() => setState("idle"), 4000);
    return () => window.clearTimeout(timer);
  }, [state]);

  const link = useMemo(() => {
    const code = encodeSharedHoldings(watchEvents);
    const { origin, pathname } = window.location;
    return `${origin}${pathname}#/?${SHARE_PARAM}=${encodeURIComponent(code)}`;
  }, [watchEvents]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setState("copied");
    } catch {
      // Clipboard access is blocked in some browsers and in private windows;
      // the prompt still lets the user copy the link by hand.
      window.prompt("Copy this link to open your portfolio anywhere:", link);
      setState("failed");
    }
  };

  return (
    <button
      type="button"
      className="linkbtn"
      onClick={copy}
      title="Copies a link containing your holdings. Open it on another device, or send it to someone - nothing is stored on a server."
    >
      {state === "copied" ? "Link copied" : "Share link"}
    </button>
  );
}
