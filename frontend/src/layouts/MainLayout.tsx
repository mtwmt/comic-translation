// MainLayout 元件 - 主要佈局

import { Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { Header } from './Header';

export function MainLayout() {
  return (
    <div className="min-h-screen flex flex-col bg-base-200">
      <Header />
      <main className="flex-1 container mx-auto p-4 max-w-7xl">
        <Outlet />
      </main>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            background: '#363636',
            color: '#fff',
          },
        }}
      />
    </div>
  );
}
