import {
  getCachedJob,
  cacheJob,
  cacheJobs,
  getAllCachedJobs,
  enqueueMutation,
  getCachedAiResponse,
  cacheAiResponse
} from './indexedDB';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Helper to determine if we are offline
export function isDeviceOnline(): boolean {
  if (typeof window !== "undefined") {
    return navigator.onLine;
  }
  return true;
}

// Local mock updater that mimics backend changes on the cached IndexedDB data
async function applyOfflineMutationLocal(
  entity_type: 'job' | 'note' | 'part' | 'tech',
  entity_id: string,
  operation: 'status' | 'create' | 'delete' | 'availability' | 'workflow',
  payload: any
): Promise<any> {
  console.log(`[Offline API] Applying offline mutation locally: ${entity_type}.${operation} on ${entity_id}`);
  
  if (entity_type === 'job' && operation === 'status') {
    const job = await getCachedJob(entity_id);
    if (job) {
      job.status = payload.status;
      if (!job.status_history) job.status_history = [];
      job.status_history.unshift({
        id: `local_sh_${Date.now()}`,
        from_status: job.status,
        to_status: payload.status,
        changed_by: 'tech',
        changed_by_name: 'You (Offline)',
        changed_at: new Date().toISOString(),
        note: payload.note || null
      });
      await cacheJob(job);
      return job;
    }
  } else if (entity_type === 'note' && operation === 'create') {
    const job = await getCachedJob(entity_id);
    if (job) {
      const newNote = {
        id: `local_n_${Date.now()}`,
        author_id: 'tech',
        note_type: payload.note_type || 'general',
        body: payload.body,
        is_internal: true,
        created_at: new Date().toISOString()
      };
      if (!job.notes) job.notes = [];
      job.notes.unshift(newNote);
      await cacheJob(job);
      return job;
    }
  } else if (entity_type === 'part' && operation === 'create') {
    const job = await getCachedJob(entity_id);
    if (job) {
      const newPart = {
        id: `local_p_${Date.now()}`,
        name: payload.name,
        quantity: payload.quantity,
        price_cents: payload.price_cents,
        serial_number: payload.serial_number || null
      };
      if (!job.parts) job.parts = [];
      job.parts.push(newPart);
      await cacheJob(job);
      return job;
    }
  } else if (entity_type === 'part' && operation === 'delete') {
    const job = await getCachedJob(entity_id);
    const partId = payload.partId;
    if (job) {
      if (job.parts) {
        job.parts = job.parts.filter((p: any) => p.id !== partId);
      }
      await cacheJob(job);
      return job;
    }
  } else if (entity_type === 'tech' && operation === 'availability') {
    // Return a structured availability response
    return {
      success: true,
      tech_profile: {
        availability_status: payload.status,
        status_changed_at: new Date().toISOString()
      }
    };
  } else if (entity_type === 'job' && operation === 'workflow') {
    const job = await getCachedJob(entity_id);
    if (job) {
      if (!job.inspection_data) {
        job.inspection_data = {};
      }
      const { step, inputs, skipped, idempotency_key } = payload;
      job.inspection_data[step] = {
        inputs,
        skipped,
        idempotency_key,
        completed_at: new Date().toISOString()
      };
      await cacheJob(job);
      return {
        status: "success",
        step_data: job.inspection_data[step]
      };
    }
  }
  return null;
}

export async function offlineSafeFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const method = (options.method || 'GET').toUpperCase();
  const urlObj = new URL(url, typeof window !== "undefined" ? window.location.origin : undefined);
  const pathname = urlObj.pathname;

  // --- GET REQUESTS FLOW ---
  if (method === 'GET') {
    // If online, attempt actual fetch
    if (isDeviceOnline()) {
      try {
        const res = await fetch(url, options);
        if (res.ok) {
          const resClone = res.clone();
          const data = await resClone.json();

          // Intercept and cache retrieved data in IndexedDB
          if (pathname.includes('/me/jobs/today') || pathname.includes('/me/jobs/upcoming')) {
            if (Array.isArray(data)) {
              await cacheJobs(data);
            }
          } else if (pathname.startsWith('/jobs/') && !pathname.endsWith('/workflow') && !pathname.endsWith('/notes') && !pathname.endsWith('/parts') && !pathname.endsWith('/photos')) {
            // It's a single job details load
            // Path looks like /jobs/uuid
            const parts = pathname.split('/');
            const jobId = parts[parts.length - 1];
            if (jobId && data && data.id === jobId) {
              await cacheJob(data);
            }
          } else if (pathname.startsWith('/jobs/') && pathname.endsWith('/workflow')) {
            // It's a /jobs/{id}/workflow load
            const parts = pathname.split('/');
            const jobId = parts[2];
            if (jobId && data) {
              await cacheJob({ id: `workflow_${jobId}`, ...data });
            }
          } else if (pathname.includes('/ai/') || (pathname.includes('/workflow/') && pathname.includes('/ai'))) {
            // Cache AI response
            const parts = pathname.split('/');
            const jobId = parts[2]; // /jobs/[id]/workflow/...
            if (jobId) {
              await cacheAiResponse(jobId, data);
            }
          }
        }
        return res;
      } catch (err) {
        console.warn("[Offline API] Fetch failed, falling back to IndexedDB cache:", err);
      }
    }

    // Offline / Network Error: fall back to IndexedDB cache
    console.log(`[Offline API] Offline or fetch failed. Retrieving GET request from IndexedDB: ${pathname}`);
    
    if (pathname.includes('/me/jobs/today')) {
      const allJobs = await getAllCachedJobs();
      // Filter out jobs that are today
      const today = new Date().toDateString();
      const todayJobs = allJobs.filter(j => {
        if (!j.scheduled_start) return false;
        return new Date(j.scheduled_start).toDateString() === today;
      });
      return new Response(JSON.stringify(todayJobs), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    } else if (pathname.includes('/me/jobs/upcoming')) {
      const allJobs = await getAllCachedJobs();
      const today = new Date().toDateString();
      const upcomingJobs = allJobs.filter(j => {
        if (!j.scheduled_start) return false;
        return new Date(j.scheduled_start).toDateString() !== today;
      });
      return new Response(JSON.stringify(upcomingJobs), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    } else if (pathname.includes('/me/stats/today')) {
      // Return a basic offline stats structure
      const allJobs = await getAllCachedJobs();
      const today = new Date().toDateString();
      const completedToday = allJobs.filter(j => 
        j.status === 'completed' && j.scheduled_start && new Date(j.scheduled_start).toDateString() === today
      ).length;
      return new Response(JSON.stringify({
        jobs_completed: completedToday,
        earnings_today: null,
        earnings_enabled: false,
        offline: true
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    } else if (pathname.startsWith('/jobs/') && !pathname.endsWith('/workflow') && !pathname.endsWith('/notes') && !pathname.endsWith('/parts') && !pathname.endsWith('/photos')) {
      const parts = pathname.split('/');
      const jobId = parts[parts.length - 1];
      const job = await getCachedJob(jobId);
      if (job) {
        return new Response(JSON.stringify(job), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return new Response(JSON.stringify({ error: "Offline: Job details not cached." }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    } else if (pathname.startsWith('/jobs/') && pathname.endsWith('/workflow')) {
      const parts = pathname.split('/');
      const jobId = parts[2];
      const cachedWf = await getCachedJob(`workflow_${jobId}`);
      if (cachedWf) {
        const cachedJob = await getCachedJob(jobId);
        const localProgress = cachedJob?.inspection_data || {};
        const mergedProgress = { ...cachedWf.progress, ...localProgress };
        return new Response(JSON.stringify({
          steps: cachedWf.steps,
          progress: mergedProgress
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return new Response(JSON.stringify({ error: "Offline: Workflow configuration not cached." }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    } else if (pathname.includes('/ai/') || (pathname.includes('/workflow/') && pathname.includes('/ai'))) {
      const parts = pathname.split('/');
      const jobId = parts[2];
      const cachedAi = await getCachedAiResponse(jobId);
      if (cachedAi) {
        return new Response(JSON.stringify(cachedAi), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return new Response(JSON.stringify({ error: "Offline: AI diagnostics not cached." }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Default basic fallback
    return new Response(JSON.stringify({ error: "Device is offline. Check connection." }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // --- MUTATION REQUESTS FLOW (POST, PUT, DELETE) ---
  
  // Helper to parse JSON body from request
  let bodyJson: any = {};
  if (options.body && typeof options.body === 'string') {
    try {
      bodyJson = JSON.parse(options.body);
    } catch (_) {}
  }

  const isOnline = isDeviceOnline();

  // If online, perform mutation fetch
  if (isOnline) {
    try {
      const res = await fetch(url, options);
      // Cache the updated job details on successful mutations to ensure client cache matches the server
      if (res.ok) {
        const resClone = res.clone();
        try {
          const data = await resClone.json();
          // If the return object is a Job, save it
          if (data && data.id && typeof data.job_number === 'string') {
            await cacheJob(data);
          }
        } catch (_) {}
      }
      return res;
    } catch (err) {
      console.warn("[Offline API] Mutation fetch failed due to network error, queueing offline:", err);
    }
  }

  // Offline / Mutation failed: Queue the mutation in IndexedDB sync_queue
  console.log(`[Offline API] Offline mutation detected. Enqueueing in sync_queue: ${pathname}`);

  let entity_type: 'job' | 'note' | 'part' | 'tech' = 'job';
  let entity_id = '';
  let operation: 'status' | 'create' | 'delete' | 'availability' | 'workflow' = 'status';
  let payload = bodyJson;

  // Parse path to resolve entity_type, entity_id, operation
  if (pathname.includes('/me/availability')) {
    entity_type = 'tech';
    entity_id = 'me';
    operation = 'availability';
  } else if (pathname.includes('/status')) {
    // /jobs/{job_id}/status
    const parts = pathname.split('/');
    entity_type = 'job';
    entity_id = parts[2];
    operation = 'status';
  } else if (pathname.endsWith('/notes')) {
    // /jobs/{job_id}/notes
    const parts = pathname.split('/');
    entity_type = 'note';
    entity_id = parts[2];
    operation = 'create';
  } else if (pathname.endsWith('/parts')) {
    // /jobs/{job_id}/parts
    const parts = pathname.split('/');
    entity_type = 'part';
    entity_id = parts[2];
    operation = 'create';
  } else if (pathname.includes('/parts/')) {
    // /jobs/{job_id}/parts/{part_id} (DELETE)
    const parts = pathname.split('/');
    entity_type = 'part';
    entity_id = parts[2];
    operation = 'delete';
    payload = { partId: parts[4] };
  } else if (pathname.includes('/workflow/') && !pathname.endsWith('/ai')) {
    // /jobs/{job_id}/workflow/{step_key}
    const parts = pathname.split('/');
    entity_type = 'job';
    entity_id = parts[2];
    operation = 'workflow';
    payload = {
      step: parts[4],
      inputs: bodyJson.inputs,
      skipped: bodyJson.skipped,
      idempotency_key: bodyJson.idempotency_key
    };
  }

  const idempotency_key = bodyJson.idempotency_key || `mut_ik_${entity_type}_${operation}_${Date.now()}`;
  
  // Attach last_known_updated_at from cached Job entity for conflict detection on server
  let finalPayload = { ...payload };
  if (entity_type === 'job' || entity_type === 'note' || entity_type === 'part') {
    const job = await getCachedJob(entity_id);
    if (job && job.updated_at) {
      finalPayload.last_known_updated_at = job.updated_at;
    }
  }

  // Enqueue in IndexedDB
  await enqueueMutation({
    entity_type,
    entity_id,
    operation,
    payload: finalPayload,
    client_timestamp: Date.now(),
    idempotency_key
  });

  // Apply to local DB cache for immediate UI feedback
  const localUpdatedData = await applyOfflineMutationLocal(entity_type, entity_id, operation, payload);

  return new Response(JSON.stringify(localUpdatedData || { success: true, queued: true }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' }
  });
}
