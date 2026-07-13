import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        canvas: "var(--td-canvas)",
        surface: "var(--td-surface-card)",
        "surface-soft": "var(--td-surface-soft)",
        "surface-elevated": "var(--td-surface-elevated)",
        hairline: "var(--td-hairline)",
        body: "var(--td-body)",
        "body-strong": "var(--td-body-strong)",
        muted: "var(--td-muted)",
        brand: "var(--td-brand)",
        "brand-muted": "var(--td-brand-muted)",
        "m-blue-light": "var(--td-m-blue-light)",
        "m-blue-dark": "var(--td-m-blue-dark)",
        "m-red": "var(--td-m-red)",
        success: "var(--td-success)",
        warning: "var(--td-warning)",
        danger: "var(--td-danger)",
      },
      fontFamily: {
        sans: "var(--td-font-body)",
        display: "var(--td-font-display)",
        mono: "var(--td-font-mono)",
      },
      borderRadius: {
        DEFAULT: "0px",
        sm: "0px",
        md: "4px",
        full: "9999px",
      },
    },
  },
  plugins: [],
} satisfies Config;
