import { defineRailway, github, project, service } from "railway/iac";

export default defineRailway(() => {
  const folio = github("borbalita/folio", { branch: "main", checkSuites: false, rootDirectory: "/backend" });

  const backend = service("backend", {
    source: folio,
    start: "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    healthcheck: "/health",
    replicas: { "ams": 1 },
    domains: ["api.folio.tasnadi-ai.de"],
  });
  const frontend = service("frontend", {
    source: github("borbalita/folio", { branch: "main", checkSuites: false, rootDirectory: "/frontend" }),
    replicas: { "ams": 1 },
    domains: ["folio.tasnadi-ai.de"],
  });
  const emailIngest = service("email-ingest", {
    source: folio,
    // Same root as the API, so it must set its own start command; a cron run has no healthcheck.
    start: "python -m ingest.email --scheduled",
    replicas: { "ams": 1 },
    deploy: { cronSchedule: "*/30 * * * *", restartPolicyType: "NEVER" },
    networking: { privateNetworkEndpoint: "folio" },
  });

  const bankSync = service("bank-sync", {
    source: folio,
    start: "python -m ingest.bank",
    replicas: { "ams": 1 },
    // UTC; three runs stay inside the bank's four unattended reads per account a day.
    deploy: { cronSchedule: "0 4,11,18 * * *", restartPolicyType: "NEVER" },
  });

  return project("brave-energy", {
    variables: { managed: false },
    resources: [backend, frontend, emailIngest, bankSync],
  });
});
