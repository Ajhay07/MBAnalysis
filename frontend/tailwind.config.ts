import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: "#fafaf8",
        graphite: "#2b2d2f",
        steel: "#5b6166",
        "steel-light": "#8b9196",
        border: "#e2e1dc",
        accent: {
          DEFAULT: "#d2601a",
          dark: "#b3500f",
          light: "#f4e3d3",
        },
      },
      borderRadius: {
        industrial: "10px",
      },
      boxShadow: {
        industrial: "0 1px 2px rgba(20,20,20,0.06), 0 1px 1px rgba(20,20,20,0.04)",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["Consolas", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
