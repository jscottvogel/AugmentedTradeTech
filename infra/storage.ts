export function createStorage() {
  // S3 bucket for media files configured for CloudFront access
  const bucket = new sst.aws.Bucket("MediaBucket", {
    access: "cloudfront",
    transform: {
      bucket: {
        tags: {
          Component: "storage",
        },
      },
    },
  });

  // CloudFront distribution for media delivery
  const mediaRouter = new sst.aws.Router("MediaRouter", {
    routes: {
      "/*": bucket,
    },
    transform: {
      cdn: {
        tags: {
          Component: "storage",
        },
      },
    },
  });

  return { bucket, mediaRouter };
}
