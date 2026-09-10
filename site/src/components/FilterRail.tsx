import type { FactorSpec } from "../data/types";
import { CHG_ANY, useApp, type Ranges } from "../state/AppState";
import { COLUMNS } from "./columns";

interface Props {
  sectorCounts: [string, number][];
  factors: FactorSpec[];
}

/**
 * A persistent rail rather than filters scattered per column, so every active
 * constraint is visible in one place. In Basic mode it holds exactly two
 * controls: sector and the overall score.
 */
export function FilterRail({ sectorCounts, factors }: Props) {
  const { mode, sectors, toggleSector, ranges, setRange, chgMin, setChgMin, clearFilters,
          hiddenColumns, toggleColumn, resetWidths } = useApp();
  const pro = mode === "pro";

  return (
    <aside className="rail">
      <div className="grp">
        <h3>Sector</h3>
        {sectorCounts.map(([sector, count]) => (
          <label className="chk" key={sector}>
            <input
              type="checkbox"
              checked={sectors.includes(sector)}
              onChange={() => toggleSector(sector)}
            />
            <span>{sector}</span>
            <span className="ct">{count}</span>
          </label>
        ))}
        {!sectorCounts.length && <p className="railhelp">No sectors in this view.</p>}
      </div>

      <div className="grp">
        <h3>Show only scores above</h3>
        <p className="railhelp">
          Scores run 0–100, where 100 is the best in the stock&apos;s own sector. Drag right to
          demand a higher score — fewer stocks match.
        </p>
        <RangeSlider label="Rankfield Score" value={ranges.composite} onChange={(v) => setRange("composite", v)} />
        {pro &&
          factors.map((factor) => (
            <RangeSlider
              key={factor.key}
              label={factor.label}
              value={ranges[factor.key as keyof Ranges]}
              onChange={(v) => setRange(factor.key as keyof Ranges, v)}
            />
          ))}
      </div>

      {pro && (
        <div className="grp">
          <h3>Show only price moves above</h3>
          <p className="railhelp">
            Price change since the prior scoring date. Drag right to hide decliners and weak movers.
          </p>
          <div className="rng">
            <div className="lbl">
              <span>1-month change ≥</span>
              <span className={`val${chgMin > CHG_ANY ? " act" : ""}`}>
                {chgMin <= CHG_ANY ? "Any" : `${chgMin > 0 ? "+" : ""}${chgMin}%`}
              </span>
            </div>
            <input
              type="range"
              min={CHG_ANY}
              max={30}
              step={1}
              value={chgMin}
              onChange={(e) => setChgMin(Number(e.target.value))}
              aria-label="Minimum one-month price change"
            />
            <div className="scale">
              <span>Any</span>
              <span>+30%</span>
            </div>
          </div>
        </div>
      )}

      {pro && (
        <div className="grp">
          <h3>Columns</h3>
          <p className="railhelp">Hide what you are not using. Remembered on this device.</p>
          {COLUMNS.filter((c) => !c.locked && (mode === "pro" || !c.pro)).map((c) => (
            <label className="chk" key={c.key}>
              <input
                type="checkbox"
                checked={!hiddenColumns.includes(c.key)}
                onChange={() => toggleColumn(c.key)}
              />
              <span>{c.title}</span>
            </label>
          ))}
          <button type="button" className="linkbtn" style={{ marginTop: 8 }} onClick={resetWidths}>
            Reset column widths
          </button>
        </div>
      )}

      <div className="grp">
        <button type="button" className="linkbtn" onClick={clearFilters}>
          Clear all filters
        </button>
      </div>
    </aside>
  );
}

function RangeSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="rng">
      <div className="lbl">
        <span>{label} ≥</span>
        <span className={`val${value > 0 ? " act" : ""}`}>{value === 0 ? "Any" : value}</span>
      </div>
      <input
        type="range"
        min={0}
        max={90}
        step={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={`Minimum ${label}`}
      />
      <div className="scale">
        <span>Any</span>
        <span>90</span>
      </div>
    </div>
  );
}
