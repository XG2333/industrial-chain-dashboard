import type { CustomFlowbiteTheme } from 'flowbite-react/types';

export const flowbiteTheme: CustomFlowbiteTheme = {
  card: {
    root: {
      base: 'flex rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800',
      children: 'flex h-full flex-col p-0',
      horizontal: {
        off: 'flex-col',
        on: 'flex-col md:max-w-xl md:flex-row',
      },
      href: 'hover:bg-slate-100 dark:hover:bg-slate-700',
    },
    img: {
      base: '',
      horizontal: {
        off: 'rounded-t-lg',
        on: 'h-96 w-full rounded-t-lg object-cover md:h-auto md:w-48 md:rounded-none md:rounded-l-lg',
      },
    },
  },
  button: {
    base: 'relative flex items-center justify-center rounded-lg text-center font-medium focus:outline-none focus:ring-4',
    size: {
      sm: 'h-9 px-3 text-xs',
    },
  },
  badge: {
    root: {
      base: 'flex h-fit items-center gap-1 font-semibold',
    },
  },
  alert: {
    base: 'flex flex-col gap-2 p-4 text-sm',
    rounded: 'rounded-lg',
  },
  sidebar: {
    root: {
      base: 'h-full',
      inner: 'h-full overflow-y-auto overflow-x-hidden bg-white px-3 py-4 dark:bg-slate-800',
    },
    item: {
      base: 'flex items-center justify-center rounded-lg p-2 text-base font-normal text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700',
      active: 'bg-slate-100 dark:bg-slate-700',
    },
  },
  navbar: {
    root: {
      base: 'bg-white px-2 py-2.5 sm:px-4 dark:bg-slate-800',
      bordered: {
        on: 'border-b border-slate-200 dark:border-slate-700',
        off: '',
      },
    },
  },
};
