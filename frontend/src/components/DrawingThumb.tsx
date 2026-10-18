"use client";

import { useState } from "react";
import { FileImage } from "lucide-react";
import { drawingFileUrl, drawingPagePreviewUrl } from "@/lib/api";

export default function DrawingThumb({ id, fileType, className = "w-16 h-12" }: { id: string; fileType: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  const src = fileType === "pdf" ? drawingPagePreviewUrl(id, 1) : drawingFileUrl(id);
  return (
    <div className={`${className} border border-border rounded bg-white flex items-center justify-center overflow-hidden shrink-0`}>
      {failed ? (
        <FileImage size={18} className="text-steel-light" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="max-w-full max-h-full object-contain" onError={() => setFailed(true)} />
      )}
    </div>
  );
}
