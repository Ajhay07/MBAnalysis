import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: "#f3f5f8",
        graphite: "#0f1b2d",
        ink: "#0f1b2d",
        steel: "#5a6576",
        "steel-light": "#8a94a3",
        border: "#e3e8ef",
        navy: {
          DEFAULT: "#0e1d30",
          light: "#16294180",
          line: "#1f3550",
        },
        brand: {
          DEFAULT: "#1f6feb",
          dark: "#1658c4",
          light: "#e8f0fe",
        },
        accent: {
          DEFAULT: "#f26b1d",
          dark: "#d9590f",
          light: "#fde9dc",
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
