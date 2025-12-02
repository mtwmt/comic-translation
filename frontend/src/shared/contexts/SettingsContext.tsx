// SettingsContext - 使用 React Context API 取代 Zustand
// ✅ 遵循 React 官方最佳實踐
// 參考：https://react.dev/learn/passing-data-deeply-with-context

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { STORAGE_KEYS } from '@/shared/constants/config';
import type { Settings } from '@/pages/SettingsPage/settings.types';

// 定義 Context 型別
interface SettingsContextType extends Settings {
  // Actions
  setApiKey: (apiKey: string) => void;
  setGlobalPrompt: (prompt: string) => void;
  addNameMapping: (original: string, translation: string) => void;
  removeNameMapping: (original: string) => void;
  updateNameMapping: (mappings: Record<string, string>) => void;
  clearSettings: () => void;
  hasApiKey: boolean;
}

// ✅ 官方最佳實踐：建立 Context，預設值為 undefined
const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

// 初始狀態
const initialState: Settings = {
  apiKey: '',
  nameMapping: {},
  globalPrompt: '',
};

// ✅ 官方最佳實踐：Provider 元件
export function SettingsProvider({ children }: { children: ReactNode }) {
  // ✅ 官方最佳實踐：使用 lazy initialization 從 localStorage 讀取
  const [settings, setSettings] = useState<Settings>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.SETTINGS);
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...initialState, ...parsed };
      }
      return initialState;
    } catch (error) {
      console.error('Failed to load settings from localStorage:', error);
      return initialState;
    }
  });

  // ✅ 官方最佳實踐：useEffect 同步狀態到 localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.SETTINGS, JSON.stringify(settings));
    } catch (error) {
      console.error('Failed to save settings to localStorage:', error);
    }
  }, [settings]); // 只追蹤 settings

  // ✅ 官方最佳實踐：使用 useCallback 記憶化函數，避免子元件不必要的 re-render
  const setApiKey = useCallback((apiKey: string) => {
    setSettings((prev) => ({ ...prev, apiKey }));
  }, []);

  const setGlobalPrompt = useCallback((prompt: string) => {
    setSettings((prev) => ({ ...prev, globalPrompt: prompt }));
  }, []);

  const addNameMapping = useCallback((original: string, translation: string) => {
    setSettings((prev) => ({
      ...prev,
      nameMapping: {
        ...prev.nameMapping,
        [original]: translation,
      },
    }));
  }, []);

  const removeNameMapping = useCallback((original: string) => {
    setSettings((prev) => {
      const { [original]: _, ...rest } = prev.nameMapping;
      return { ...prev, nameMapping: rest };
    });
  }, []);

  const updateNameMapping = useCallback((mappings: Record<string, string>) => {
    setSettings((prev) => ({ ...prev, nameMapping: mappings }));
  }, []);

  const clearSettings = useCallback(() => {
    setSettings(initialState);
  }, []);

  // ✅ 官方最佳實踐：使用 useMemo 優化（可選，這裡因為不複雜所以不必要）
  const value: SettingsContextType = {
    ...settings,
    setApiKey,
    setGlobalPrompt,
    addNameMapping,
    removeNameMapping,
    updateNameMapping,
    clearSettings,
    hasApiKey: !!settings.apiKey,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// ✅ 官方最佳實踐：自訂 Hook，封裝 useContext 並提供錯誤檢查
export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
