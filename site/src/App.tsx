import { HashRouter, Route, Routes } from "react-router-dom";
import { AppHeader, StatusBanner } from "./components/Shell";
import { AppStateProvider } from "./state/AppState";
import { metricCoverage, usePayload } from "./data/usePayload";
import { RankingPage } from "./routes/RankingPage";
import { StockPage } from "./routes/StockPage";
import { MethodologyPage } from "./routes/MethodologyPage";
import { WeightsPage } from "./routes/WeightsPage";
import { ValidationPage } from "./routes/ValidationPage";
import { StabilityPage } from "./routes/StabilityPage";
import { CoveragePage } from "./routes/CoveragePage";

/**
 * Hash routing, deliberately. Static hosts (GitHub Pages, Cloudflare Pages)
 * serve no rewrite rule, so a deep path like /stock/AAPL would 404 on a hard
 * refresh or a shared link. `#/stock/AAPL` is stable, shareable and correct on
 * every static host without a per-host workaround.
 */
export function App() {
  return (
    <AppStateProvider>
      <HashRouter>
        <Chrome />
      </HashRouter>
    </AppStateProvider>
  );
}

function Chrome() {
  const { scores } = usePayload();
  return (
    <>
      <StatusBanner meta={scores?.meta} />
      <AppHeader meta={scores?.meta} coverage={metricCoverage(scores)} />
      <Routes>
        <Route path="/" element={<RankingPage />} />
        <Route path="/stock/:ticker" element={<StockPage />} />
        <Route path="/weights" element={<WeightsPage />} />
        <Route path="/validation" element={<ValidationPage />} />
        <Route path="/stability" element={<StabilityPage />} />
        <Route path="/methodology" element={<MethodologyPage />} />
        <Route path="/coverage" element={<CoveragePage />} />
        <Route path="*" element={<RankingPage />} />
      </Routes>
    </>
  );
}
