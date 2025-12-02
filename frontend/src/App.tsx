// App.tsx - 根元件，配置 React Router
// ✅ React 官方最佳實踐：在最頂層設定 Context Provider

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { SettingsProvider } from './shared/contexts/SettingsContext';
import { MainLayout } from './layouts/MainLayout';
import { TranslationPage } from './pages/TranslationPage';
import { SettingsPage } from './pages/SettingsPage';
import { ROUTES } from './shared/constants/config';

function App() {
  return (
    // ✅ 官方最佳實踐：Provider 包裹整個應用，讓所有元件都能存取
    <SettingsProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path={ROUTES.HOME} element={<TranslationPage />} />
            <Route path={ROUTES.SETTINGS} element={<SettingsPage />} />
            <Route path="*" element={<Navigate to={ROUTES.HOME} replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SettingsProvider>
  );
}

export default App;
