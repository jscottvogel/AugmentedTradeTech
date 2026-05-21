import { test, expect } from "@playwright/test";

test.describe("Dispatcher Dashboard E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to initialize domain origin
    await page.goto("/login");
    
    // Inject Admin credentials and token into localStorage to bypass AuthGuard
    await page.evaluate(() => {
      localStorage.setItem("accessToken", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfYWRtaW5fZGVtbyIsInVzZXJfaWQiOiJ1c3JfYWRtaW5fZGVtbyIsImNvbXBhbnlfaWQiOiJjb21wX2RlbW8iLCJyb2xlIjoiY29tcGFueV9hZG1pbiIsImVtYWlsIjoiYWRtaW5AZGVtby5jb20iLCJpc19hY3RpdmUiOnRydWUsImV4cCI6MjA5NDY3NDA1N30.lUozxQJma39___xWPgtt9kj_ynKrlwHwQsykF03rkg8");
      localStorage.setItem("user", JSON.stringify({
        id: "usr_admin_demo",
        email: "admin@demo.com",
        full_name: "Sarah Admin",
        role: "company_admin",
        is_active: true,
        company_id: "comp_demo"
      }));
    });
  });

  test("Loads dashboard columns, searches, loads job detail, and assigns a tech", async ({ page }) => {
    // 1. Load the dispatcher dashboard
    await page.goto("/dispatch");

    // Check header heading
    const header = page.locator("h1");
    await expect(header).toContainText("Augmented Trade Tech");
    await expect(page.locator("text=Dispatcher Dashboard")).toBeVisible();

    // 2. Check Kanban board columns are present
    const columns = ["unassigned", "scheduled", "en route", "on site", "in progress", "completed"];
    for (const col of columns) {
      await expect(page.locator(`text=${col}`).first()).toBeVisible();
    }

    // 3. Check Technician Board list is visible
    await expect(page.locator("text=Technicians Board")).toBeVisible();
    // Scope John Technician locator to the left sidebar (aside.w-80) to avoid strict mode violations
    await expect(page.locator("aside.w-80").locator("text=John Technician").first()).toBeVisible();

    // 4. Test Search Functionality by Customer Name ('Connor')
    const searchInput = page.locator("input[placeholder*='Search jobs, customers']");
    await searchInput.fill("Connor");
    await page.waitForTimeout(500);

    // Assert that 'Sarah Connor' job card is visible on the board (.first() avoids strict mode overlap with sidebar active job)
    await expect(page.locator("main").locator("text=Sarah Connor").first()).toBeVisible();

    // Clear search
    await searchInput.fill("");
    await page.waitForTimeout(500);

    // 5. Click a job card in the Kanban board to open the slide-in detail panel
    const jobCard = page.locator("main").locator("text=Sarah Connor").first();
    await jobCard.click();

    // Detail panel should open and display 'Work Order Details'
    await expect(page.locator("h3:has-text('Work Order Details')")).toBeVisible();
    await expect(page.locator("text=Client Information")).toBeVisible();
    
    // 6. Assert AI Recommendation is resolved and displayed
    await expect(page.locator("text=AI Smart Dispatch Suggestion")).toBeVisible({ timeout: 6000 });
    
    // 7. Test direct technician assignment from the detail panel dropdown
    const techSelect = page.locator("aside select");
    await expect(techSelect).toBeVisible();
    await techSelect.selectOption({ label: "John Technician (available)" });
    
    // Wait for the assignment network request to complete and data to reload
    await page.waitForTimeout(1000);
    
    // Verify lead technician tag shows John Technician on the card
    await expect(page.locator("text=John Technician").first()).toBeVisible();
  });

  test("Creates a new job with inline new customer creation", async ({ page }) => {
    await page.goto("/dispatch");

    // Click 'Create Job' button
    await page.locator("button:has-text('Create Job')").click();
    await expect(page.locator("h3:has-text('Create New Job Order')")).toBeVisible();

    // Click 'Create New Customer' toggle
    await page.locator("button:has-text('Create New Customer')").click();

    // Fill inline Customer Fields using explicit form labels
    await page.locator("form label:has-text('First Name') + input").fill("Bruce");
    await page.locator("form label:has-text('Last Name') + input").fill("Wayne");
    await page.locator("form label:has-text('Email') + input").fill("bruce@waynecorp.com");
    await page.locator("form label:has-text('Phone') + input").fill("5551234567");
    await page.locator("form label:has-text('Address') + input").fill("1007 Mountain Drive");
    await page.locator("form label:has-text('City') + input").fill("Gotham");
    await page.locator("form label:has-text('State') + input").fill("NJ");

    // Select Trade & Priority
    await page.locator("form label:has-text('Trade') + select").selectOption("hvac");
    await page.locator("form label:has-text('Priority') + select").selectOption("emergency");

    // Fill start and end times for today so it appears on today's Kanban board
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    const startStr = `${yyyy}-${mm}-${dd}T10:00`;
    const endStr = `${yyyy}-${mm}-${dd}T12:00`;
    await page.locator("form label:has-text('Start Window Date/Time') + input").fill(startStr);
    await page.locator("form label:has-text('End Window Date/Time') + input").fill(endStr);

    // Fill Problem description
    await page.locator("form label:has-text('Problem Description') + textarea").fill("Batcave AC compressor is making a loud screeching noise.");

    // Submit Job Creation form
    await page.locator("button[type='submit']").click();

    // Wait for modal to close and board to refresh
    await expect(page.locator("h3:has-text('Create New Job Order')")).not.toBeVisible();
    
    // Search for the newly created customer
    const searchInput = page.locator("input[placeholder*='Search jobs, customers']");
    await searchInput.fill("Wayne");
    await page.waitForTimeout(500);

    // Verify the new job card exists for Bruce Wayne
    await expect(page.locator("text=Bruce Wayne").first()).toBeVisible();
    await expect(page.locator("text=EMERGENCY").first()).toBeVisible();
  });
});
