import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import App from "./App.tsx";
import { createQueryClient } from "./api/queryClient";
import { redirectLegacyTabLink } from "./lib/location";

// Before anything reads the URL: links from when pages were tabs.
redirectLegacyTabLink();

const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
