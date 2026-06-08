import type { DomSnapshot } from "../shared/types";

function text(selector: string): string[] {
  return Array.from(document.querySelectorAll(selector))
    .map((node) => node.textContent?.replace(/\s+/g, " ").trim() ?? "")
    .filter(Boolean)
    .slice(0, 40);
}

function snapshot(): DomSnapshot {
  const description = document.querySelector<HTMLMetaElement>("meta[name='description']")?.content ?? "";
  const links = Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]"))
    .map((link) => ({ text: link.textContent?.replace(/\s+/g, " ").trim() ?? "", href: link.href }))
    .filter((link) => link.text && link.href)
    .slice(0, 80);

  return {
    title: document.title,
    url: location.href,
    description,
    headings: text("h1,h2,h3"),
    visibleText: document.body.innerText.replace(/\s+/g, " ").trim().slice(0, 12000),
    links
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "COLLECT_DOM") {
    sendResponse(snapshot());
  }
  return true;
});
