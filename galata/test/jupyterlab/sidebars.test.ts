// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { expect, galata, test } from '@jupyterlab/galata';

import { Locator } from '@playwright/test';

import * as path from 'path';

const sidebarIds: galata.SidebarTabId[] = [
  'filebrowser',
  'jp-property-inspector',
  'jp-running-sessions',
  'table-of-contents',
  'extensionmanager.main-view'
];

test.use({
  mockState: true
});

const testFileName = 'simple.md';
const testNotebook = 'simple_notebook.ipynb';
const testFolderName = 'test-folder';

const sidebarWidths = {
  small: 226,
  medium: 308,
  large: 371
};

/**
 * Add provided text as label on first tab in given tabbar.
 * By default we only have icons, but we should test for the
 * styling of labels which are used downstream (e.g. sidecar).
 */
async function mockLabelOnFirstTab(tabbar: Locator, text: string) {
  await tabbar
    .locator('.lm-TabBar-tabLabel')
    .first()
    .evaluate((node: HTMLElement, text: string) => {
      node.innerText = text;
    }, text);
}

test.use({
  tmpPath: 'test-sidebars'
});

test.describe('Sidebars', () => {
  test.beforeAll(async ({ request, tmpPath }) => {
    const contents = galata.newContentsHelper(request);

    // Create some dummy content
    await contents.uploadFile(
      path.resolve(__dirname, `./notebooks/${testNotebook}`),
      `${tmpPath}/${testNotebook}`
    );
    await contents.uploadFile(
      path.resolve(__dirname, `./notebooks/${testFileName}`),
      `${tmpPath}/${testFileName}`
    );
    // Create a dummy folder
    await contents.createDirectory(`${tmpPath}/${testFolderName}`);
  });

  test.afterAll(async ({ request, tmpPath }) => {
    // Clean up the test files
    const contents = galata.newContentsHelper(request);
    await contents.deleteDirectory(tmpPath);
  });

  sidebarIds.forEach(sidebarId => {
    test(`Open Sidebar tab ${sidebarId}`, async ({ page }) => {
      await page.sidebar.openTab(sidebarId);
      expect(await page.sidebar.isTabOpen(sidebarId)).toEqual(true);

      const imageName = `opened-sidebar-${sidebarId.replace('.', '-')}.png`;
      const position = await page.sidebar.getTabPosition(sidebarId);
      const sidebar = page.sidebar.getContentPanelLocator(
        position ?? undefined
      );
      expect(await sidebar.screenshot()).toMatchSnapshot(
        imageName.toLowerCase()
      );
    });
  });

  // Additional test cases for resized widths of the file browser
  for (const [sizeName, size] of Object.entries(sidebarWidths)) {
    test(`Open Sidebar tab filebrowser ${sizeName}`, async ({ page }) => {
      await page.sidebar.openTab('filebrowser');
      // Resize the sidebar to the desired width.
      await page.sidebar.setWidth(size, 'left');
      const imageName = `opened-sidebar-filebrowser-${sizeName}.png`;
      const position = await page.sidebar.getTabPosition('filebrowser');
      const sidebar = page.sidebar.getContentPanelLocator(
        position ?? undefined
      );
      expect(await sidebar.screenshot()).toMatchSnapshot(
        imageName.toLowerCase()
      );
    });
  }

  test('File Browser has no unused rules', async ({ page }) => {
    await page.sidebar.openTab('filebrowser');
    const clickMenuItem = async (command): Promise<void> => {
      const contextmenu = await page.menu.openContextMenuLocator(
        '.jp-DirListing-headerItem'
      );
      const item = await page.menu.getMenuItemLocatorInMenu(
        contextmenu,
        command
      );
      await item?.click();
    };
    await clickMenuItem('Show File Checkboxes');
    await clickMenuItem('Show File Size Column');

    await page.notebook.createNew('notebook.ipynb');

    const unusedRules = await page.style.findUnusedStyleRules({
      fragments: ['jp-DirListing', 'jp-FileBrowser'],
      exclude: [
        // active during renaming
        'jp-DirListing-editor',
        // hidden files
        '[data-is-dot]',
        // filtering results
        '.jp-DirListing-content mark',
        // only added after resizing
        'jp-DirListing-narrow',
        // used in "open file" dialog containing a file browser
        '.jp-Open-Dialog'
      ]
    });
    expect(unusedRules.length).toEqual(0);
  });

  test('Left light tabbar (with text)', async ({ page }) => {
    await page.theme.setLightTheme();
    const imageName = 'left-light-tabbar-with-text.png';
    const tabbar = page.sidebar.getTabBarLocator();
    await mockLabelOnFirstTab(tabbar, 'File Browser');
    expect(await tabbar.screenshot()).toMatchSnapshot(imageName.toLowerCase());
  });

  test('Right dark tabbar (with text)', async ({ page }) => {
    await page.theme.setDarkTheme();
    const imageName = 'right-dark-tabbar-with-text.png';
    const tabbar = page.sidebar.getTabBarLocator('right');
    await mockLabelOnFirstTab(tabbar, 'Property Inspector');
    expect(await tabbar.screenshot()).toMatchSnapshot(imageName.toLowerCase());
  });

  test('Move File Browser to right', async ({ page }) => {
    await page.sidebar.moveTabToRight('filebrowser');
    expect(await page.sidebar.getTabPosition('filebrowser')).toBe('right');
  });

  test('Open File Browser on right', async ({ page }) => {
    await page.sidebar.moveTabToRight('filebrowser');
    await page.sidebar.openTab('filebrowser');
    expect(await page.sidebar.isTabOpen('filebrowser')).toEqual(true);
  });

  test('Open Sidebar on right', async ({ page }) => {
    await page.sidebar.open('right');
    expect(await page.sidebar.isOpen('right')).toEqual(true);
  });

  test('Close Sidebar on right', async ({ page }) => {
    await page.sidebar.open('right');
    await page.menu.clickMenuItem('View>Appearance>Show Right Sidebar');
    expect(await page.sidebar.isOpen('right')).toEqual(false);
  });

  test('Capture File Browser on right', async ({ page }) => {
    await page.sidebar.moveTabToRight('filebrowser');
    await page.sidebar.openTab('filebrowser');

    let imageName = 'filebrowser-right.png';
    expect(await page.screenshot()).toMatchSnapshot(imageName);
  });

  test('Move Debugger to left', async ({ page }) => {
    await page.sidebar.moveTabToLeft('jp-debugger-sidebar');
    expect(await page.sidebar.getTabPosition('jp-debugger-sidebar')).toEqual(
      'left'
    );
  });

  test('Check Running Session button on sidebar has correct aria label and role', async ({
    page
  }) => {
    await page.sidebar.open('left');
    const runningSessionsWidget = page.locator('#jp-running-sessions');
    const runningSessionsElementAriaLabel =
      await runningSessionsWidget.getAttribute('aria-label');
    const runningSessionsElementRole =
      await runningSessionsWidget.getAttribute('role');
    expect(runningSessionsElementAriaLabel).toEqual('Running Sessions section');
    expect(runningSessionsElementRole).toEqual('region');
  });

  test('Check Extension Manager button on sidebar has correct aria label and role', async ({
    page
  }) => {
    await page.sidebar.open('left');
    const extensionManagerWidget = page.locator(
      '#extensionmanager\\.main-view'
    );
    const extensionManagerElementAriaLabel =
      await extensionManagerWidget.getAttribute('aria-label');
    const extensionManagerElementRole =
      await extensionManagerWidget.getAttribute('role');
    expect(extensionManagerElementAriaLabel).toEqual(
      'Extension Manager section'
    );
    expect(extensionManagerElementRole).toEqual('region');
  });

  test('Check File Browser button on sidebar has correct aria label and role', async ({
    page
  }) => {
    await page.sidebar.open('left');
    const fileBrowserWidget = page.locator('#filebrowser');
    const fileBrowserElementAriaLabel =
      await fileBrowserWidget.getAttribute('aria-label');
    const fileBrowserElementRole = await fileBrowserWidget.getAttribute('role');
    expect(fileBrowserElementAriaLabel).toEqual('File Browser Section');
    expect(fileBrowserElementRole).toEqual('region');
  });

  test('Check Debugger button on sidebar has correct aria label and role', async ({
    page
  }) => {
    await page.sidebar.open('right');
    const debuggerWidget = page.locator('#jp-debugger-sidebar');
    const debuggerElementAriaLabel =
      await debuggerWidget.getAttribute('aria-label');
    const debuggerElementRole = await debuggerWidget.getAttribute('role');
    expect(debuggerElementAriaLabel).toEqual('Debugger section');
    expect(debuggerElementRole).toEqual('region');
  });

  test('Check Table of Contents button on sidebar has correct aria label and role', async ({
    page
  }) => {
    await page.sidebar.open('left');
    const tableOfContentsWidget = page.locator('#table-of-contents');
    const tableOfContentsElementAriaLabel =
      await tableOfContentsWidget.getAttribute('aria-label');
    const tableOfContentsElementRole =
      await tableOfContentsWidget.getAttribute('role');
    expect(tableOfContentsElementAriaLabel).toEqual(
      'Table of Contents section'
    );
    expect(tableOfContentsElementRole).toEqual('region');
  });
});
