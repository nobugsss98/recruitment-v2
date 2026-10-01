/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        surface: {
          950: '#0b0e17',
          900: '#10141f',
          850: '#141a29',
          800: '#1a2133',
          750: '#202839',
          700: '#2a3350',
        },
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-14px)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.8s linear infinite',
        float: 'float 7s ease-in-out infinite',
      },
      boxShadow: {
        glow: '0 0 24px rgba(99, 102, 241, 0.35)',
      },
    },
  },
  plugins: [],
};
