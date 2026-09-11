import React, { forwardRef, useEffect, useState } from 'react';
import { ArrowUp, BarChart3, LayoutDashboard, Menu, Moon, Sun, Zap } from 'lucide-react';
import { Navbar, Sidebar, SidebarItem, SidebarItemGroup, SidebarItems } from 'flowbite-react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { useVerticalDrag } from '@/hooks/useVerticalDrag';
import { cn } from '@/lib/utils';

const NAV = [
  { to: '/overview', icon: LayoutDashboard, label: '行情总览' },
  { to: '/battery', icon: Zap, label: '锂电板块' },
  { to: '/tin', icon: Zap, label: '锡板块' },
  { to: '/silicon', icon: Zap, label: '硅板块' },
];

const RouterSidebarItemLink = forwardRef<
  HTMLAnchorElement,
  { href?: string; children: React.ReactNode } & React.AnchorHTMLAttributes<HTMLAnchorElement>
>(({ href, children, ...props }, ref) => (
  <Link ref={ref} to={href ?? '/'} {...props}>
    {children}
  </Link>
));
RouterSidebarItemLink.displayName = 'RouterSidebarItemLink';

export function Layout() {
  const { pathname } = useLocation();
  const mainRef = React.useRef<HTMLElement>(null);
  const [showTop, setShowTop] = React.useState(false);
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [dark, setDark] = React.useState(() => {
    const stored = localStorage.getItem('theme');
    if (stored === 'dark') return true;
    if (stored === 'light') return false;
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const { top: backToTopTop, onMouseDown: onBackToTopDrag, onClickCapture: onBackToTopClickCapture } = useVerticalDrag(
    typeof window !== 'undefined' ? window.innerHeight - 240 : 120,
    200,
  );

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const onScroll = () => setShowTop(el.scrollTop > 240);
    el.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  const toggleDark = () => setDark((prev) => !prev);

  const pageTitle = pathname.startsWith('/tin')
    ? '锡板块'
    : pathname.startsWith('/silicon')
      ? '硅板块'
      : pathname.startsWith('/battery')
        ? '锂电板块'
        : '行情总览';
  const isIndustryPage = pathname.startsWith('/tin') || pathname.startsWith('/silicon') || pathname.startsWith('/battery');

  return (
    <div className="flex h-screen flex-col bg-muted">
      <Navbar fluid border className="z-30 shrink-0 bg-card">
        <div className="flex w-full items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              variant="ghost"
              onClick={() => setSidebarOpen((v) => !v)}
              className="lg:hidden"
              aria-label="打开导航"
              title="打开导航"
            >
              <Menu className="h-4 w-4" />
            </Button>
            <Link
              to="/"
              className="flex shrink-0 items-center gap-2 text-base font-bold tracking-tight text-foreground"
            >
              <BarChart3 className="h-5 w-5" />
              市场看板
            </Link>
            {!isIndustryPage && (
              <span className="hidden text-sm font-medium text-muted-foreground md:inline">
                {pageTitle}
              </span>
            )}
          </div>
          <Button
            variant="ghost"
            onClick={toggleDark}
            aria-label="切换深色模式"
            title="切换深色模式"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </Navbar>

      <div className="flex min-h-0 flex-1">
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/40 lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}
        <aside
          className={cn(
            'h-full shrink-0 border-r border-border bg-card',
            sidebarOpen ? 'fixed inset-y-0 left-0 z-40 w-64 shadow-xl lg:static lg:shadow-none' : 'hidden lg:block',
          )}
        >
          <Sidebar className="h-full">
            <SidebarItems>
              <SidebarItemGroup>
                {NAV.map(({ to, icon: Icon, label }) => {
                  const active =
                    to === '/overview'
                      ? pathname === '/' || pathname.startsWith('/overview')
                      : pathname.startsWith(to);
                  return (
                    <SidebarItem
                      key={to}
                      as={RouterSidebarItemLink}
                      href={to}
                      active={active}
                      icon={Icon}
                      className={
                        active
                          ? 'bg-accent font-semibold text-accent-foreground hover:bg-accent'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      }
                    >
                      {label}
                    </SidebarItem>
                  );
                })}
              </SidebarItemGroup>
            </SidebarItems>
          </Sidebar>
        </aside>
        <main ref={mainRef} className="min-w-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {showTop && (
        <div
          className="fixed right-4 z-50 flex cursor-grab select-none touch-none flex-col items-center gap-1.5"
          style={{ top: backToTopTop }}
          onMouseDown={onBackToTopDrag}
          onClickCapture={onBackToTopClickCapture}
        >
          <span className="rounded-md bg-card px-2 py-0.5 text-xs font-semibold text-muted-foreground shadow">
            回到顶部
          </span>
          <button
            onClick={() => mainRef.current?.scrollTo({ top: 0, behavior: 'smooth' })}
            className="flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition hover:bg-primary/90"
            aria-label="回到顶部"
            title="回到顶部"
          >
            <ArrowUp className="h-6 w-6" />
          </button>
        </div>
      )}
    </div>
  );
}
