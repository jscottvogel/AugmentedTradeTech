export function createQueues() {
  const syncQueueDLQ = new sst.aws.Queue("SyncQueueDLQ", {
    transform: {
      queue: {
        tags: {
          Component: "queue",
        },
      },
    },
  });

  const syncQueue = new sst.aws.Queue("SyncQueue", {
    transform: {
      queue: {
        tags: {
          Component: "queue",
        },
      },
    },
  });

  const aiQueue = new sst.aws.Queue("AiQueue", {
    transform: {
      queue: {
        tags: {
          Component: "queue",
        },
      },
    },
  });

  const notificationQueue = new sst.aws.Queue("NotificationQueue", {
    transform: {
      queue: {
        tags: {
          Component: "queue",
        },
      },
    },
  });

  return { syncQueue, syncQueueDLQ, aiQueue, notificationQueue };
}
