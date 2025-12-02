// useTranslation Hook - 使用 React 19 useActionState

import { useState } from 'react';
import { translationApi } from './translationApi';
import { useToast } from '@/shared/hooks/useToast';
import { useSettings } from '@/pages/SettingsPage';
import type { TranslationResult } from './translation.types';

export function useTranslation() {
  const [isTranslating, setIsTranslating] = useState(false);
  const [result, setResult] = useState<TranslationResult | null>(null);
  const toast = useToast();
  const { apiKey, nameMapping, globalPrompt, hasApiKey } = useSettings();

  const translate = async (image: File) => {
    if (!hasApiKey) {
      toast.error('請先在設定頁面輸入 Gemini API Key');
      return;
    }

    setIsTranslating(true);
    setResult(null);

    try {
      // 先設定 API Key 到後端
      await translationApi.setConfig({
        api_key: apiKey,
        name_mapping: nameMapping,
        global_prompt: globalPrompt,
      });

      const response = await translationApi.translateImage({
        image,
        nameMapping,
        extraPrompt: globalPrompt,
      });

      if (response.success && response.output_url) {
        setResult({
          imageUrl: response.output_url,
          filename: response.filename,
          timestamp: new Date(),
        });
        toast.success('翻譯完成！');
      } else {
        toast.error(response.error || '翻譯失敗');
      }
    } catch (error) {
      console.error('Translation error:', error);
      toast.error('翻譯過程中發生錯誤');
    } finally {
      setIsTranslating(false);
    }
  };

  const clearResult = () => {
    setResult(null);
  };

  return {
    translate,
    isTranslating,
    result,
    clearResult,
    hasResult: !!result,
  };
}
