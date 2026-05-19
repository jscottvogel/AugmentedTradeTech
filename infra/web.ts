export function createWeb(db: any, apiRouter: any) {
  // Next.js Frontend Site (PWA)
  const web = new sst.aws.Nextjs("WebSite", {
    path: "apps/web",
    link: [db],
    environment: {
      NEXT_PUBLIC_API_URL: apiRouter.url,
    },
    transform: {
      bucket: {
        tags: {
          Component: "web",
        },
      },
      server: {
        tags: {
          Component: "web",
        },
      },
      imageOptimization: {
        tags: {
          Component: "web",
        },
      },
      distribution: {
        tags: {
          Component: "web",
        },
      },
    },
  });

  return { web };
}
