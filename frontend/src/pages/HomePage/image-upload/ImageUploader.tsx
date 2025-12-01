// ImageUploader 元件 - 使用 react-dropzone 官方庫

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/shared/components/ui/Button";
import { Card } from "@/shared/components/ui/Card";
import { useImageUpload } from "./useImageUpload";

interface ImageUploaderProps {
  onImageSelected?: (file: File) => void;
}

export function ImageUploader({ onImageSelected }: ImageUploaderProps) {
  const { image, isUploading, uploadImage, clearImage } = useImageUpload();

  // 使用 react-dropzone 的 onDrop callback
  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (file) {
        const success = await uploadImage(file);
        if (success && onImageSelected) {
          onImageSelected(file);
        }
      }
    },
    [uploadImage, onImageSelected]
  );

  // 使用 react-dropzone hook
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/webp": [".webp"],
    },
    maxSize: 10 * 1024 * 1024, // 10MB
    multiple: false,
    disabled: isUploading,
  });

  const handleClear = () => {
    clearImage();
  };

  return (
    <Card title="上傳圖片">
      {!image ? (
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
            isDragActive
              ? "border-primary bg-base-200"
              : "border-base-300 hover:border-primary hover:bg-base-200"
          }`}
        >
          <input {...getInputProps()} />
          <div className="space-y-4">
            <svg
              className="mx-auto h-12 w-12 text-base-content opacity-40"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div className="text-base-content">
              <p className="text-lg font-semibold">
                {isDragActive ? "放開以上傳圖片" : "點擊上傳或拖曳圖片到此處"}
              </p>
              <p className="text-sm opacity-60 mt-2">
                支援 PNG, JPG, JPEG, WebP (最大 10MB)
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="relative rounded-lg overflow-hidden border border-base-300">
            <img
              src={image.preview}
              alt="Preview"
              className="w-full h-auto max-h-96 object-contain bg-base-200"
            />
          </div>
          <div className="flex justify-between items-center">
            <p className="text-sm opacity-60">{image.file.name}</p>
            <Button variant="error" size="sm" onClick={handleClear}>
              移除
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
