import { expect, test } from "@playwright/test";

const sidSession = process.env.ADMIN_E2E_SESSION || "";
const csrfToken = process.env.ADMIN_E2E_CSRF || "e2e-csrf-token";
const cookieOrigin = process.env.ADMIN_E2E_COOKIE_ORIGIN || "";

test.describe("admin panel layout", () => {
  test.skip(!sidSession, "ADMIN_E2E_SESSION is required to run admin E2E tests");

  test.beforeEach(async ({ context, baseURL }) => {
    if (!baseURL) throw new Error("baseURL is required");
    const origins = [...new Set([baseURL, cookieOrigin].filter(Boolean))];
    await context.addCookies(
      origins.flatMap((url) => [
        {
          name: "sid_session",
          value: sidSession,
          url,
          httpOnly: true,
          sameSite: "Lax" as const,
        },
        {
          name: "csrf_token",
          value: csrfToken,
          url,
          httpOnly: false,
          sameSite: "Lax" as const,
        },
      ]),
    );
  });

  for (const path of ["/admin", "/admin/users", "/admin/whitelist", "/admin/conversations"]) {
    test(`desktop layout stays within viewport for ${path}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 1200 });
      await page.goto(path, { waitUntil: "networkidle" });

      await expect(page.locator(".admin-shell")).toBeVisible();
      await expect(page.locator(".admin-sidebar")).toBeVisible();
      await expect(page.locator(".admin-topbar")).toBeVisible();

      const metrics = await page.evaluate(() => ({
        bodyScrollWidth: document.body.scrollWidth,
        bodyClientWidth: document.body.clientWidth,
        shellScrollWidth: document.querySelector<HTMLElement>(".admin-shell")?.scrollWidth ?? 0,
        shellClientWidth: document.querySelector<HTMLElement>(".admin-shell")?.clientWidth ?? 0,
      }));

      expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.bodyClientWidth);
      expect(metrics.shellScrollWidth).toBeLessThanOrEqual(metrics.shellClientWidth);
    });
  }

  test("desktop users page can open add-user modal", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1200 });
    await page.goto("/admin/users", { waitUntil: "networkidle" });

    await page.getByRole("button", { name: "添加用户" }).click();
    await expect(page.locator(".admin-dialog")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "添加用户" })).toBeVisible();
  });

  test("mobile users page dialog and page avoid overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.goto("/admin/users", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "添加用户" }).click();

    const metrics = await page.evaluate(() => {
      const switchRow = document.querySelector<HTMLElement>(".admin-switch-row");
      const topbar = document.querySelector<HTMLElement>(".admin-topbar");
      const formGrid = document.querySelector<HTMLElement>(".admin-form-grid");
      return {
        bodyScrollWidth: document.body.scrollWidth,
        bodyClientWidth: document.body.clientWidth,
        switchDirection: switchRow ? getComputedStyle(switchRow).flexDirection : "",
        topbarDirection: topbar ? getComputedStyle(topbar).flexDirection : "",
        formGridColumns: formGrid ? getComputedStyle(formGrid).gridTemplateColumns : "",
      };
    });

    expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.bodyClientWidth);
    expect(metrics.switchDirection).toBe("column");
    expect(metrics.topbarDirection).toBe("column");
    expect(metrics.formGridColumns.split(" ").length).toBe(1);
  });

  test("mobile conversations page opens playback dialog without overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await page.goto("/admin/conversations", { waitUntil: "networkidle" });

    const firstViewButton = page.getByRole("button", { name: "查看" }).first();
    if (await firstViewButton.isVisible()) {
      await firstViewButton.click();
    }

    const metrics = await page.evaluate(() => {
      const dialogGrid = document.querySelector<HTMLElement>(".admin-conversation-dialog-grid");
      return {
        bodyScrollWidth: document.body.scrollWidth,
        bodyClientWidth: document.body.clientWidth,
        gridColumns: dialogGrid ? getComputedStyle(dialogGrid).gridTemplateColumns : "",
      };
    });

    expect(metrics.bodyScrollWidth).toBeLessThanOrEqual(metrics.bodyClientWidth);
    if (metrics.gridColumns) {
      expect(metrics.gridColumns.split(" ").length).toBe(1);
    }
  });

  test("admin sidebar contains whitelist module", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1200 });
    await page.goto("/admin", { waitUntil: "networkidle" });

    await expect(page.getByRole("link", { name: "白名单管理" })).toBeVisible();
  });
});