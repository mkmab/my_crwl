import React from "react";
import ReactDOM from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Download,
  Globe2,
  Loader2,
  Mail,
  Radar,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type {
  AnalysisResponse,
  JobStage,
  ResearchJobState,
} from "../shared/types";
import {
  composeTemplate,
  customSignatureId,
  customTemplateId,
  defaultEmailSignature,
  defaultEmailTemplate,
  emailTemplates,
  signatureTemplates,
} from "../shared/emailTemplates";
import "./styles.css";

const fallbackApi = "http://127.0.0.1:8000";

const emptyState: ResearchJobState = {
  tab: { url: "", title: "" },
  apiBaseUrl: fallbackApi,
  emailTemplate: defaultEmailTemplate,
  emailSignature: defaultEmailSignature,
  selectedEmailTemplateId: customTemplateId,
  selectedSignatureTemplateId: "simple",
  aiModel: "auto",
  analysis: null,
  email: null,
  loading: false,
  status: "Ready",
  error: "",
  stages: [],
  updatedAt: Date.now(),
};

function App() {
  const [state, setState] = React.useState<ResearchJobState>(emptyState);
  const [copied, setCopied] = React.useState(false);
  const [copiedOwner, setCopiedOwner] = React.useState(false);

  React.useEffect(() => {
    chrome.runtime.sendMessage(
      { type: "GET_JOB_STATE" },
      (response: ResearchJobState) => {
        if (response) setState(response);
      },
    );
    chrome.runtime.sendMessage({ type: "GET_ACTIVE_TAB" }, (tab) => {
      if (tab) setState((current) => ({ ...current, tab }));
    });
    const listener = (message: { type?: string; state?: ResearchJobState }) => {
      if (message?.type === "JOB_STATE_UPDATED" && message.state)
        setState(message.state);
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  function saveSettings(
    next: Partial<
      Pick<ResearchJobState, "apiBaseUrl" | "emailTemplate" | "emailSignature" | "selectedEmailTemplateId" | "selectedSignatureTemplateId" | "aiModel">
    >,
  ) {
    setState((prev) => {
      const updated = { ...prev, ...next } as ResearchJobState;
      chrome.runtime.sendMessage({
        type: "SAVE_SETTINGS",
        apiBaseUrl: updated.apiBaseUrl,
        emailTemplate: updated.emailTemplate,
        emailSignature: updated.emailSignature,
        selectedEmailTemplateId: updated.selectedEmailTemplateId,
        selectedSignatureTemplateId: updated.selectedSignatureTemplateId,
        aiModel: (updated as any).aiModel || "auto",
      });
      return updated;
    });
  }

  function selectEmailTemplate(templateId: string) {
    if (templateId === customTemplateId) {
      saveSettings({ selectedEmailTemplateId: customTemplateId });
      return;
    }
    const template = emailTemplates.find((item) => item.id === templateId);
    if (!template) return;
    saveSettings({
      selectedEmailTemplateId: templateId,
      emailTemplate: composeTemplate(template, {
        id: state.selectedSignatureTemplateId || customSignatureId,
        name: "Selected signature",
        body: state.emailSignature || defaultEmailSignature,
      }),
    });
  }

  function selectSignatureTemplate(signatureId: string) {
    if (signatureId === customSignatureId) {
      saveSettings({ selectedSignatureTemplateId: customSignatureId });
      return;
    }
    const signature = signatureTemplates.find((item) => item.id === signatureId);
    const template = emailTemplates.find(
      (item) => item.id === state.selectedEmailTemplateId,
    );
    const emailSignature = signature?.body || defaultEmailSignature;
    saveSettings({
      selectedSignatureTemplateId: signatureId,
      emailSignature,
      emailTemplate:
        template && signature
          ? composeTemplate(template, signature)
          : state.emailTemplate,
    });
  }
  function startAnalysis() {
    setCopied(false);
    chrome.runtime.sendMessage(
      {
        type: "SAVE_SETTINGS",
        apiBaseUrl: state.apiBaseUrl,
        emailTemplate: state.emailTemplate,
        emailSignature: state.emailSignature,
        selectedEmailTemplateId: state.selectedEmailTemplateId,
        selectedSignatureTemplateId: state.selectedSignatureTemplateId,
        aiModel: (state as any).aiModel || "auto",
      },
      () => {
        chrome.runtime.sendMessage({ type: "START_ANALYSIS" });
      },
    );
  }

  function stopAnalysis() {
    chrome.runtime.sendMessage({ type: "STOP_ANALYSIS" });
  }

  async function copyEmail() {
    if (!state.email) return;
    await navigator.clipboard.writeText(
      `Subject: ${state.email.subject}\n\n${state.email.body}`,
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  const tabUrl = (state && (state as any).tab && (state as any).tab.url) || "";
  const disabled =
    Boolean(state?.loading) ||
    !tabUrl ||
    (typeof tabUrl === "string" && tabUrl.startsWith("chrome://"));

  return (
    <main className="min-h-screen w-[420px] overflow-hidden bg-[#f8fafc] text-slate-950">
      <section className="border-b border-slate-200 bg-[#f1f7f4] px-5 pb-5 pt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-slate-950 text-white shadow-glow">
              <Radar size={19} />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-normal">MyCRWL</h1>
              <p className="text-xs text-slate-600">Website intelligence</p>
            </div>
          </div>
          <span className="rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs font-medium text-emerald-700 shadow-sm">
            Side panel
          </span>
        </div>

        <div className="mt-5 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-emerald-100 text-emerald-700">
              <Globe2 size={19} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">
                {state.tab.title || "Current tab"}
              </p>
              <p className="mt-1 truncate text-xs text-slate-500">
                {state.tab.url || "No active website detected"}
              </p>
            </div>
          </div>

          <input
            value={state.apiBaseUrl}
            onChange={(event) =>
              saveSettings({ apiBaseUrl: event.target.value })
            }
            className="mt-4 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs outline-none transition focus:border-slate-400"
            aria-label="Backend API URL"
          />

          <label className="mt-3 block text-xs font-semibold text-slate-700">
            AI Model
          </label>
          <select
            value={(state as any).aiModel || "auto"}
            onChange={(e) => saveSettings({ aiModel: e.target.value })}
            className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs outline-none"
          >
            <option value="auto">Auto (Gemini → Hugging Face)</option>
            <option value="gemini">Gemini</option>
            <option value="huggingface">Hugging Face</option>
          </select>

          <label className="mt-4 block text-xs font-semibold text-slate-700">
            Email template
          </label>
          <select
            value={state.selectedEmailTemplateId || customTemplateId}
            onChange={(event) => selectEmailTemplate(event.target.value)}
            className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs outline-none transition focus:border-slate-400"
          >
            <option value={customTemplateId}>Custom writing</option>
            {emailTemplates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>

          <label className="mt-3 block text-xs font-semibold text-slate-700">
            Signature template
          </label>
          <select
            value={state.selectedSignatureTemplateId || "simple"}
            onChange={(event) => selectSignatureTemplate(event.target.value)}
            className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs outline-none transition focus:border-slate-400"
          >
            <option value={customSignatureId}>Custom signature in body</option>
            {signatureTemplates.map((signature) => (
              <option key={signature.id} value={signature.id}>
                {signature.name}
              </option>
            ))}
          </select>

          <label
            className="mt-3 block text-xs font-semibold text-slate-700"
            htmlFor="email-signature"
          >
            Signature sent to AI
          </label>
          <textarea
            id="email-signature"
            value={state.emailSignature || defaultEmailSignature}
            onChange={(event) =>
              saveSettings({
                emailSignature: event.target.value,
                selectedSignatureTemplateId: customSignatureId,
              })
            }
            className="mt-2 min-h-[76px] w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-xs leading-5 outline-none transition focus:border-slate-400"
          />

          <label
            className="mt-3 block text-xs font-semibold text-slate-700"
            htmlFor="email-template"
          >
            Subject and body sent to AI
          </label>
          <textarea
            id="email-template"
            value={state.emailTemplate}
            onChange={(event) =>
              saveSettings({
                emailTemplate: event.target.value,
                selectedEmailTemplateId: customTemplateId,
              })
            }
            className="mt-2 min-h-[168px] w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-xs leading-5 outline-none transition focus:border-slate-400"
          />

          <div className="mt-4 flex gap-2">
            <button
              onClick={startAnalysis}
              disabled={disabled}
              className="flex h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-semibold text-white shadow-glow transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {state.loading ? (
                <Loader2 className="animate-spin" size={17} />
              ) : (
                <Sparkles size={17} />
              )}
              {state.loading
                ? "Working in background"
                : "Analyze and Generate Email"}
            </button>
            <button
              onClick={stopAnalysis}
              disabled={!state.loading}
              className="flex h-11 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:opacity-40"
            >
              Stop
            </button>
          </div>

          <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
            <Activity size={14} />
            {state.status}
          </p>
          {state.error ? (
            <p className="mt-2 flex gap-2 text-xs leading-5 text-red-600">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              {state.error}
            </p>
          ) : null}
        </div>
      </section>

      <section className="max-h-[calc(100vh-390px)] min-h-[320px] overflow-y-auto px-5 py-4">
        <StageList stages={state.stages} />
        <AnimatePresence mode="wait">
          {state.analysis ? (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 space-y-3"
            >
              <ResultHeader analysis={state.analysis} />
              <OwnerInfoCard
                analysis={state.analysis}
                copied={copiedOwner}
                onCopy={() => {
                  const ownerInfo =
                    state.analysis?.owner_name || state.analysis?.owner_email
                      ? `${state.analysis.owner_name || "N/A"}\n${state.analysis.owner_email || "N/A"}`
                      : "Owner information not found";
                  navigator.clipboard.writeText(ownerInfo);
                  setCopiedOwner(true);
                  setTimeout(() => setCopiedOwner(false), 1600);
                }}
              />
              {state.email ? (
                <EmailCard
                  subject={state.email.subject}
                  body={state.email.body}
                  copied={copied}
                  onCopy={copyEmail}
                />
              ) : null}
              <PaletteCard
                colors={state.analysis.theme_colors}
                logo={state.analysis.logo_url || state.analysis.favicon_url}
              />
              <MetricGrid analysis={state.analysis} />
              <JsonCard
                title="Recommendations"
                value={state.analysis.improvement_suggestions}
              />
              {state.analysis.pdf_url ? (
                <a
                  href={state.analysis.pdf_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex h-11 items-center justify-center gap-2 rounded-lg bg-emerald-600 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
                >
                  <Download size={17} />
                  Download PDF Report
                </a>
              ) : null}
            </motion.div>
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-4 grid gap-3"
            >
              <EmptyCard
                icon={<Sparkles size={18} />}
                title="AI business intelligence"
                text="Category, offerings, audience, trust, SEO, UX, and conversion analysis."
              />
              <EmptyCard
                icon={<Mail size={18} />}
                title="Cold email generation"
                text="Uses the completed research and your editable format to write a specific outreach email."
              />
              <EmptyCard
                icon={<ShieldCheck size={18} />}
                title="PDF-ready reporting"
                text="Generates a polished local report with screenshots and recommendations."
              />
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </main>
  );
}

function StageList({ stages }: { stages: JobStage[] }) {
  const visibleStages = stages.length
    ? stages
    : ["collecting", "crawling", "ai", "email", "pdf", "complete"].map(
        (id) => ({ id, label: id, state: "pending" as const }),
      );
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-sm font-semibold">Process</p>
      <div className="mt-3 space-y-2">
        {visibleStages.map((stage) => (
          <div
            key={stage.id}
            className="flex items-center gap-2 text-xs text-slate-600"
          >
            {stage.state === "done" ? (
              <CheckCircle2 size={15} className="text-emerald-600" />
            ) : stage.state === "active" ? (
              <Loader2 size={15} className="animate-spin text-slate-900" />
            ) : stage.state === "error" ? (
              <AlertCircle size={15} className="text-red-600" />
            ) : (
              <span className="h-[15px] w-[15px] rounded-full border border-slate-300" />
            )}
            <span
              className={
                stage.state === "active" ? "font-semibold text-slate-900" : ""
              }
            >
              {stage.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ResultHeader({ analysis }: { analysis: AnalysisResponse }) {
  const aiLabel =
    analysis.ai_source === "gemini"
      ? "Gemini"
      : analysis.ai_source === "huggingface"
        ? "Hugging Face"
        : "Local fallback";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
            Analysis
          </p>
          <h2 className="mt-2 text-base font-semibold">
            {analysis.website_name}
          </h2>
        </div>
        <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-700">
          {aiLabel}
        </span>
      </div>
      <p className="mt-2 text-sm leading-5 text-slate-600">
        {analysis.short_summary}
      </p>
      {analysis.ai_source === "local_fallback" && analysis.ai_failure_reason ? (
        <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <span className="font-semibold">AI fallback reason:</span> {analysis.ai_failure_reason}
        </p>
      ) : null}
    </div>
  );
}

function OwnerInfoCard({
  analysis,
  copied,
  onCopy,
}: {
  analysis: AnalysisResponse;
  copied: boolean;
  onCopy: () => void;
}) {
  const hasOwnerInfo = analysis.owner_name || analysis.owner_email;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold">Owner / Contact Information</p>
        <button
          onClick={onCopy}
          className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 text-slate-700 transition hover:bg-slate-50"
          title="Copy owner info"
        >
          {copied ? (
            <CheckCircle2 size={16} className="text-emerald-600" />
          ) : (
            <Clipboard size={16} />
          )}
        </button>
      </div>
      {hasOwnerInfo ? (
        <div className="mt-2 space-y-1 text-xs">
          {analysis.owner_name && (
            <p className="text-slate-700">
              <span className="font-medium">Name:</span> {analysis.owner_name}
            </p>
          )}
          {analysis.owner_email && (
            <p className="text-slate-700">
              <span className="font-medium">Email:</span> {analysis.owner_email}
            </p>
          )}
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          Owner or contact information not found
        </p>
      )}
    </div>
  );
}

function EmailCard({
  subject,
  body,
  copied,
  onCopy,
}: {
  subject: string;
  body: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold">Personalized cold email</p>
        <button
          onClick={onCopy}
          className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 text-slate-700 transition hover:bg-slate-50"
          title="Copy email"
        >
          {copied ? (
            <CheckCircle2 size={16} className="text-emerald-600" />
          ) : (
            <Clipboard size={16} />
          )}
        </button>
      </div>
      <p className="mt-3 text-xs font-semibold text-slate-800">
        Subject: {subject}
      </p>
      <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-600">
        {body}
      </p>
    </div>
  );
}

function PaletteCard({ colors, logo }: { colors: string[]; logo: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Brand System</p>
        {logo ? (
          <img
            src={logo}
            className="h-8 max-w-[92px] rounded object-contain"
            alt="Detected logo"
          />
        ) : null}
      </div>
      <div className="mt-3 flex gap-2">
        {colors.length ? (
          colors
            .slice(0, 7)
            .map((color) => (
              <span
                key={color}
                title={color}
                className="h-8 flex-1 rounded-md border border-black/5"
                style={{ background: color }}
              />
            ))
        ) : (
          <p className="text-xs text-slate-500">No CSS colors detected.</p>
        )}
      </div>
    </div>
  );
}

function MetricGrid({ analysis }: { analysis: AnalysisResponse }) {
  const seo = analysis.seo_analysis.quality_score ?? "N/A";
  const trust = analysis.trust_analysis.trust_score ?? "N/A";
  const category = analysis.category_analysis.primary_category ?? "Unknown";
  const pages = analysis.technical_analysis.pages_crawled ?? "N/A";
  return (
    <div className="grid grid-cols-2 gap-3">
      <Metric label="Category" value={String(category)} />
      <Metric label="SEO" value={String(seo)} />
      <Metric label="Trust" value={String(trust)} />
      <Metric label="Pages" value={String(pages)} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-h-[84px] rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-2 break-words text-sm font-semibold text-slate-900">
        {value}
      </p>
    </div>
  );
}

function JsonCard({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown>;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-semibold">{title}</p>
      <div className="mt-2 space-y-2">
        {Object.entries(value)
          .slice(0, 5)
          .map(([key, item]) => (
            <p key={key} className="text-xs leading-5 text-slate-600">
              <span className="font-semibold text-slate-800">
                {key.replaceAll("_", " ")}:
              </span>{" "}
              {Array.isArray(item) ? item.join(", ") : String(item)}
            </p>
          ))}
      </div>
    </div>
  );
}

function EmptyCard({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-700">
          {icon}
        </div>
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">{text}</p>
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);

