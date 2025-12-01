// Settings Form 元件

import { useState } from 'react';
import { Input } from '@/shared/components/ui/Input';
import { Button } from '@/shared/components/ui/Button';
import { Card } from '@/shared/components/ui/Card';
import { useToast } from '@/shared/hooks/useToast';
import { useSettings } from './useSettings';

export function SettingsForm() {
  const { apiKey, globalPrompt, setApiKey, setGlobalPrompt } = useSettings();
  const toast = useToast();

  const [formData, setFormData] = useState({
    apiKey: apiKey || '',
    globalPrompt: globalPrompt || '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!formData.apiKey.trim()) {
      toast.error('請輸入 API Key');
      return;
    }

    setApiKey(formData.apiKey);
    setGlobalPrompt(formData.globalPrompt);
    toast.success('設定已儲存');
  };

  return (
    <Card title="API 設定">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Gemini API Key"
          type="password"
          placeholder="請輸入您的 Gemini API Key"
          value={formData.apiKey}
          onChange={(e) =>
            setFormData({ ...formData, apiKey: e.target.value })
          }
          required
        />

        <div className="form-control w-full">
          <label className="label">
            <span className="label-text">全域 Prompt（選填）</span>
          </label>
          <textarea
            className="textarea textarea-bordered h-24"
            placeholder="例如：保持幽默風格、使用台灣用語"
            value={formData.globalPrompt}
            onChange={(e) =>
              setFormData({ ...formData, globalPrompt: e.target.value })
            }
          />
        </div>

        <Button type="submit" variant="primary" size="md">
          儲存設定
        </Button>
      </form>
    </Card>
  );
}
