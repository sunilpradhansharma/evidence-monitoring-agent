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
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      borderRadius: { xl: "12px" },
      boxShadow: {
        card: "0 1px 2px rgba(16,32,48,0.05), 0 1px 1px rgba(16,32,48,0.04)",
        lift: "0 6px 18px rgba(16,32,48,0.10)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s ease-out both",
      },
    },
  },
  plugins: [],
};
