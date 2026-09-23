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
import "./styles/task-editor-polish.css";
import "./styles/v0.6-project-prompt.css";
import "./styles/project-config.css";
import "./styles/v0.7-controls-polish.css";
import "./styles/v0.8-ai-enhance.css";
import "./styles/v0.9-flex-layout-fixes.css";
import "./styles/v0.9-compact-density.css";
import "./styles/task-editor-feedback.css";
import "./styles/batch-review.css";

initializeTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OverlayProvider>
      <App />
    </OverlayProvider>
  </StrictMode>,
);
