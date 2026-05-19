export function createQueues() {
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

  return { syncQueue, aiQueue, notificationQueue };
}
