const DB_NAME = "ATTPhotoOfflineDB";
const STORE_NAME = "offlinePhotos";
const DB_VERSION = 1;

export interface OfflinePhoto {
  id: string;
  jobId: string;
  stepKey: string;
  photoType: string;
  file: Blob;
  caption: string;
  timestamp: number;
}

export function initDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !window.indexedDB) {
      reject(new Error("IndexedDB not supported in this environment"));
      return;
    }

    const request = window.indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = (event) => {
      reject(new Error("Failed to open IndexedDB"));
    };

    request.onsuccess = (event) => {
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
  });
}

export async function saveOfflinePhoto(
  jobId: string,
  stepKey: string,
  photoType: string,
  file: Blob,
  caption: string
): Promise<{ id: string; objectUrl: string }> {
  const db = await initDb();
  const id = `off_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  const photoRecord: OfflinePhoto = {
    id,
    jobId,
    stepKey,
    photoType,
    file,
    caption,
    timestamp: Date.now(),
  };

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.add(photoRecord);

    request.onsuccess = () => {
      const objectUrl = URL.createObjectURL(file);
      resolve({ id, objectUrl });
    };

    request.onerror = () => {
      reject(new Error("Failed to save photo to IndexedDB"));
    };
  });
}

export async function getOfflinePhotos(jobId: string): Promise<OfflinePhoto[]> {
  const db = await initDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();

    request.onsuccess = () => {
      const allPhotos = request.result as OfflinePhoto[];
      // Filter by jobId
      const filtered = allPhotos.filter((p) => p.jobId === jobId);
      resolve(filtered);
    };

    request.onerror = () => {
      reject(new Error("Failed to retrieve offline photos"));
    };
  });
}

export async function deleteOfflinePhoto(id: string): Promise<void> {
  const db = await initDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.delete(id);

    request.onsuccess = () => {
      resolve();
    };

    request.onerror = () => {
      reject(new Error("Failed to delete offline photo"));
    };
  });
}
