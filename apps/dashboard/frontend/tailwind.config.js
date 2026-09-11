import flowbiteReact from 'flowbite-react/plugin/tailwindcss';

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    './.flowbite-react/class-list.json',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // shadcn/ui 颜色映射：index.css 存 OKLCH 分量（L C H 空格分隔，不带 oklch() 包装），
      // 此处统一包成 oklch(var(--x) / <alpha-value>) —— 这样 bg-primary/70、border-border/60
      // 等透明度修饰类才生成有效 CSS（直接 var() 引用会让带 /n 的类全部失效透明）
      colors: {
        background: 'oklch(var(--background) / <alpha-value>)',
        foreground: 'oklch(var(--foreground) / <alpha-value>)',
        card: 'oklch(var(--card) / <alpha-value>)',
        'card-foreground': 'oklch(var(--card-foreground) / <alpha-value>)',
        popover: 'oklch(var(--popover) / <alpha-value>)',
        'popover-foreground': 'oklch(var(--popover-foreground) / <alpha-value>)',
        primary: 'oklch(var(--primary) / <alpha-value>)',
        'primary-foreground': 'oklch(var(--primary-foreground) / <alpha-value>)',
        secondary: 'oklch(var(--secondary) / <alpha-value>)',
        'secondary-foreground': 'oklch(var(--secondary-foreground) / <alpha-value>)',
        muted: 'oklch(var(--muted) / <alpha-value>)',
        'muted-foreground': 'oklch(var(--muted-foreground) / <alpha-value>)',
        accent: 'oklch(var(--accent) / <alpha-value>)',
        'accent-foreground': 'oklch(var(--accent-foreground) / <alpha-value>)',
        destructive: 'oklch(var(--destructive) / <alpha-value>)',
        'destructive-foreground': 'oklch(var(--destructive-foreground) / <alpha-value>)',
        border: 'oklch(var(--border) / <alpha-value>)',
        input: 'oklch(var(--input) / <alpha-value>)',
        ring: 'oklch(var(--ring) / <alpha-value>)',
      },
    },
  },
  plugins: [flowbiteReact],
};
