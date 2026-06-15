/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Clinical blue accent
        brand: {
          DEFAULT: "#185FA5",
          dark: "#12497E",
          soft: "#E8F1F9",
          line: "#B9D4E8",
        },
        // Status families: soft tint bg + dark ink
        fav: { ink: "#0F6E56", bg: "#E1F5EE" },
        part: { ink: "#854F0B", bg: "#FAEEDA" },
        neg: { ink: "#A32D2D", bg: "#FCEBEB" },
        wrong: { ink: "#534AB7", bg: "#EBE9F9" },
        ink: { DEFAULT: "#16202B", soft: "#5A6675", faint: "#8A95A3" },
        surface: { DEFAULT: "#FFFFFF", muted: "#F7F9FB" },
        page: "#F1F4F7",
        hair: "#E3E8EE",
        // Deep-navy sidebar shell. A darker companion to the clinical brand blue; same hue family,
        // used only for the persistent left navigation chrome.
        navy: {
          DEFAULT: "#0F2840",
          deep: "#0A1E31",
          soft: "#163653",
          line: "#274B6B",
          ink: "#AFC4D8",
          faint: "#7C97B0",
        },
      },
      fontFamily: {
        sans: [
          "Figtree",
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      borderRadius: { xl: "12px" },
      // Layered, soft shadows so surfaces lift off the page (still subtle). Shadow tint uses the
      // existing ink color (16,32,48) — no palette color is introduced or changed.
      boxShadow: {
        card: "0 1px 2px rgba(16,32,48,0.04), 0 4px 12px -2px rgba(16,32,48,0.08)",
        lift: "0 2px 6px -2px rgba(16,32,48,0.10), 0 14px 30px -8px rgba(16,32,48,0.16)",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.34, 1.4, 0.64, 1)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.34, 1.4, 0.64, 1) both",
      },
    },
  },
  plugins: [],
};
