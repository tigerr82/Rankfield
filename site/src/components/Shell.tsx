import { useRef, type ReactNode, type RefObject } from "react";
import { NavLink } from "react-router-dom";
import type { ScoresMeta } from "../data/types";
import { usePayload } from "../data/usePayload";
import { weeksSince } from "../lib/format";
import { useApp } from "../state/AppState";

/**
 * A fixed application shell, not a scrolling document.
 *
 * `body` is 100vh with overflow hidden; the banner and header are fixed chrome;
 * `main` is THE single scroll container. Nothing else scrolls, which is what
 * keeps the toolbar and table headers pinned correctly and stops the nested
 * scrollbars that make a data product feel unfinished.
 */
export function Shell({
  rail,
  children,
  scrollRef,
}: {
  rail?: ReactNode;
  children: ReactNode;
  scrollRef: RefObject<HTMLElement | null>;
}) {
  const { scores } = usePayload();
  const { railCollapsed } = useApp();
  return (
    <div className={`shell${rail && !railCollapsed ? "" : " norail"}`}>
      {rail && !railCollapsed ? rail : null}
      <main ref={scrollRef as RefObject<HTMLDivElement>}>
        {children}
        {/* Attribution and disclaimer sit inside the scroll container so they
            appear on every page without adding a second scrollport. */}
        <Footer meta={scores?.meta} />
      </main>
    </div>
  );
}

export function useScrollRef(): RefObject<HTMLElement | null> {
  return useRef<HTMLElement | null>(null);
}

export function AppHeader({ meta, coverage }: { meta?: ScoresMeta; coverage?: number }) {
  const { theme, cycleTheme } = useApp();
  const scored = meta
    ? Object.entries(meta.counts).filter(([k]) => k !== "insufficient").reduce((a, [, v]) => a + v, 0)
    : null;
  // One row. The brand line and tagline repeated what the page already shows,
  // and the three stats do not need a two-line label each - so the whole
  // header now costs a single line of height instead of three.
  return (
    <header className="app">
      <span className="wordmark" title="Rankfield - sector-relative equity scoring, with the work shown.">
        Rankfield
      </span>
      <nav className="main">
        <NavLink to="/" end>Rankings</NavLink>
        <NavLink to="/weights">Weights</NavLink>
        <NavLink to="/validation">Validation</NavLink>
        <NavLink to="/stability">Stability</NavLink>
        <NavLink to="/methodology">Methodology</NavLink>
        <NavLink to="/coverage">Coverage</NavLink>
      </nav>
      <div className="hdr-meta mono">
        {scored != null && <span title="Stocks with a Rankfield Score this month">{scored.toLocaleString()} scored</span>}
        {meta && <span title="Scoring date - the last trading day of the prior month">{meta.scoring_date}</span>}
        {meta?.first_run && (
          <span
            className="tag"
            title="The first scoring run: there is no prior month yet, so change columns show a dash (never 0%) until the next monthly run."
          >
            First run
          </span>
        )}
        {coverage != null && (
          <span title="Share of applicable metrics resolved across every scored stock">
            {Math.round(coverage * 100)}% coverage
          </span>
        )}
      </div>
      <button type="button" className="icon-btn" onClick={cycleTheme} title="Cycle theme: auto (follows your system) -> dark -> light">
        {theme === "system" ? "Auto" : theme === "dark" ? "Dark" : "Light"}
      </button>
    </header>
  );
}

/** Only a warning earns a full-width bar: data more than five weeks old means a
 *  monthly run was missed. The first-run notice now lives as a tag in the header,
 *  and the routine "scored on ..." bar is gone - the header already says it. */
export function StatusBanner({ meta }: { meta?: ScoresMeta }) {
  if (!meta || weeksSince(meta.scoring_date) <= 5) return null;
  return (
    <div className="banner stale">
      <span className="tag">Stale data</span>
      <span>
        Last scoring run <b>{meta.scoring_date}</b> is over five weeks old - a monthly run was missed.
      </span>
    </div>
  );
}

export function Footer({ meta }: { meta?: ScoresMeta }) {
  return (
    <footer className="pf">
      Fundamentals from SEC EDGAR company filings (public domain). Prices are split- and
      dividend-adjusted closes from {meta?.sources?.prices?.name ?? "the configured price provider"};
      universe, sector and market cap from the Nasdaq stock screener. Scores are sector-relative
      percentile ranks — a stock is measured against its own sector, never against the whole market.
      Metrics unavailable for a company are excluded and its remaining weights renormalised; they are
      never scored as zero.
      {meta && (
        <>
          {" "}
          Last run {meta.run_date} for scoring date {meta.scoring_date}.
        </>
      )}{" "}
      <br />
      <b>This is information, not investment advice.</b> Rankfield is a research tool, is not a
      registered investment adviser, and nothing here is a recommendation to buy or sell any
      security.
    </footer>
  );
}
