# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: apps\web\tests\sync.spec.ts >> Offline Sync & Conflict Resolution E2E Tests >> Verify offline queueing, online flush and conflict resolution
- Location: apps\web\tests\sync.spec.ts:33:7

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/login", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | 
  3  | test.describe("Offline Sync & Conflict Resolution E2E Tests", () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     page.on("console", msg => {
  6  |       console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
  7  |     });
  8  |     page.on("pageerror", err => {
  9  |       console.log(`[BROWSER EXCEPTION] ${err.message}`);
  10 |     });
  11 | 
  12 |     // Navigate to initialize domain origin
> 13 |     await page.goto("/login");
     |                ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  14 |     
  15 |     // Inject Demo credentials and token into localStorage to bypass AuthGuard
  16 |     await page.evaluate(() => {
  17 |       localStorage.setItem("accessToken", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfdGVjaF9kZW1vIiwidXNlcl9pZCI6InVzcl90ZWNoX2RlbW8iLCJjb21wYW55X2lkIjoiY29tcF9kZW1vIiwicm9sZSI6InRlY2giLCJlbWFpbCI6InRlY2hAZGVtby5jb20iLCJpc19hY3RpdmUiOnRydWUsImV4cCI6MjA5NDY3NDA1N30.iihlmRmjiC3fgmZm8olye4f3O8G7xfqRxwWVOL9a7yc");
  18 |       localStorage.setItem("user", JSON.stringify({
  19 |         id: "usr_tech_demo",
  20 |         email: "tech@demo.com",
  21 |         full_name: "John Technician",
  22 |         role: "tech",
  23 |         is_active: true,
  24 |         company_id: "comp_demo",
  25 |         tech_profile: {
  26 |           availability_status: "available",
  27 |           status_changed_at: new Date().toISOString()
  28 |         }
  29 |       }));
  30 |     });
  31 |   });
  32 | 
  33 |   test("Verify offline queueing, online flush and conflict resolution", async ({ page, context }) => {
  34 |     // Go to single job chat page where we can add a note
  35 |     await page.goto("/app/jobs/job_demo_1/ai");
  36 |     
  37 |     // Wait for chat to load
  38 |     await expect(page.locator("h1")).toContainText("Senior Tech AI Mentor");
  39 |     
  40 |     // Simulate going offline
  41 |     await context.setOffline(true);
  42 |     await page.waitForTimeout(1000);
  43 | 
  44 |     // Verify offline banner shows up
  45 |     await expect(page.locator("text=Offline Mode").first()).toBeVisible();
  46 | 
  47 |     // Perform mutation offline: click Add to Notes
  48 |     const addToNotesBtn = page.locator("button:has-text('Add to Job Notes')");
  49 |     await expect(addToNotesBtn).toBeVisible();
  50 |     await addToNotesBtn.click();
  51 | 
  52 |     await page.waitForTimeout(1000);
  53 | 
  54 |     // Intercept /sync/flush to mock a conflict resolution response
  55 |     await page.route("**/sync/flush", async (route) => {
  56 |       console.log("[PLAYWRIGHT MOCK] Intercepted /sync/flush request");
  57 |       const req = route.request();
  58 |       const postData = JSON.parse(req.postData() || "{}");
  59 |       console.log("[PLAYWRIGHT MOCK] Request postData:", postData);
  60 |       
  61 |       const ik = postData.items?.[0]?.idempotency_key || "ik_mock_conflict";
  62 |       
  63 |       await route.fulfill({
  64 |         status: 200,
  65 |         contentType: "application/json",
  66 |         body: JSON.stringify({
  67 |           results: [
  68 |             {
  69 |               idempotency_key: ik,
  70 |               status: "conflict",
  71 |               server_response: {
  72 |                 id: "job_demo_1",
  73 |                 job_number: "JOB-DEMO-001",
  74 |                 status: "confirmed",
  75 |                 reported_problem: "Leaking water",
  76 |                 updated_at: new Date().toISOString()
  77 |               }
  78 |             }
  79 |           ]
  80 |         })
  81 |       });
  82 |     });
  83 | 
  84 |     // Go back online
  85 |     console.log("[PLAYWRIGHT TEST] Going back online...");
  86 |     await context.setOffline(false);
  87 |     
  88 |     // Let's also dispatch online event manually on the window just in case
  89 |     await page.evaluate(() => {
  90 |       window.dispatchEvent(new Event('online'));
  91 |     });
  92 | 
  93 |     // The sync engine triggers background sync, receives conflict, dispatches event,
  94 |     // and displays the glassmorphic conflict toast: "Some changes were updated by the server"
  95 |     await expect(page.locator("text=Some changes were updated by the server")).toBeVisible({ timeout: 15000 });
  96 |   });
  97 | });
  98 | 
```