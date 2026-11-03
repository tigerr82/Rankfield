import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { startCounting } from "./lib/track";
import "./styles/app.css";

startCounting();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
