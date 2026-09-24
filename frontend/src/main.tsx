import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { OverlayProvider } from "./ui/overlay";
import { initializeTheme } from "./ui/theme";
import "./ui/primitives/style.css";
import "./styles/tokens.css";
import "./styles/prompt-asset-editor.css";
import "./styles/overlays.css";
import "./styles/simple-editor.css";
import "./styles/project-workspace.css";
import "./styles/application-settings.css";
import "./styles/task-editor-header.css";
import "./styles/task-editor-prompt.css";
import "./styles/project-config.css";
import "./styles/task-editor-controls.css";
import "./styles/prompt-enhancement.css";
import "./styles/layout-resilience.css";
import "./styles/layout-density.css";
import "./styles/task-editor-alignment.css";
import "./styles/batch-review.css";

initializeTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OverlayProvider>
      <App />
    </OverlayProvider>
  </StrictMode>,
);
