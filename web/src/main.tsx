import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { httpApi } from "./api";
import { Chat } from "./Chat";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Chat api={httpApi} />
  </StrictMode>,
);
