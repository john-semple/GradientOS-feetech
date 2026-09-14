import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 8000,
    host: "0.0.0.0",
    // IPs are how this Pi is reached (loopback + tailnet). Vite 5.4+ may
    // reject unknown Host headers otherwise. Do not add the school Wi-Fi
    // address. Docs: /home/user/openchamber-handoff/gradientos-web.md
    allowedHosts: [
      "gradientrobotics.local",
      "jetson.local",
      "mini-arm.local",
      "localhost",
      "127.0.0.1",
      "100.121.188.134",
    ]
  }
});
