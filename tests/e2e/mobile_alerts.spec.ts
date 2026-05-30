import { test } from "@playwright/test";
import { openMobileSmokePage } from "./mobile_helpers";

test("alerts page works on mobile data URL", async ({ page }, testInfo) => {
  await openMobileSmokePage(page, testInfo, "/alerts/");
});
