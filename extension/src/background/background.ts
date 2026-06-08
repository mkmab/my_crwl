chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.set({ apiBaseUrl: "http://127.0.0.1:8000" });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "GET_ACTIVE_TAB") {
    return false;
  }

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    sendResponse({ url: tab?.url ?? "", title: tab?.title ?? "", tabId: tab?.id });
  });
  return true;
});
