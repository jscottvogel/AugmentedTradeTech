/// <reference path="./.sst/platform/config.d.ts" />
import { createDatabase } from "./infra/database";
import { createStorage } from "./infra/storage";
import { createQueues } from "./infra/queue";
import { createApi } from "./infra/api";
import { createWeb } from "./infra/web";

export default $config({
  app(input) {
    return {
      name: "augmentedtradetech",
      removal: input?.stage === "production" ? "retain" : "remove",
      home: "aws",
      providers: {
        aws: {
          defaultTags: {
            tags: {
              Environment: input.stage,
              Feature: "core",
              CostCenter: "platform",
              ManagedBy: "sst",
            },
          },
        },
      },
    };
  },
  async run() {
    // 1. Database Stack (VPC & Aurora Serverless v2 PostgreSQL 15)
    const { vpc, db } = createDatabase();

    // 2. Storage Stack (Media Bucket & CloudFront Router)
    const { bucket, mediaRouter } = createStorage();

    // 3. Queue Stack (SQS Queues: sync, ai, notification)
    const { syncQueue, aiQueue, notificationQueue } = createQueues();

    // 4. API Stack (FastAPI Lambda Function URL behind CloudFront Router)
    const { apiFunction, apiRouter } = createApi({
      db,
      vpc,
      mediaBucket: bucket,
      syncQueue,
      aiQueue,
      notificationQueue,
    });

    // 5. Web Stack (Next.js SSR Web Site)
    const { web } = createWeb(db, apiRouter);

    // 6. Background Heartbeat Timeout Cron Job (Runs every 5 minutes)
    new sst.aws.Cron("HeartbeatCron", {
      schedule: "rate(5 minutes)",
      job: {
        handler: "apps/api/app/cron/heartbeat.handler",
        link: [db],
        vpc,
      },
    });

    return {
      databaseHost: db.host,
      mediaUrl: mediaRouter.url,
      apiUrl: apiRouter.url,
      webUrl: web.url,
    };
  },
});
