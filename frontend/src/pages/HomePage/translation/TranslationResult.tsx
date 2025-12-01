// TranslationResult 元件

import { Button } from '@/shared/components/ui/Button';
import { Card } from '@/shared/components/ui/Card';
import { downloadFile } from '@/shared/utils/fileHelpers';
import { translationApi } from './translationApi';
import { useToast } from '@/shared/hooks/useToast';
import type { TranslationResult as TranslationResultType } from './translation.types';

interface TranslationResultProps {
  result: TranslationResultType;
  onClear?: () => void;
}

export function TranslationResult({ result, onClear }: TranslationResultProps) {
  const toast = useToast();

  const handleDownload = async () => {
    try {
      const blob = await translationApi.downloadResult(result.filename);
      downloadFile(blob, result.filename);
      toast.success('下載完成');
    } catch (error) {
      console.error('Download error:', error);
      toast.error('下載失敗');
    }
  };

  return (
    <Card title="翻譯結果">
      <div className="space-y-4">
        <div className="relative rounded-lg overflow-hidden border border-base-300">
          <img
            src={result.imageUrl}
            alt="Translation result"
            className="w-full h-auto max-h-96 object-contain bg-base-200"
          />
        </div>

        <div className="flex gap-2 justify-end">
          <Button variant="primary" onClick={handleDownload}>
            下載圖片
          </Button>
          {onClear && (
            <Button variant="ghost" onClick={onClear}>
              重新翻譯
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
