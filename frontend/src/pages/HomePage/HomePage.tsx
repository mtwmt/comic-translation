// HomePage - 翻譯主頁

import { useState } from 'react';
import { ImageUploader } from './image-upload';
import { TranslationResult, useTranslation } from './translation';
import { Button } from '@/shared/components/ui/Button';

export function HomePage() {
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const { translate, isTranslating, result, clearResult } = useTranslation();

  const handleImageSelected = (file: File) => {
    setSelectedImage(file);
    clearResult();
  };

  const handleTranslate = () => {
    if (selectedImage) {
      translate(selectedImage);
    }
  };

  const handleClear = () => {
    setSelectedImage(null);
    clearResult();
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-2">漫畫翻譯器</h1>
        <p className="text-base-content opacity-60">
          使用 AI 將日文漫畫翻譯成繁體中文
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6">
        <div>
          <ImageUploader onImageSelected={handleImageSelected} />
          {selectedImage && !result && (
            <div className="mt-4 flex justify-center">
              <Button
                variant="primary"
                size="lg"
                onClick={handleTranslate}
                loading={isTranslating}
                disabled={isTranslating}
              >
                {isTranslating ? '翻譯中...' : '開始翻譯'}
              </Button>
            </div>
          )}
        </div>

        <div>
          {result && <TranslationResult result={result} onClear={handleClear} />}
          {isTranslating && (
            <div className="flex flex-col items-center justify-center h-full space-y-4">
              <span className="loading loading-spinner loading-lg"></span>
              <p className="text-lg">AI 正在翻譯中，請稍候...</p>
              <p className="text-sm opacity-60">這可能需要 10-30 秒</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
