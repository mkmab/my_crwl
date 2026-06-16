import type { AnalysisResponse, CrawlResponse, DomSnapshot, EmailResponse, JobStage, JobStageId, ResearchJobState } from "../shared/types";

const fallbackApi = "http://127.0.0.1:8000";
const stateKey = "researchJobState";
const defaultEmailTemplate =
  '[their domain] or "quick site note" or "website question"\n\nYour [X page] is missing [specific thing] -- which means [consequence].\n\nFor a [type of business], that usually means [lost revenue / traffic / trust].\n\nI fix this kind of thing for [type of business].\n\nI put together [specific free thing] -- want me to send it over?';

const stageLabels: Record<JobStageId, string> = {
  idle: "Ready",
  collecting: "Collecting visible page context",
  crawling: "Crawling website",
  ai: "Sending research to AI",
  email: "Generating personalized cold email",
  pdf: "Making PDF report",
  complete: "Final process complete",
  error: "Needs attention"
};

const orderedStages: JobStageId[] = ["collecting", "crawling", "ai", "email", "pdf", "complete"];

let jobState: ResearchJobState = {
  tab: { url: "", title: "" },
  apiBaseUrl: fallbackApi,
  emailTemplate: defaultEmailTemplate,
  aiModel: "gemini",
  analysis: null,
  email: null,
  loading: false,
  status: stageLabels.idle,
  error: "",
  stages: makeStages("idle"),
  updatedAt: Date.now()
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.set({ apiBaseUrl: fallbackApi });
  chrome.storage.local.get([stateKey], ({ [stateKey]: stored }) => {
    if (!stored) persistState(jobState);
  });
});

chrome.action.onClicked.addListener((tab) => {
  const openPanel = chrome.sidePanel?.open;
  if (openPanel && tab.windowId !== undefined) {
    openPanel({ windowId: tab.windowId });
  }
});

chrome.storage.local.get([stateKey], ({ [stateKey]: stored }) => {
  if (stored) {
    jobState = { ...jobState, ...stored };
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "GET_ACTIVE_TAB") {
    getActiveTab().then(sendResponse);
    return true;
  }

  if (message?.type === "GET_JOB_STATE") {
    loadState().then(sendResponse);
    return true;
  }

  if (message?.type === "SAVE_SETTINGS") {
    const apiBaseUrl = String(message.apiBaseUrl || fallbackApi);
    const emailTemplate = String(message.emailTemplate || defaultEmailTemplate);
    const aiModel = String(message.aiModel || "gemini");
    chrome.storage.sync.set({ apiBaseUrl });
    updateState({ apiBaseUrl, emailTemplate, aiModel }).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message?.type === "START_ANALYSIS") {
    runAnalysis().then(
      () => sendResponse({ ok: true }),
      (error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Analysis failed" })
    );
    return true;
  }

  if (message?.type === "STOP_ANALYSIS") {
    // attempt to cancel running backend job (use promises to avoid top-level await in listener)
    loadState()
      .then(async (stored) => {
        const apiBaseUrl = normalizeApi(stored.apiBaseUrl || fallbackApi);
        const url = stored.tab?.url;
        if (url) {
          try {
            await postJson(`${apiBaseUrl}/stop`, { url });
          } catch (err) {
            // ignore
          }
        }
        await updateState({ loading: false, status: stageLabels.idle, stages: makeStages("idle") });
        sendResponse({ ok: true });
      })
      .catch((err) => {
        sendResponse({ ok: false, error: err instanceof Error ? err.message : String(err) });
      });
    return true;
  }

  return false;
});

async function runAnalysis() {
  if (jobState.loading) return;

  const tab = await getActiveTab();
  const stored = await loadState();
  const apiBaseUrl = normalizeApi(stored.apiBaseUrl || fallbackApi);
  const emailTemplate = stored.emailTemplate || defaultEmailTemplate;

  await updateState({
    tab,
    apiBaseUrl,
    emailTemplate,
    analysis: null,
    email: null,
    loading: true,
    error: "",
    status: stageLabels.collecting,
    stages: makeStages("collecting")
  });

  try {
    const dom = await collectDom(tab.tabId);
    await setStage("crawling");
    const crawl = await postJson<CrawlResponse>(`${apiBaseUrl}/crawl`, {
      url: tab.url,
      dom_snapshot: dom ? JSON.stringify(dom) : undefined,
      ai_model: stored.aiModel || "gemini"
    });

    await setStage("ai", "Crawling complete. Sending website research to AI.");
    const research = await postJson<AnalysisResponse>(`${apiBaseUrl}/research-from-crawl`, {
      crawl,
      dom_snapshot: dom ? JSON.stringify(dom) : undefined,
      ai_model: stored.aiModel || "gemini"
    });
    await updateState({ analysis: research });

    await setStage("email");
    const email = await postJson<EmailResponse>(`${apiBaseUrl}/generate-email`, {
      analysis: research,
      template: emailTemplate,
      ai_model: stored.aiModel || "gemini"
    });
    await updateState({ email });

    await setStage("pdf");
    const pdf = await postJson<{ pdf_url: string }>(`${apiBaseUrl}/generate-pdf`, { analysis: { ...research, cold_email: email }, ai_model: stored.aiModel || "gemini" });
    const analysisWithPdf = { ...research, pdf_url: pdf.pdf_url };

    await updateState({
      analysis: analysisWithPdf,
      loading: false,
      status: stageLabels.complete,
      stages: makeStages("complete"),
      updatedAt: Date.now()
    });
  } catch (error) {
    await updateState({
      loading: false,
      error: error instanceof Error ? error.message : "Analysis failed",
      status: "Check backend connection or AI configuration",
      stages: makeStages("error")
    });
    throw error;
  }
}

async function collectDom(tabId?: number): Promise<DomSnapshot | null> {
  if (!tabId) return null;
  try {
    return (await chrome.tabs.sendMessage(tabId, { type: "COLLECT_DOM" })) as DomSnapshot;
  } catch {
    return null;
  }
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  return { url: tab?.url ?? "", title: tab?.title ?? "", tabId: tab?.id };
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Backend returned ${response.status}`);
  }
  return (await response.json()) as T;
}

async function setStage(stage: JobStageId, status = stageLabels[stage]) {
  await updateState({ status, stages: makeStages(stage) });
}

async function loadState(): Promise<ResearchJobState> {
  const { [stateKey]: stored } = await chrome.storage.local.get([stateKey]);
  if (stored) {
    jobState = { ...jobState, ...stored };
  }
  return jobState;
}

async function updateState(patch: Partial<ResearchJobState>) {
  jobState = { ...jobState, ...patch, updatedAt: Date.now() };
  await persistState(jobState);
  chrome.runtime.sendMessage({ type: "JOB_STATE_UPDATED", state: jobState }).catch(() => undefined);
}

async function persistState(state: ResearchJobState) {
  await chrome.storage.local.set({ [stateKey]: state });
}

function makeStages(active: JobStageId): JobStage[] {
  return orderedStages.map((id) => {
    if (active === "idle") return { id, label: stageLabels[id], state: "pending" };
    if (active === "error") return { id, label: stageLabels[id], state: id === "complete" ? "pending" : "error" };
    const activeIndex = orderedStages.indexOf(active);
    const index = orderedStages.indexOf(id);
    return {
      id,
      label: stageLabels[id],
      state: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending"
    };
  });
}

function normalizeApi(value: string) {
  return value.replace(/\/$/, "");
}
