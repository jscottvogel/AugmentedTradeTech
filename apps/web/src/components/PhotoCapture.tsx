"use client";

import React, { useState, useRef, useEffect } from "react";
import imageCompression from "browser-image-compression";
import { saveOfflinePhoto } from "../utils/indexedDB";
import { Camera, RefreshCw, AlertCircle, CheckCircle2, Trash2, CloudOff, Loader2 } from "lucide-react";

interface PhotoCaptureProps {
  jobId: string;
  stepKey: string;
  photoType: string;
  accessToken: string;
  isOnline: boolean;
  onUploadSuccess: (cdnUrl: string, photoId: string) => void;
  initialPhotoUrl?: string;
  placeholderText?: string;
}

export default function PhotoCapture({
  jobId,
  stepKey,
  photoType,
  accessToken,
  isOnline,
  onUploadSuccess,
  initialPhotoUrl,
  placeholderText = "Capture Photo"
}: PhotoCaptureProps) {
  const [photoUrl, setPhotoUrl] = useState<string | null>(initialPhotoUrl || null);
  const [status, setStatus] = useState<"idle" | "compressing" | "uploading" | "offline-saved" | "success" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const activeFileRef = useRef<Blob | null>(null);

  // Sync initialPhotoUrl when it changes externally
  useEffect(() => {
    if (initialPhotoUrl) {
      setPhotoUrl(initialPhotoUrl);
      setStatus("success");
    }
  }, [initialPhotoUrl]);

  const handleCaptureClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    console.log("PhotoCapture: handleFileChange triggered, file:", file?.name, "type:", file?.type, "size:", file?.size);
    if (!file) return;

    let processedFile: Blob = file;
    const MAX_SIZE = 2 * 1024 * 1024; // 2MB
    if (file.size > MAX_SIZE) {
      console.log("PhotoCapture: Image is larger than 2MB. Compressing...", { size: file.size });
      try {
        // 1. Client-side compression
        // 2MB max, max 2048px width/height, quality 0.85, automatically strips EXIF
        const options = {
          maxSizeMB: 2,
          maxWidthOrHeight: 2048,
          useWebWorker: false, // Disabled for robustness in headless environments
          onProgress: (percent: number) => {
            console.log(`PhotoCapture: Compression progress = ${percent}%`);
            setProgress(percent);
          }
        };

        processedFile = await imageCompression(file, options);
        console.log("PhotoCapture: Image compression finished successfully. New size:", processedFile.size);
      } catch (compressErr: any) {
        console.warn("PhotoCapture: Client-side image compression failed, falling back to original file:", compressErr);
        processedFile = file;
      }
    } else {
      console.log("PhotoCapture: Image is under 2MB limit. Bypassing compression.", { size: file.size });
    }

    try {
      activeFileRef.current = processedFile;

      // Update preview immediately using processed blob
      const localUrl = URL.createObjectURL(processedFile);
      setPhotoUrl(localUrl);

      if (!isOnline) {
        console.log("PhotoCapture: Device is offline. Saving photo to IndexedDB...");
        // 2. Offline Mode: save to IndexedDB
        setStatus("offline-saved");
        const { id } = await saveOfflinePhoto(
          jobId,
          stepKey,
          photoType,
          processedFile,
          `Offline capture for step: ${stepKey}`
        );
        console.log("PhotoCapture: Photo saved offline with ID:", id);
        onUploadSuccess(localUrl, id); // pass local URL & offline ID
      } else {
        console.log("PhotoCapture: Device is online. Directing to S3 upload flow...");
        // 3. Online Mode: upload to S3 directly
        await uploadFile(processedFile);
      }
    } catch (err: any) {
      console.error("PhotoCapture: Error in post-processing/saving flow:", err);
      setStatus("error");
      setErrorMsg(err.message || "Failed to process photo.");
    }
  };

  const uploadFile = async (fileBlob: Blob) => {
    console.log("PhotoCapture: uploadFile invoked, size:", fileBlob.size);
    setStatus("uploading");
    setProgress(0);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      // A. Get S3 Presigned URL
      console.log(`PhotoCapture: Requesting S3 presigned URL from ${API_URL}/jobs/${jobId}/photos/presign`);
      const presignRes = await fetch(`${API_URL}/jobs/${jobId}/photos/presign`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          photo_type: photoType
        })
      });

      console.log("PhotoCapture: S3 presign response status:", presignRes.status);

      if (!presignRes.ok) {
        throw new Error("Failed to get S3 upload signature.");
      }

      const { upload_url, s3_key, headers } = await presignRes.json();
      console.log("PhotoCapture: S3 signature received. S3 Key:", s3_key, "Upload URL:", upload_url);

      // B. Direct PUT upload with progress tracking
      console.log("PhotoCapture: Starting PUT request directly to S3...");
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", upload_url, true);

        // Apply headers returned by presign endpoint
        if (headers) {
          Object.entries(headers).forEach(([key, val]) => {
            xhr.setRequestHeader(key, val as string);
          });
        }

        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const pct = Math.round((event.loaded / event.total) * 100);
            console.log(`PhotoCapture: Direct PUT upload progress = ${pct}%`);
            setProgress(pct);
          }
        };

        xhr.onload = () => {
          console.log("PhotoCapture: PUT request onload status:", xhr.status);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            reject(new Error(`S3 upload failed with status ${xhr.status}`));
          }
        };

        xhr.onerror = (e) => {
          console.error("PhotoCapture: PUT request error event:", e);
          reject(new Error("Network error during S3 upload."));
        };

        xhr.send(fileBlob);
      });

      console.log("PhotoCapture: PUT upload to S3 finished successfully. Registering photo with backend...");

      // C. Register photo details in DB
      const registerRes = await fetch(`${API_URL}/jobs/${jobId}/photos`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          s3_key: s3_key,
          photo_type: photoType,
          caption: `Inspection photo for step: ${stepKey}`,
          file_size_bytes: fileBlob.size,
          mime_type: fileBlob.type
        })
      });

      console.log("PhotoCapture: Registration response status:", registerRes.status);

      if (!registerRes.ok) {
        throw new Error("Failed to register upload with server.");
      }

      const updatedJob = await registerRes.json();
      console.log("PhotoCapture: Registration succeeded. Updated job structure retrieved.");
      
      // Find the newly registered photo
      const matched = updatedJob.photos.find((p: any) => p.cdn_url.includes(s3_key));
      const finalCdnUrl = matched?.cdn_url || `${API_URL}/mock-s3-upload/${s3_key}`;
      const finalId = matched?.id || `jph_${Date.now()}`;

      console.log("PhotoCapture: Final CDN URL resolved:", finalCdnUrl, "Photo ID:", finalId);

      setPhotoUrl(finalCdnUrl);
      setStatus("success");
      onUploadSuccess(finalCdnUrl, finalId);
    } catch (err: any) {
      console.error("PhotoCapture: Upload error:", err);
      setStatus("error");
      setErrorMsg(err.message || "Failed to upload photo.");
    }
  };

  const handleRetry = () => {
    if (activeFileRef.current) {
      if (isOnline) {
        uploadFile(activeFileRef.current);
      } else {
        setStatus("offline-saved");
      }
    } else {
      handleCaptureClick();
    }
  };

  const handleRemove = () => {
    setPhotoUrl(null);
    setStatus("idle");
    setProgress(0);
    setErrorMsg(null);
    activeFileRef.current = null;
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="w-full flex flex-col items-center justify-center p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl backdrop-blur-md transition-all duration-300">
      <input
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        ref={fileInputRef}
        onChange={handleFileChange}
      />

      {status === "idle" && (
        <button
          type="button"
          onClick={handleCaptureClick}
          className="flex flex-col items-center gap-3 py-8 px-12 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-medium shadow-lg hover:shadow-cyan-500/20 active:scale-[0.98] transition-all duration-300 group cursor-pointer"
        >
          <Camera className="w-8 h-8 text-white group-hover:scale-110 transition-transform duration-300" />
          <span>{placeholderText}</span>
        </button>
      )}

      {status === "compressing" && (
        <div className="flex flex-col items-center gap-4 py-6 w-full max-w-xs">
          <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-cyan-400 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
          <span className="text-sm font-semibold text-slate-300">Compressing Image ({progress}%)</span>
        </div>
      )}

      {status === "uploading" && (
        <div className="flex flex-col items-center gap-4 py-6 w-full max-w-xs">
          <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-gradient-to-r from-indigo-500 to-cyan-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
          <span className="text-sm font-semibold text-slate-300">Uploading to Cloud ({progress}%)</span>
        </div>
      )}

      {status === "offline-saved" && photoUrl && (
        <div className="flex flex-col items-center gap-4 w-full">
          <div className="relative w-full aspect-video rounded-xl overflow-hidden border border-slate-700 bg-slate-950">
            <img src={photoUrl} alt="Captured" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-slate-950/40 flex items-center justify-center">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/90 text-slate-950 text-xs font-bold shadow-md animate-pulse">
                <CloudOff className="w-3.5 h-3.5" />
                <span>Saved Offline (Pending Connection)</span>
              </div>
            </div>
          </div>
          <div className="flex gap-3 w-full">
            <button
              type="button"
              onClick={handleCaptureClick}
              className="flex-1 py-2 px-4 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold border border-slate-700 text-sm active:scale-95 transition-all cursor-pointer"
            >
              Retake
            </button>
            <button
              type="button"
              onClick={handleRemove}
              className="py-2 px-3 rounded-lg bg-rose-950/60 hover:bg-rose-900 border border-rose-800 text-rose-300 font-semibold text-sm active:scale-95 transition-all cursor-pointer"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {status === "success" && photoUrl && (
        <div className="flex flex-col items-center gap-4 w-full">
          <div className="relative w-full aspect-video rounded-xl overflow-hidden border border-emerald-500/40 bg-slate-950">
            <img src={photoUrl} alt="Uploaded" className="w-full h-full object-cover" />
            <div className="absolute top-2 right-2 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/90 text-slate-950 text-[10px] font-bold shadow-md">
              <CheckCircle2 className="w-3 h-3" />
              <span>SAVED</span>
            </div>
          </div>
          <div className="flex gap-3 w-full">
            <button
              type="button"
              onClick={handleCaptureClick}
              className="flex-1 py-2 px-4 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold border border-slate-700 text-sm active:scale-95 transition-all cursor-pointer"
            >
              Retake
            </button>
            <button
              type="button"
              onClick={handleRemove}
              className="py-2 px-3 rounded-lg bg-rose-950/60 hover:bg-rose-900 border border-rose-800 text-rose-300 font-semibold text-sm active:scale-95 transition-all cursor-pointer"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="flex flex-col items-center gap-4 py-4 w-full max-w-xs text-center">
          <AlertCircle className="w-10 h-10 text-rose-500 animate-bounce" />
          <div className="flex flex-col gap-1">
            <span className="text-sm font-bold text-rose-400">Upload Failed</span>
            {errorMsg && <p className="text-xs text-slate-400 max-w-[200px] line-clamp-2">{errorMsg}</p>}
          </div>
          <div className="flex gap-2 w-full">
            <button
              type="button"
              onClick={handleRetry}
              className="flex-1 py-2 px-4 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold text-sm shadow-md active:scale-95 transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Retry Upload</span>
            </button>
            <button
              type="button"
              onClick={handleRemove}
              className="py-2 px-3 rounded-lg bg-slate-850 hover:bg-slate-800 border border-slate-700 text-slate-300 font-semibold text-sm active:scale-95 transition-all cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
