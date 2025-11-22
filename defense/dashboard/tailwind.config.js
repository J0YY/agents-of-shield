/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#86fffb",
        danger: "#ff4d6d",
        panel: "#0f172a"
      }
    }
  },
  plugins: []
};

