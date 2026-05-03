import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import "./index.css";
import App from "./App";
import LiveFeed from "./pages/LiveFeed";
import IncidentDetail from "./pages/IncidentDetail";
import { ToastProvider } from "./components/Toast";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<App />}>
              <Route index element={<LiveFeed />} />
              <Route path="incidents/:id" element={<IncidentDetail />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
