export function createDatabase() {
  // AWS VPC for isolating database and backend resources
  const vpc = new sst.aws.Vpc("Vpc", { bastion: true, nat: "ec2" });

  // Aurora Serverless v2 Postgres 15 database
  const db = new sst.aws.Aurora("Database", {
    engine: "postgres",
    version: "15.7",
    vpc,
    scaling: {
      min: $app.stage === "dev" ? "0 ACU" : "2 ACU",
      max: $app.stage === "dev" ? "4 ACU" : "64 ACU",
    },
    transform: {
      cluster: {
        tags: {
          Component: "database",
        },
      },
    },
  });

  return { vpc, db };
}
