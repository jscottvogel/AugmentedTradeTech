export function createApi(args: {
  db: any;
  vpc: any;
  mediaBucket: any;
  syncQueue: any;
  aiQueue: any;
  notificationQueue: any;
}) {
  // FastAPI Backend Function running inside the VPC with link to DB, Storage, and Queues
  const apiFunction = new sst.aws.Function("ApiFunction", {
    runtime: "python3.13",
    handler: "apps/api/app/main.handler",
    vpc: args.vpc,
    url: true,
    link: [
      args.db,
      args.mediaBucket,
      args.syncQueue,
      args.aiQueue,
      args.notificationQueue,
    ],
    transform: {
      function: {
        tags: {
          Component: "api",
        },
      },
    },
  });

  // CloudFront distribution serving the API
  const apiRouter = new sst.aws.Router("ApiRouter", {
    routes: {
      "/*": apiFunction.url,
    },
    transform: {
      cdn: {
        tags: {
          Component: "api",
        },
      },
    },
  });

  return { apiFunction, apiRouter };
}
