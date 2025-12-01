// Translation API

import apiClient from '@/api/client';
import type { TranslationRequest, TranslationResponse } from './translation.types';

export const translationApi = {
  // 設定翻譯配置
  async setConfig(config: {
    api_key: string;
    name_mapping?: Record<string, string>;
    global_prompt?: string;
  }): Promise<{ ok: boolean; message: string }> {
    const response = await apiClient.post('/config', config);
    return response.data;
  },

  // 翻譯圖片
  async translateImage(request: TranslationRequest): Promise<TranslationResponse> {
    const formData = new FormData();
    formData.append('file', request.image);

    if (request.nameMapping && Object.keys(request.nameMapping).length > 0) {
      formData.append('name_mapping', JSON.stringify(request.nameMapping));
    }

    if (request.extraPrompt) {
      formData.append('extra_prompt', request.extraPrompt);
    }

    const response = await apiClient.post<TranslationResponse>(
      '/translate',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );

    return response.data;
  },

  // 下載翻譯結果
  async downloadResult(filename: string): Promise<Blob> {
    const response = await apiClient.get(`/download/${filename}`, {
      responseType: 'blob',
    });

    return response.data;
  },
};
