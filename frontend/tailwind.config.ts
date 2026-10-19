import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: "#f3f5f8",
        graphite: "#13213a",
        ink: "#0f2340",
        steel: "#5a6576",
        "steel-light": "#8a94a3",
        border: "#e3e8ef",
        navy: {
          DEFAULT: "#0f2340",
          light: "#16305a",
          line: "#24344c",
        },
        brand: {
          DEFAULT: "#1d64c8",
          dark: "#164f9f",
          light: "#e8f0fb",
        },
        accent: {
          DEFAULT: "#f26a1b",
          dark: "#d9580c",
          light: "#feecdf",
        },
      },
      borderRadius: {
        industrial: "8px",
      },
      boxShadow: {
        industrial: "0 1px 2px rgba(15,27,45,0.05), 0 1px 3px rgba(15,27,45,0.04)",
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
