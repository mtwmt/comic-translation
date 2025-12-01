// Settings Zustand Store - 遵循最佳實踐
// ✅ Store 定義在元件外部
// ✅ 整合 localStorage persistence

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { STORAGE_KEYS } from '@/shared/constants/config';
import type { Settings } from './settings.types';

interface SettingsState extends Settings {
  // Actions
  setApiKey: (apiKey: string) => void;
  setGlobalPrompt: (prompt: string) => void;
  addNameMapping: (original: string, translation: string) => void;
  removeNameMapping: (original: string) => void;
  updateNameMapping: (mappings: Record<string, string>) => void;
  clearSettings: () => void;
}

const initialState: Settings = {
  apiKey: '',
  nameMapping: {},
  globalPrompt: '',
};

// ✅ Zustand 最佳實踐：Store 定義在元件外部
export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      ...initialState,

      setApiKey: (apiKey) =>
        set({ apiKey }),

      setGlobalPrompt: (prompt) =>
        set({ globalPrompt: prompt }),

      addNameMapping: (original, translation) =>
        set((state) => ({
          nameMapping: {
            ...state.nameMapping,
            [original]: translation,
          },
        })),

      removeNameMapping: (original) =>
        set((state) => {
          const { [original]: _, ...rest } = state.nameMapping;
          return { nameMapping: rest };
        }),

      updateNameMapping: (mappings) =>
        set({ nameMapping: mappings }),

      clearSettings: () => set(initialState),
    }),
    {
      name: STORAGE_KEYS.SETTINGS,
    }
  )
);
