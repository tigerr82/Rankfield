import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { FactorKey, SegmentKey } from "../data/types";
import { DEFAULT_WEIGHTS, FACTOR_ORDER, type Weights } from "../lib/scoring";
import { allEvents, currentHoldings, removeAll, toggle, type WatchEvent } from "../lib/portfolio";

export type Mode = "basic" | "pro";
export type Theme = "system" | "light" | "dark";
export type ViewScope = "top_decile" | "all";
export type SortDir = 1 | -1;

export const CHG_ANY = -100;

export interface Ranges {
  composite: number;
  quality: number;
  growth: number;
  valuation: number;
  health: number;
}

const EMPTY_RANGES: Ranges = { composite: 0, quality: 0, growth: 0, valuation: 0, health: 0 };

/** Columns that exist only in Pro mode. Sorting by one of these must not
 *  survive a switch to Basic, where the column is not shown. */
const PRO_ONLY_SORT_KEYS: string[] = [...FACTOR_ORDER, "rank_change", "_spark", "_stability"];

function persisted<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* blocked site data: preferences simply are not remembered */
  }
}

interface AppContextValue {
  mode: Mode;
  setMode: (mode: Mode) => void;
  theme: Theme;
  cycleTheme: () => void;
  setTheme: (theme: Theme) => void;

  segment: SegmentKey | "insufficient";
  setSegment: (segment: SegmentKey | "insufficient") => void;
  scope: ViewScope;
  setScope: (scope: ViewScope) => void;

  query: string;
  setQuery: (query: string) => void;
  sectors: string[];
  toggleSector: (sector: string) => void;
  ranges: Ranges;
  setRange: (key: keyof Ranges, value: number) => void;
  chgMin: number;
  setChgMin: (value: number) => void;
  clearFilters: () => void;
  hasFilters: boolean;

  sortKey: string;
  sortDir: SortDir;
  setSort: (key: string, dir?: SortDir) => void;

  weights: Weights;
  setWeight: (key: FactorKey, value: number) => void;
  resetWeights: () => void;

  railCollapsed: boolean;
  toggleRail: () => void;

  hiddenColumns: string[];
  toggleColumn: (key: string) => void;
  widths: Record<string, number>;
  setWidths: (widths: Record<string, number>) => void;
  resetWidths: () => void;

  watchEvents: WatchEvent[];
  holdings: string[];
  toggleHolding: (ticker: string) => void;
  clearHoldings: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  // Basic is the default for a first-time visitor: a calmer default, not a
  // crippled tier - the toggle stays visible in the toolbar at all times.
  const [mode, setModeRaw] = useState<Mode>(() => persisted<Mode>("rankfield_mode_v1", "basic"));
  const [theme, setTheme] = useState<Theme>(() => persisted<Theme>("rankfield_theme_v1", "system"));
  const [segment, setSegment] = useState<SegmentKey | "insufficient">("operating");
  const [scope, setScope] = useState<ViewScope>("top_decile");
  const [query, setQuery] = useState("");
  const [sectors, setSectors] = useState<string[]>([]);
  const [ranges, setRanges] = useState<Ranges>(EMPTY_RANGES);
  const [chgMin, setChgMin] = useState(CHG_ANY);
  const [sortKey, setSortKey] = useState("composite");
  const [sortDir, setSortDir] = useState<SortDir>(-1);
  // What-if weights are session state on purpose. They never persist and never
  // write to history: the stored monthly scores keep the official weights.
  const [weights, setWeights] = useState<Weights>({ ...DEFAULT_WEIGHTS });
  const [hiddenColumns, setHiddenColumns] = useState<string[]>(() =>
    persisted<string[]>("rankfield_hidden_cols_v1", []),
  );
  const [widths, setWidthsRaw] = useState<Record<string, number>>(() =>
    persisted<Record<string, number>>("rankfield_widths_v1", {}),
  );
  const [watchEvents, setWatchEvents] = useState<WatchEvent[]>(() => allEvents());
  // Below this the window cannot hold the rail AND the full Pro column set:
  // 236px of rail + ~36px of margin + a ~997px table + a scrollbar.
  const RAIL_FITS_ABOVE = 1280;

  // Seeing every column at once matters more than keeping the filters pinned,
  // so on a narrow window the rail starts closed and opens as an overlay. It
  // only ever auto-closes - never auto-opens - so it cannot fight the user.
  const [railCollapsed, setRailCollapsed] = useState<boolean>(() => {
    const stored = persisted<boolean>("rankfield_rail_collapsed_v1", false);
    if (typeof window !== "undefined" && window.innerWidth < RAIL_FITS_ABOVE) return true;
    return stored;
  });

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth < RAIL_FITS_ABOVE) setRailCollapsed(true);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    persist("rankfield_theme_v1", theme);
  }, [theme]);

  const setMode = useCallback((next: Mode) => {
    setModeRaw(next);
    persist("rankfield_mode_v1", next);
    if (next === "basic") {
      // Hidden filters must not silently filter. A user must never see a
      // filtered table with no visible explanation for why rows are missing,
      // nor sorted by a column that is no longer on screen.
      setRanges((prev) => ({ ...EMPTY_RANGES, composite: prev.composite }));
      setChgMin(CHG_ANY);
      setSortKey((prev) => {
        if (!PRO_ONLY_SORT_KEYS.includes(prev)) return prev;
        setSortDir(-1);
        return "composite";
      });
    }
  }, []);

  const cycleTheme = useCallback(() => {
    setTheme((prev) => (prev === "system" ? "dark" : prev === "dark" ? "light" : "system"));
  }, []);

  const toggleSector = useCallback((sector: string) => {
    setSectors((prev) => (prev.includes(sector) ? prev.filter((s) => s !== sector) : [...prev, sector]));
  }, []);

  const setRange = useCallback((key: keyof Ranges, value: number) => {
    setRanges((prev) => ({ ...prev, [key]: value }));
  }, []);

  const clearFilters = useCallback(() => {
    setSectors([]);
    setRanges(EMPTY_RANGES);
    setChgMin(CHG_ANY);
    setQuery("");
  }, []);

  const setSort = useCallback((key: string, dir?: SortDir) => {
    setSortKey((prevKey) => {
      if (dir != null) {
        setSortDir(dir);
        return key;
      }
      if (prevKey === key) {
        setSortDir((d) => (d === -1 ? 1 : -1) as SortDir);
        return key;
      }
      setSortDir(key === "ticker" || key === "name" || key === "sector" ? 1 : -1);
      return key;
    });
  }, []);

  const setWeight = useCallback((key: FactorKey, value: number) => {
    setWeights((prev) => ({ ...prev, [key]: value }));
  }, []);
  const resetWeights = useCallback(() => setWeights({ ...DEFAULT_WEIGHTS }), []);

  const toggleColumn = useCallback((key: string) => {
    setHiddenColumns((prev) => {
      const next = prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key];
      persist("rankfield_hidden_cols_v1", next);
      return next;
    });
  }, []);

  const setWidths = useCallback((next: Record<string, number>) => {
    setWidthsRaw(next);
    persist("rankfield_widths_v1", next);
  }, []);
  const resetWidths = useCallback(() => {
    setWidthsRaw({});
    persist("rankfield_widths_v1", {});
  }, []);

  const toggleRail = useCallback(() => {
    setRailCollapsed((prev) => {
      persist("rankfield_rail_collapsed_v1", !prev);
      return !prev;
    });
  }, []);

  const toggleHolding = useCallback((ticker: string) => setWatchEvents([...toggle(ticker)]), []);
  const clearHoldings = useCallback(() => setWatchEvents([...removeAll()]), []);

  const holdings = useMemo(() => currentHoldings(watchEvents), [watchEvents]);
  const hasFilters =
    sectors.length > 0 ||
    chgMin > CHG_ANY ||
    query.length > 0 ||
    Object.values(ranges).some((v) => v > 0);

  const value: AppContextValue = {
    mode, setMode, theme, cycleTheme, setTheme,
    segment, setSegment, scope, setScope,
    query, setQuery, sectors, toggleSector, ranges, setRange, chgMin, setChgMin,
    clearFilters, hasFilters,
    sortKey, sortDir, setSort,
    weights, setWeight, resetWeights,
    railCollapsed, toggleRail,
    hiddenColumns, toggleColumn, widths, setWidths, resetWidths,
    watchEvents, holdings, toggleHolding, clearHoldings,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppStateProvider");
  return ctx;
}
