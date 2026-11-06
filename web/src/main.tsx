import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import "./styles.css";
import "./theme.css";
import "./desk.css";
import "./look.css";
import "./login.css";
import { applyTheme, savedTheme } from "./lib/theme";

applyTheme(savedTheme());

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
  </StrictMode>,
);
