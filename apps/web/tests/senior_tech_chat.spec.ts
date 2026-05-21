import { test, expect } from "@playwright/test";

test.describe("Senior Tech AI Chat Interface E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
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

  test("Verify chat UI components, sending messages, and suggested chips", async ({ page }) => {
    // 1. Go to AI Chat route
    await page.goto("/app/jobs/job_demo_1/ai");
    
    // 2. Verify title and header are present
    const header = page.locator("h1");
    await expect(header).toContainText("Senior Tech AI Mentor");
    
    // 3. Verify initial mentor message
    await expect(page.locator("text=I'm your Senior Tech assistant. Ask me anything")).toBeVisible();

    // 4. Test typing and sending a message
    const input = page.locator("input[type='text']");
    await expect(input).toBeVisible();
    await input.fill("What is the typical subcooling for Carrier condenser?");
    
    const sendBtn = page.locator("footer button").nth(1); // second button is send
    await expect(sendBtn).toBeEnabled();
    await sendBtn.click();

    // 5. Verify user message appears in list
    await expect(page.locator("text=What is the typical subcooling for Carrier condenser?")).toBeVisible();
    
    // 6. Verify streaming indicator shows up and then disappears (as mock generates response)
    await page.waitForTimeout(1000);
    
    // 7. Verify mock AI reply contains senior tech responses
    await expect(page.locator("text=Hey there, senior tech here!")).toBeVisible();

    // 8. Test suggested question chip
    const chip = page.locator("button:has-text('What are the likely causes?')");
    await expect(chip).toBeVisible();
    await chip.click();
    
    // 9. Verify chip text was sent
    await expect(page.locator("text=What are the likely causes?")).toBeVisible();
  });

  test("Verify notes integration and offline state", async ({ page, context }) => {
    // Navigate to Chat page
    await page.goto("/app/jobs/job_demo_1/ai");
    
    // Check that notes addition button is visible on assistant messages
    const addToNotesBtn = page.locator("button:has-text('Add to Job Notes')");
    await expect(addToNotesBtn).toBeVisible();
    
    // Click Add to Notes
    await addToNotesBtn.click();
    
    // Toast notification should appear
    await expect(page.locator("text=Added to Job Notes successfully!")).toBeVisible();

    // Simulate going offline
    await context.setOffline(true);
    await page.waitForTimeout(500);

    // Verify offline warning banner and status badge
    await expect(page.locator("text=Offline Mode").first()).toBeVisible();
    await expect(page.locator("text=AI chat requires connection.")).toBeVisible();

    // Reconnect to restore state
    await context.setOffline(false);
    await page.waitForTimeout(500);
    await expect(page.locator("text=Mentor Online")).toBeVisible();
  });
});
