/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        colors: {
          'brand-bg': '#111827',
          'brand-surface': '#1F2937',
          'brand-border': '#374151',
          'brand-text': '#F9FAFB',
          'brand-text-secondary': '#9CA3AF',
          'brand-primary': '#3B82F6',
          'brand-primary-hover': '#2563EB',
        },
      },
    },
    plugins: [
      require('@tailwindcss/typography'),
    ],
  }
  