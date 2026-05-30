import { test } from "@playwright/test";
import { openMobileSmokePage } from "./mobile_helpers";

test("digest page works on mobile data URL", async ({ page }, testInfo) => {
  await openMobileSmokePage(page, testInfo, "/digest/");
});
