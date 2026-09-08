import { Suspense, lazy } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';

const Overview = lazy(() => import('@/pages/Overview').then((m) => ({ default: m.Overview })));
const Metals = lazy(() => import('@/pages/Metals').then((m) => ({ default: m.Metals })));
const Battery = lazy(() => import('@/pages/Battery').then((m) => ({ default: m.Battery })));
const Silicon = lazy(() => import('@/pages/Silicon').then((m) => ({ default: m.Silicon })));

function PageLoader() {
  return (
    <div className='flex h-[60vh] items-center justify-center text-muted-foreground dark:text-slate-400'>
      <p>加载中…</p>
    </div>
  );
}

export function Router() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path='/' element={
          <Suspense fallback={<PageLoader />}><Overview /></Suspense>
        } />
        <Route path='/overview' element={
          <Suspense fallback={<PageLoader />}><Overview /></Suspense>
        } />
        <Route path='/tin' element={
          <Suspense fallback={<PageLoader />}><Metals /></Suspense>
        } />
        <Route path='/silicon' element={
          <Suspense fallback={<PageLoader />}><Silicon /></Suspense>
        } />
        <Route path='/battery' element={
          <Suspense fallback={<PageLoader />}><Battery /></Suspense>
        } />
      </Route>
    </Routes>
  );
}
