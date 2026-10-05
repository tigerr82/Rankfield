import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { ScoresPayload } from "../data/types";
import { crossSearch, SHOWN_OTHER } from "../lib/crossSearch";
import { useApp } from "../state/AppState";

/**
 * The search box looks at the table on screen; this looks at the rest.
 *
 * A reader who types JPMorgan while Operating is open would otherwise be told
 * nothing matched, as if the company were not in the product. Each hit names
 * its table, links to the company, and the table name switches to it with the
 * search kept, so the company can be seen in its own ranking.
 */
export function OtherTables({ scores }: { scores: ScoresPayload }) {
  const { query, segment, setSegment } = useApp();
  // With a ranked table open the search already covers every ranked table in the
  // table itself, so only the unranked list is left to mention here.
  const include = segment === "insufficient" ? "ranked" : "unranked";
  const hits = useMemo(() => crossSearch(scores, query, segment, include), [scores, query, segment, include]);
  if (!hits.length) return null;

  const label = (table: string) =>
    table === "insufficient"
      ? "Insufficient data"
      : scores.segments_meta.find((m) => m.key === table)?.label ?? table;

  return (
    <div className="othertabs" role="note">
      <span className="mosumlabel">{include === "unranked" ? "Also unranked" : "Also in other tables"}</span>
      {hits.slice(0, SHOWN_OTHER).map((h) => (
        <span key={h.ticker} className="othertab">
          <Link to={`/stock/${h.ticker}`} className="mosumlink">
            {h.ticker}
          </Link>{" "}
          {h.name.replace(/\s+(Class [A-Z] )?(Common Stock|Ordinary Shares).*$/i, "")}{" "}
          <button
            type="button"
            className="othertabgo"
            title="Open that table, keeping your search"
            onClick={() => setSegment(h.table)}
          >
            {label(h.table)}
            {h.rank != null ? ` · #${h.rank.toLocaleString()}` : ""}
          </button>
        </span>
      ))}
      {hits.length > SHOWN_OTHER && <span>+{hits.length - SHOWN_OTHER} more - narrow the search</span>}
    </div>
  );
}
