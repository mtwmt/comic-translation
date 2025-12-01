// useSettings Hook - 封裝 Settings Store
// ✅ Zustand 最佳實踐：使用自定義 Hook 封裝 store，使用 selectors

import { useSettingsStore } from './settingsStore';

export function useSettings() {
  // ✅ 使用 selectors 避免不必要的 re-render
  const apiKey = useSettingsStore((state) => state.apiKey);
  const nameMapping = useSettingsStore((state) => state.nameMapping);
  const globalPrompt = useSettingsStore((state) => state.globalPrompt);

  const setApiKey = useSettingsStore((state) => state.setApiKey);
  const setGlobalPrompt = useSettingsStore((state) => state.setGlobalPrompt);
  const addNameMapping = useSettingsStore((state) => state.addNameMapping);
  const removeNameMapping = useSettingsStore((state) => state.removeNameMapping);
  const updateNameMapping = useSettingsStore((state) => state.updateNameMapping);

  return {
    apiKey,
    nameMapping,
    globalPrompt,
    setApiKey,
    setGlobalPrompt,
    addNameMapping,
    removeNameMapping,
    updateNameMapping,
    hasApiKey: !!apiKey,
  };
}
