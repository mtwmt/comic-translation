// useImageUpload Hook

import { useState, useCallback } from 'react';
import { validateImageFile } from '@/shared/utils/validators';
import { createFilePreview } from '@/shared/utils/fileHelpers';
import { useToast } from '@/shared/hooks/useToast';
import type { UploadedImage } from './upload.types';

export function useImageUpload() {
  const [image, setImage] = useState<UploadedImage | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const toast = useToast();

  const uploadImage = useCallback(
    async (file: File) => {
      setIsUploading(true);

      try {
        // 驗證檔案
        const validation = validateImageFile(file);
        if (!validation.valid) {
          toast.error(validation.error || '檔案驗證失敗');
          return false;
        }

        // 建立預覽
        const preview = await createFilePreview(file);

        setImage({
          file,
          preview,
          id: `${Date.now()}-${file.name}`,
        });

        toast.success('圖片已載入');
        return true;
      } catch (error) {
        console.error('Upload error:', error);
        toast.error('圖片載入失敗');
        return false;
      } finally {
        setIsUploading(false);
      }
    },
    [toast]
  );

  const clearImage = useCallback(() => {
    if (image?.preview) {
      URL.revokeObjectURL(image.preview);
    }
    setImage(null);
  }, [image]);

  return {
    image,
    isUploading,
    uploadImage,
    clearImage,
    hasImage: !!image,
  };
}
