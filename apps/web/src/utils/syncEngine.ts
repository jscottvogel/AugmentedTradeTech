import {
  getSyncQueue,
  deleteMutation,
  updateMutationStatus,
  getPhotosQueue,
  deleteQueuedPhoto,
  updatePhotoStatus,
  cacheJobs,
  cacheJob,
  getCachedJob
} from './indexedDB';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let isSyncingActive = false;
let syncNeedsReplay = false;

export async function triggerBackgroundSync(
  accessToken: string,
  onSyncStateChange?: (state: 'idle' | 'syncing' | 'success' | 'error') => void
): Promise<void> {
  if (isSyncingActive) {
    console.log('[Sync Engine] Sync is already in progress. Queueing replay.');
    syncNeedsReplay = true;
    return;
  }
  if (!accessToken) {
    console.log('[Sync Engine] No access token available. Skipping background sync.');
    return;
  }

  isSyncingActive = true;
  onSyncStateChange?.('syncing');

  try {
    do {
      syncNeedsReplay = false;
      console.log('[Sync Engine] Starting background sync...');

      // 1. Flush sync_queue in chronological client_timestamp order
      await flushSyncQueue(accessToken);

      // 2. Upload pending photos from photos_queue
      await flushPhotosQueue(accessToken);

      // 3. Pull fresh job data from API
      await pullFreshJobs(accessToken);
    } while (syncNeedsReplay);

    console.log('[Sync Engine] Background sync completed successfully!');
    onSyncStateChange?.('success');
  } catch (err) {
    console.error('[Sync Engine] Background sync failed:', err);
    onSyncStateChange?.('error');
    throw err;
  } finally {
    isSyncingActive = false;
  }
}

async function flushSyncQueue(accessToken: string): Promise<void> {
  const queue = await getSyncQueue();
  if (queue.length === 0) {
    console.log('[Sync Engine] No pending mutations in sync_queue.');
    return;
  }

  console.log(`[Sync Engine] Flushing ${queue.length} mutations in bulk...`);

  // Set all to syncing
  for (const item of queue) {
    await updateMutationStatus(item.id, 'syncing');
  }

  const items = queue.map(item => ({
    idempotency_key: item.idempotency_key,
    entity_type: item.entity_type,
    entity_id: item.entity_id,
    operation: item.operation,
    payload: item.payload,
    client_timestamp: item.client_timestamp
  }));

  const url = `${API_URL}/sync/flush`;
  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${accessToken}`
  };

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ items })
    });

    if (!res.ok) {
      for (const item of queue) {
        await updateMutationStatus(item.id, 'failed');
      }
      throw new Error(`Sync flush failed: status ${res.status}`);
    }

    const data = await res.json();
    const results = data.results || [];
    const resultsMap = new Map<string, any>(results.map((r: any) => [r.idempotency_key, r]));

    let hasConflict = false;

    for (const item of queue) {
      const result = resultsMap.get(item.idempotency_key);
      if (!result) {
        await updateMutationStatus(item.id, 'failed');
        continue;
      }

      if (result.status === 'applied') {
        const resData = result.server_response;
        if (resData) {
          if (resData.id && typeof resData.job_number === 'string') {
            await cacheJob(resData);
          } else if (item.entity_type === 'job' && item.operation === 'workflow' && resData.step_data) {
            // Update cached job's inspection_data
            const cachedJob = await getCachedJob(item.entity_id);
            if (cachedJob) {
              if (!cachedJob.inspection_data) cachedJob.inspection_data = {};
              cachedJob.inspection_data[item.payload.step] = resData.step_data;
              await cacheJob(cachedJob);
            }

            // Update cached workflow progress
            const cachedWf = await getCachedJob(`workflow_${item.entity_id}`);
            if (cachedWf) {
              if (!cachedWf.progress) cachedWf.progress = {};
              cachedWf.progress[item.payload.step] = resData.step_data;
              await cacheJob(cachedWf);
            }
          }
        }
        await deleteMutation(item.id);
      } else if (result.status === 'conflict') {
        hasConflict = true;
        const resData = result.server_response; // Authoritative server state
        if (resData && resData.id && typeof resData.job_number === 'string') {
          await cacheJob(resData);
        }
        await deleteMutation(item.id);
      } else {
        // failed or anything else
        await updateMutationStatus(item.id, 'failed');
      }
    }

    if (hasConflict) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('sync-conflict'));
      }
    }
  } catch (err) {
    for (const item of queue) {
      await updateMutationStatus(item.id, 'failed');
    }
    console.error('[Sync Engine] Failed to flush sync queue:', err);
    throw err;
  }
}

async function flushPhotosQueue(accessToken: string): Promise<void> {
  const queue = await getPhotosQueue();
  if (queue.length === 0) {
    console.log('[Sync Engine] No pending photos in photos_queue.');
    return;
  }

  console.log(`[Sync Engine] Uploading ${queue.length} pending photos...`);

  for (const item of queue) {
    await updatePhotoStatus(item.id, 'uploading');

    try {
      console.log(`[Sync Engine] Requesting S3 presigned URL for photo type ${item.photo_type} on job ${item.job_id}`);
      
      // A. Get Presigned URL
      const presignRes = await fetch(`${API_URL}/jobs/${item.job_id}/photos/presign`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          photo_type: item.photo_type
        })
      });

      if (!presignRes.ok) {
        throw new Error(`Failed to get S3 signature: status ${presignRes.status}`);
      }

      const { upload_url, s3_key, headers } = await presignRes.json();

      // B. Direct S3 Upload
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('PUT', upload_url, true);
        if (headers) {
          Object.entries(headers).forEach(([k, v]) => {
            xhr.setRequestHeader(k, v as string);
          });
        }
        xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`S3 PUT failed: ${xhr.status}`));
        xhr.onerror = () => reject(new Error('Network error during S3 upload'));
        xhr.send(item.blob);
      });

      // C. Register Photo details in DB using /sync/photos/confirm
      const registerRes = await fetch(`${API_URL}/sync/photos/confirm`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          photo_uploads: [{
            idempotency_key: item.id || `photo_ik_${Date.now()}`,
            s3_key: s3_key,
            job_id: item.job_id,
            step_key: item.step_key,
            photo_type: item.photo_type
          }]
        })
      });

      if (!registerRes.ok) {
        throw new Error(`Failed to register photo: status ${registerRes.status}`);
      }

      const confirmData = await registerRes.json();
      const photoResult = confirmData.results?.[0];
      if (!photoResult || photoResult.status === 'error') {
        throw new Error(`Failed to register photo: ${photoResult?.message || 'unknown error'}`);
      }
      console.log('[Sync Engine] Photo registered successfully in database.');

      // D. If this photo is part of an active workflow step progress, save it in workflow step inputs
      if (item.step_key) {
        const cdnDomain = process.env.NEXT_PUBLIC_CDN_DOMAIN || "media.augmentedtradetech.com";
        const finalCdnUrl = `https://${cdnDomain}/${s3_key}`;
        const finalId = photoResult.photo_id;

        console.log(`[Sync Engine] Registering photo reference into workflow step: ${item.step_key}`);
        
        const stepUpdateRes = await fetch(`${API_URL}/jobs/${item.job_id}/workflow/${item.step_key}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`
          },
          body: JSON.stringify({
            inputs: {
              photo_url: finalCdnUrl,
              photo_id: finalId,
              caption: `Sync photo for step: ${item.step_key}`
            },
            skipped: false,
            idempotency_key: `sync_ik_${item.id}`
          })
        });

        if (stepUpdateRes.ok) {
          try {
            const stepUpdateData = await stepUpdateRes.json();
            if (stepUpdateData && stepUpdateData.step_data) {
              // Update cached job
              const cachedJob = await getCachedJob(item.job_id);
              if (cachedJob) {
                if (!cachedJob.inspection_data) cachedJob.inspection_data = {};
                cachedJob.inspection_data[item.step_key] = stepUpdateData.step_data;
                await cacheJob(cachedJob);
              }
              // Update cached workflow
              const cachedWf = await getCachedJob(`workflow_${item.job_id}`);
              if (cachedWf) {
                if (!cachedWf.progress) cachedWf.progress = {};
                cachedWf.progress[item.step_key] = stepUpdateData.step_data;
                await cacheJob(cachedWf);
              }
            }
          } catch (err) {
            console.warn("[Sync Engine] Failed to update cache after sync photo workflow association:", err);
          }
        }
      }

      // Sync complete, delete from IndexedDB photos_queue
      await deleteQueuedPhoto(item.id);
      console.log(`[Sync Engine] Synced photo item ${item.id} completed.`);
    } catch (err) {
      await updatePhotoStatus(item.id, 'failed');
      console.error(`[Sync Engine] Failed to sync photo item ${item.id}:`, err);
      throw err; // Stop syncing remaining photos if one fails to preserve connection order
    }
  }
}

async function pullFreshJobs(accessToken: string): Promise<void> {
  console.log('[Sync Engine] Pulling fresh job list from API...');
  
  try {
    const [resToday, resUpcoming] = await Promise.all([
      fetch(`${API_URL}/me/jobs/today`, { headers: { Authorization: `Bearer ${accessToken}` } }),
      fetch(`${API_URL}/me/jobs/upcoming`, { headers: { Authorization: `Bearer ${accessToken}` } })
    ]);

    let freshJobs: any[] = [];
    if (resToday.ok) {
      const dataToday = await resToday.json();
      freshJobs = freshJobs.concat(dataToday);
    }
    if (resUpcoming.ok) {
      const dataUpcoming = await resUpcoming.json();
      freshJobs = freshJobs.concat(dataUpcoming);
    }

    if (freshJobs.length > 0) {
      await cacheJobs(freshJobs);
      console.log(`[Sync Engine] Updated ${freshJobs.length} jobs in IndexedDB.`);
    }
  } catch (err) {
    console.error('[Sync Engine] Failed to pull fresh jobs:', err);
  }
}
