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
  return (
    <div className={`shell${rail ? "" : " norail"}`}>
      {rail}
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
  return (
    <header className="app">
      <div>
        <div className="brandline">NYSE · NASDAQ — monthly factor scoring</div>
        <h1>Rankfield</h1>
        <div className="sub">Sector-relative equity scoring, with the work shown.</div>
      </div>
      <div className="hdr-right">
        <nav className="main">
          <NavLink to="/" end>Rankings</NavLink>
          <NavLink to="/weights">Weights</NavLink>
          <NavLink to="/validation">Validation</NavLink>
          <NavLink to="/stability">Stability</NavLink>
          <NavLink to="/methodology">Methodology</NavLink>
          <NavLink to="/coverage">Coverage</NavLink>
        </nav>
        <div className="hdr-stats">
          <div className="hstat">
            <span className="v mono">
              {meta ? Object.entries(meta.counts).filter(([k]) => k !== "insufficient").reduce((a, [, v]) => a + v, 0).toLocaleString() : "–"}
            </span>
            <span className="k">Stocks scored</span>
          </div>
          <div className="hstat">
            <span className="v mono">{meta?.scoring_date ?? "–"}</span>
            <span className="k">Scoring date</span>
          </div>
          <div className="hstat">
            <span className="v mono">{coverage != null ? `${Math.round(coverage * 100)}%` : "–"}</span>
            <span className="k">Metric coverage</span>
          </div>
        </div>
        <button type="button" className="icon-btn" onClick={cycleTheme} title="Cycle theme: system → dark → light">
          {theme === "system" ? "Theme: auto" : theme === "dark" ? "Theme: dark" : "Theme: light"}
        </button>
      </div>
    </header>
  );
}

/** Stale-data banner once the last run is more than five weeks old, and the
 *  first-run notice while month-over-month columns have no prior data. */
export function StatusBanner({ meta }: { meta?: ScoresMeta }) {
  if (!meta) return null;

  const stale = weeksSince(meta.scoring_date) > 5;
  if (stale) {
    return (
      <div className="banner stale">
        <span className="tag">Stale data</span>
        <span>
          The last scoring run was <b>{meta.scoring_date}</b>, more than five weeks ago. A monthly
          run has been missed — figures below are not current.
        </span>
      </div>
    );
  }
  if (meta.first_run) {
    return (
      <div className="banner">
        <span className="tag">First run</span>
        <span>
          This is the first scoring run, so there is no prior month to compare against.{" "}
          <b>Change columns show “—”, never 0%</b>, and score history begins accumulating from now.
        </span>
      </div>
    );
  }
  return (
    <div className="banner">
      <span className="tag">Rankfield</span>
      <span>
        Scored <b>{meta.scoring_date}</b> using weights v{meta.weights_version}. Fundamentals are
        point-in-time: only filings public on that date were used.
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
