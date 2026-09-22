import "@testing-library/jest-dom/vitest";

// jsdom has no native top layer. Browser tests verify focus and inert behavior.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

// jsdom has no layout; real resize/placement is exercised by Playwright.
globalThis.ResizeObserver = class implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

beforeEach(() => {
  if (!document.getElementById("shotmill-overlay-root")) {
    const root = document.createElement("div");
    root.id = "shotmill-overlay-root";
    document.body.append(root);
  }
});

afterEach(() => {
  document.getElementById("shotmill-overlay-root")?.replaceChildren();
});
