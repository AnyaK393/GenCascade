export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f6f5f0',
        ink: {
          50: '#f2f5f6', 100: '#e3e9eb', 200: '#c9d3d7', 300: '#a3b2b8', 400: '#73868e',
          500: '#566a72', 600: '#435660', 700: '#33454e', 800: '#22333b', 900: '#14242b',
        },
        brand: {
          50: '#ecf8f6', 100: '#d2efea', 200: '#a7dfd6', 300: '#70c8bb', 400: '#3dab9d',
          500: '#1f9083', 600: '#14756c', 700: '#105e58', 800: '#0e4b47', 900: '#0b3a38',
        },
        coral: { 50: '#fdf0ec', 100: '#fbdcd3', 300: '#f3a18c', 500: '#e8674a', 600: '#cf4e32', 700: '#ab3c24' },
        sun: { 100: '#fdf0cf', 300: '#f7cf6e', 500: '#eaa92c', 800: '#7d5205' },
      },
      fontFamily: { sans: ['"Manrope Variable"', 'system-ui', 'sans-serif'] },
      boxShadow: {
        card: '0 1px 2px rgb(20 36 43 / 0.05), 0 10px 28px -16px rgb(20 36 43 / 0.18)',
        lift: '0 2px 4px rgb(20 36 43 / 0.06), 0 18px 36px -18px rgb(20 36 43 / 0.28)',
      },
      keyframes: {
        // Every end state is `transform: none`: a leftover transform would trap the fixed modal inside the page.
        'fade-up': { from: { opacity: 0, transform: 'translateY(10px)' }, to: { opacity: 1, transform: 'none' } },
        pop: { from: { opacity: 0, transform: 'scale(.96) translateY(6px)' }, to: { opacity: 1, transform: 'none' } },
        float: { '0%, 100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-9px)' } },
        grow: { from: { transform: 'scaleX(0)' }, to: { transform: 'scaleX(1)' } },
        dot: { '0%, 60%, 100%': { transform: 'translateY(0)', opacity: 0.45 }, '30%': { transform: 'translateY(-5px)', opacity: 1 } },
        ping: { '75%, 100%': { transform: 'scale(2.4)', opacity: 0 } },
      },
      animation: {
        'fade-up': 'fade-up .45s cubic-bezier(.2,.7,.3,1) backwards',
        pop: 'pop .28s cubic-bezier(.2,.7,.3,1) backwards',
        float: 'float 6s ease-in-out infinite',
        'float-slow': 'float 8s ease-in-out -2s infinite',
        grow: 'grow .9s cubic-bezier(.2,.7,.3,1) backwards',
        dot: 'dot 1.2s ease-in-out infinite',
        beacon: 'ping 1.8s cubic-bezier(0,0,.2,1) infinite',
      },
    },
  },
  plugins: [],
};
