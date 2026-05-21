import { test, expect } from "@playwright/test";
import path from "path";

test("has heading and loads page", async ({ page }) => {
  await page.goto("/");
  
  // Verify heading is present
  const heading = page.locator("h1");
  await expect(heading).toContainText("Augmented Trade Tech");
});

test("diagnose logs", async ({ page }) => {
  page.on("console", msg => console.log("BROWSER CONSOLE:", msg.text()));
  page.on("pageerror", err => console.log("BROWSER ERROR:", err.message));
  page.on("request", req => console.log("REQ:", req.method(), req.url()));
  page.on("response", res => console.log("RES:", res.status(), res.url()));
  
  try {
    await page.goto("/", { timeout: 10000 });
  } catch (e) {
    console.log("Navigation timeout or error:", e);
  }
  await page.waitForTimeout(5000);
  console.log("FINAL URL:", page.url());
  
  const screenshotPath = path.join("C:\\Users\\j_sco\\.gemini\\antigravity\\brain\\ef0a40a8-d1e2-41fd-afc2-3a0a406c7163", "debug_auth_guard.png");
  await page.screenshot({ path: screenshotPath });
  console.log("SCREENSHOT SAVED TO:", screenshotPath);
});
