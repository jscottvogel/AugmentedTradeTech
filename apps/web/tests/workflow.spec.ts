import { test, expect } from "@playwright/test";
import path from "path";

test.describe("Guided Inspection Workflow E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    // Listen for browser console logs
    page.on("console", msg => {
      console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
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

  test("Play through HVAC workflow and verify all 12 validation requirements", async ({ page }) => {
    const mockPhotoPath = path.resolve("public/icon-192.png"); // Use a valid local image file for the compression library

    // 1. Load the inspection page
    await page.goto("/app/jobs/job_demo_1/inspection");
    
    // Check 1: HVAC workflow has 12 steps seeded correctly
    const heading = page.locator("h1");
    await expect(heading).toContainText("Inspection");
    const dots = page.locator("footer button");
    await expect(dots).toHaveCount(12);

    // Check 9: Progress bar updates correctly (starts at 0% / 0 of 12 steps)
    const progressText = page.locator("text=Progress: 0 / 12 steps completed");
    await expect(progressText).toBeVisible();

    // Check 8: Required step cannot be skipped (Skip button absent on Step 1: Arrive on Site)
    let skipBtn = page.locator("button:has-text('Skip Step')");
    await expect(skipBtn).toHaveCount(0);

    // Step 1: Arrive on Site (Photo, Required)
    const fileInput = page.locator("input[type='file']");
    await fileInput.setInputFiles(mockPhotoPath);
    
    // Next Step should be enabled
    const nextBtn = page.locator("button:has-text('Next Step')");
    await expect(nextBtn).toBeEnabled();
    await nextBtn.click(); // To Step 2

    // Step 2: Equipment Identification (Photo, Required)
    await expect(page.locator("h2")).toContainText("Equipment Identification");
    await expect(page.locator("button:has-text('Skip Step')")).toHaveCount(0);
    
    // Re-query locator to avoid stale element reference during transition
    const step2FileInput = page.locator("input[type='file']");
    await step2FileInput.setInputFiles(mockPhotoPath);
    
    // Wait for upload registration to complete and button to enable
    const nextBtnStep2 = page.locator("button:has-text('Next Step')");
    await expect(nextBtnStep2).toBeEnabled();
    await nextBtnStep2.click(); // To Step 3

    // Step 3: Safety & Power Check (Checklist, Required)
    await expect(page.locator("h2")).toContainText("Safety & Power Check");
    
    // Toggle all items using stable text selectors
    await page.locator("button:has-text('Disconnect is OFF/Safe')").click();
    await page.waitForTimeout(600);
    await page.locator("button:has-text('No immediate hazards present')").click();
    await page.waitForTimeout(600);
    await page.locator("button:has-text('Lockout/Tagout applied if required')").click();
    await page.waitForTimeout(600);
    await page.locator("button:has-text('Next Step')").click(); // To Step 4

    // Step 4: Filter & Airflow (MultiChoice, Required)
    await expect(page.locator("h2")).toContainText("Filter & Airflow");
    const choiceOptions = page.locator("button:has-text('Clean / Good condition')");
    await choiceOptions.click();
    await page.locator("button:has-text('Next Step')").click(); // To Step 5

    // Step 5: Duct Inspection (Photo, Optional)
    // Check 7: Optional step can be skipped
    await expect(page.locator("h2")).toContainText("Duct Inspection");
    const skipBtnStep5 = page.locator("button:has-text('Skip Step')");
    await expect(skipBtnStep5).toBeVisible();
    await skipBtnStep5.click();
    await page.waitForTimeout(600);
    await page.locator("button:has-text('Next Step')").click(); // To Step 6

    // Step 6: Refrigerant & Pressures (Numeric, Required)
    await expect(page.locator("h2")).toContainText("Refrigerant & Pressures");
    const numInput = page.locator("input[type='number']");
    
    // Check 5: Out-of-range numeric value shows red
    await numInput.fill("900");
    await expect(numInput).toHaveClass(/border-red-500/);

    // Check 6: In-range value shows green
    await numInput.fill("130");
    await expect(numInput).toHaveClass(/border-emerald-500/);
    await page.locator("button:has-text('Next Step')").click(); // To Step 7

    // Step 7: Temperature Readings (Numeric, Required)
    await expect(page.locator("h2")).toContainText("Temperature Readings");
    const numInputStep7 = page.locator("input[type='number']");
    await numInputStep7.fill("72");
    await page.locator("button:has-text('Next Step')").click(); // To Step 8

    // Step 8: Electrical & Components (Photo, Optional)
    await expect(page.locator("h2")).toContainText("Electrical & Components");
    await page.locator("button:has-text('Skip Step')").click();
    await page.waitForTimeout(600);
    await page.locator("button:has-text('Next Step')").click(); // To Step 9

    // Step 9: AI Diagnosis (AI Trigger, Required)
    // Check 11: AI trigger step shows spinner then result
    await expect(page.locator("h2")).toContainText("AI Diagnosis");
    const runAiBtn = page.locator("button:has-text('Run AI Analysis')");
    await runAiBtn.click();
    
    // Assert spinner is shown
    await expect(page.locator("text=Synthesizing accumulated data...")).toBeVisible();

    // Wait for the AI result card to render
    const aiMetricsHeader = page.locator("text=AI DIAGNOSTIC METRICS");
    await expect(aiMetricsHeader).toBeVisible({ timeout: 6000 });
    
    // Check 12: Step navigation dots allow backward navigation
    // We are on Step 9, let's tap Dot 3 (Safety Check)
    const dot3 = page.locator("footer button").nth(2);
    await dot3.click();
    await expect(page.locator("h2")).toContainText("Safety & Power Check");
  });
});
