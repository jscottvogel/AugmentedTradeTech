import { test, expect } from "@playwright/test";

test.describe("Offline Sync & Conflict Resolution E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    page.on("console", msg => {
      console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
    });
    page.on("pageerror", err => {
      console.log(`[BROWSER EXCEPTION] ${err.message}`);
    });

    // Navigate to initialize domain origin
    await page.goto("/login");
    
    // Inject Demo credentials and token into localStorage to bypass AuthGuard
    await page.evaluate(() => {
      localStorage.setItem("accessToken", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfdGVjaF9kZW1vIiwidXNlcl9pZCI6InVzcl90ZWNoX2RlbW8iLCJjb21wYW55X2lkIjoiY29tcF9kZW1vIiwicm9sZSI6InRlY2giLCJlbWFpbCI6InRlY2hAZGVtby5jb20iLCJpc19hY3RpdmUiOnRydWUsImV4cCI6MjA5NDY3NDA1N30.iihlmRmjiC3fgmZm8olye4f3O8G7xfqRxwWVOL9a7yc");
      localStorage.setItem("user", JSON.stringify({
        id: "usr_tech_demo",
        email: "tech@demo.com",
        full_name: "John Technician",
        role: "tech",
        is_active: true,
        company_id: "comp_demo",
        tech_profile: {
          availability_status: "available",
          status_changed_at: new Date().toISOString()
        }
      }));
    });
  });

  test("Verify offline queueing, online flush and conflict resolution", async ({ page, context }) => {
    // Go to single job chat page where we can add a note
    await page.goto("/app/jobs/job_demo_1/ai");
    
    // Wait for chat to load
    await expect(page.locator("h1")).toContainText("Senior Tech AI Mentor");
    
    // Simulate going offline
    await context.setOffline(true);
    await page.waitForTimeout(1000);

    // Verify offline banner shows up
    await expect(page.locator("text=Offline Mode").first()).toBeVisible();

    // Perform mutation offline: click Add to Notes
    const addToNotesBtn = page.locator("button:has-text('Add to Job Notes')");
    await expect(addToNotesBtn).toBeVisible();
    await addToNotesBtn.click();

    await page.waitForTimeout(1000);

    // Intercept /sync/flush to mock a conflict resolution response
    await page.route("**/sync/flush", async (route) => {
      console.log("[PLAYWRIGHT MOCK] Intercepted /sync/flush request");
      const req = route.request();
      const postData = JSON.parse(req.postData() || "{}");
      console.log("[PLAYWRIGHT MOCK] Request postData:", postData);
      
      const ik = postData.items?.[0]?.idempotency_key || "ik_mock_conflict";
      
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          results: [
            {
              idempotency_key: ik,
              status: "conflict",
              server_response: {
                id: "job_demo_1",
                job_number: "JOB-DEMO-001",
                status: "confirmed",
                reported_problem: "Leaking water",
                updated_at: new Date().toISOString()
              }
            }
          ]
        })
      });
    });

    // Go back online
    console.log("[PLAYWRIGHT TEST] Going back online...");
    await context.setOffline(false);
    
    // Let's also dispatch online event manually on the window just in case
    await page.evaluate(() => {
      window.dispatchEvent(new Event('online'));
    });

    // The sync engine triggers background sync, receives conflict, dispatches event,
    // and displays the glassmorphic conflict toast: "Some changes were updated by the server"
    await expect(page.locator("text=Some changes were updated by the server")).toBeVisible({ timeout: 15000 });
  });
});
