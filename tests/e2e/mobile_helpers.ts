import { expect, Page, TestInfo } from "@playwright/test";

export async function openMobileSmokePage(
  page: Page,
  testInfo: TestInfo,
  path: string,
): Promise<void> {
  await page.goto(path);
  await expect(page.locator("body")).toBeVisible();
  await expect(page.locator("main")).toBeVisible();
  await expectNavigationForProject(page, testInfo);
  await expectNoHorizontalOverflow(page);
  await expectTappableTarget(page, testInfo);
  await expectNoServerErrorText(page);
}

async function expectNavigationForProject(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  if (testInfo.project.name === "Desktop Chrome") {
    await expect(page.locator(".top-nav")).toBeVisible();
    return;
  }
  await expect(page.locator(".mobile-bottom-nav")).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const hasNoOverflow = await page.evaluate(() => {
    const html = document.documentElement;
    const body = document.body;
    return (
      html.scrollWidth <= html.clientWidth + 1 &&
      body.scrollWidth <= body.clientWidth + 1
    );
  });
  expect(hasNoOverflow).toBeTruthy();
}

async function expectTappableTarget(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  const selector =
    testInfo.project.name === "Desktop Chrome"
      ? "button, .top-nav a, .panel"
      : "button, .mobile-bottom-nav a, .panel, .responsive-table tbody tr";
  const target = page.locator(selector).first();
  await expect(target).toBeVisible();
  const box = await target.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
}

async function expectNoServerErrorText(page: Page): Promise<void> {
  await expect(page.locator("body")).not.toContainText("Server Error (500)");
  await expect(page.locator("body")).not.toContainText("Traceback");
  await expect(page.locator("body")).not.toContainText("DisallowedHost");
}
