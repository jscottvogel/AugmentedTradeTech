import { openDB, DBSchema, IDBPDatabase } from 'idb';

const DB_NAME = "ATT_PWA_OfflineDB";
const DB_VERSION = 1;

export interface SyncQueueItem {
  id: string;
  entity_type: 'job' | 'note' | 'part' | 'tech';
  entity_id: string;
  operation: 'status' | 'create' | 'delete' | 'availability' | 'workflow';
  payload: any;
  client_timestamp: number;
  idempotency_key: string;
  status: 'pending' | 'syncing' | 'done' | 'failed';
}

export interface PhotoQueueItem {
  id: string;
  job_id: string;
  step_key: string;
  photo_type: string;
  blob: Blob;
  status: 'pending' | 'uploading' | 'done' | 'failed';
}

interface ATTDBSchema extends DBSchema {
  jobs: {
    key: string;
    value: any;
  };
  sync_queue: {
    key: string;
    value: SyncQueueItem;
    indexes: { 'by-timestamp': number };
  };
  photos_queue: {
    key: string;
    value: PhotoQueueItem;
  };
  ai_cache: {
    key: string;
    value: {
      job_id: string;
      data: any;
    };
  };
}

let dbPromise: Promise<IDBPDatabase<ATTDBSchema>> | null = null;

function getDB(): Promise<IDBPDatabase<ATTDBSchema>> {
  if (typeof window === "undefined") {
    throw new Error("IndexedDB is only available in the browser.");
  }
  if (!dbPromise) {
    dbPromise = openDB<ATTDBSchema>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('jobs')) {
          db.createObjectStore('jobs', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('sync_queue')) {
          const syncStore = db.createObjectStore('sync_queue', { keyPath: 'id' });
          syncStore.createIndex('by-timestamp', 'client_timestamp');
        }
        if (!db.objectStoreNames.contains('photos_queue')) {
          db.createObjectStore('photos_queue', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('ai_cache')) {
          db.createObjectStore('ai_cache', { keyPath: 'job_id' });
        }
      },
    });
  }
  return dbPromise;
}

// === JOBS STORE HELPERS ===
export async function getCachedJob(id: string): Promise<any | null> {
  const db = await getDB();
  return (await db.get('jobs', id)) || null;
}

export async function getAllCachedJobs(): Promise<any[]> {
  const db = await getDB();
  return db.getAll('jobs');
}

export async function cacheJobs(jobs: any[]): Promise<void> {
  const db = await getDB();
  const tx = db.transaction('jobs', 'readwrite');
  for (const job of jobs) {
    const existing = await tx.store.get(job.id);
    if (existing) {
      await tx.store.put({ ...existing, ...job });
    } else {
      await tx.store.put(job);
    }
  }
  await tx.done;
}

export async function cacheJob(job: any): Promise<void> {
  const db = await getDB();
  const existing = await db.get('jobs', job.id);
  if (existing) {
    await db.put('jobs', { ...existing, ...job });
  } else {
    await db.put('jobs', job);
  }
}

export async function clearCachedJobs(): Promise<void> {
  const db = await getDB();
  await db.clear('jobs');
}

// === SYNC QUEUE STORE HELPERS ===
export async function enqueueMutation(item: Omit<SyncQueueItem, 'status' | 'id'> & { id?: string }): Promise<SyncQueueItem> {
  const db = await getDB();
  const id = item.id || `mut_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
  const syncItem: SyncQueueItem = {
    ...item,
    id,
    status: 'pending'
  };
  await db.put('sync_queue', syncItem);
  return syncItem;
}

export async function getSyncQueue(): Promise<SyncQueueItem[]> {
  const db = await getDB();
  const items = await db.getAll('sync_queue');
  // Sort chronologically by timestamp
  return items.sort((a, b) => a.client_timestamp - b.client_timestamp);
}

export async function updateMutationStatus(id: string, status: SyncQueueItem['status']): Promise<void> {
  const db = await getDB();
  const item = await db.get('sync_queue', id);
  if (item) {
    item.status = status;
    await db.put('sync_queue', item);
  }
}

export async function deleteMutation(id: string): Promise<void> {
  const db = await getDB();
  await db.delete('sync_queue', id);
}

// === PHOTOS QUEUE STORE HELPERS ===
export async function enqueuePhoto(photo: Omit<PhotoQueueItem, 'status'>): Promise<PhotoQueueItem> {
  const db = await getDB();
  const photoItem: PhotoQueueItem = {
    ...photo,
    status: 'pending'
  };
  await db.put('photos_queue', photoItem);
  return photoItem;
}

export async function getPhotosQueue(jobId?: string): Promise<PhotoQueueItem[]> {
  const db = await getDB();
  const photos = await db.getAll('photos_queue');
  if (jobId) {
    return photos.filter(p => p.job_id === jobId);
  }
  return photos;
}

export async function updatePhotoStatus(id: string, status: PhotoQueueItem['status']): Promise<void> {
  const db = await getDB();
  const item = await db.get('photos_queue', id);
  if (item) {
    item.status = status;
    await db.put('photos_queue', item);
  }
}

export async function deleteQueuedPhoto(id: string): Promise<void> {
  const db = await getDB();
  await db.delete('photos_queue', id);
}

// === AI CACHE STORE HELPERS ===
export async function getCachedAiResponse(jobId: string): Promise<any | null> {
  const db = await getDB();
  const record = await db.get('ai_cache', jobId);
  return record ? record.data : null;
}

export async function cacheAiResponse(jobId: string, data: any): Promise<void> {
  const db = await getDB();
  await db.put('ai_cache', { job_id: jobId, data });
}

// === BACKWARDS COMPATIBILITY HELPERS FOR GUIDED INSPECTION ===
// This maps getOfflinePhotos, deleteOfflinePhoto, saveOfflinePhoto to photos_queue

export async function saveOfflinePhoto(
  jobId: string,
  stepKey: string,
  photoType: string,
  file: Blob,
  caption?: string
): Promise<{ id: string; objectUrl: string }> {
  const id = `off_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
  await enqueuePhoto({
    id,
    job_id: jobId,
    step_key: stepKey,
    photo_type: photoType,
    blob: file
  });
  const objectUrl = URL.createObjectURL(file);
  return { id, objectUrl };
}

export async function getOfflinePhotos(jobId: string): Promise<any[]> {
  const queued = await getPhotosQueue(jobId);
  // Map back to the layout expected by GuidedInspection
  return queued.map(q => ({
    id: q.id,
    jobId: q.job_id,
    stepKey: q.step_key,
    photoType: q.photo_type,
    file: q.blob,
    caption: `Offline capture for step: ${q.step_key}`,
    timestamp: parseInt(q.id.split('_')[1]) || Date.now()
  }));
}

export async function deleteOfflinePhoto(id: string): Promise<void> {
  await deleteQueuedPhoto(id);
}
