import React from "react";
import ReactDOM from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, Download, Globe2, Loader2, Palette, Radar, ShieldCheck, Sparkles } from "lucide-react";
import type { AnalysisResponse, DomSnapshot } from "../shared/types";
import "./styles.css";

type TabInfo = { url: string; title: string; tabId?: number };

const fallbackApi = "http://127.0.0.1:8000";

function App() {
  const [tab, setTab] = React.useState<TabInfo>({ url: "", title: "" });
  const [apiBaseUrl, setApiBaseUrl] = React.useState(fallbackApi);
  const [analysis, setAnalysis] = React.useState<AnalysisResponse | null>(null);
  const [status, setStatus] = React.useState("Ready");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    chrome.storage.sync.get(["apiBaseUrl"], (items) => setApiBaseUrl(items.apiBaseUrl || fallbackApi));
    chrome.runtime.sendMessage({ type: "GET_ACTIVE_TAB" }, (response: TabInfo) => {
      if (response) setTab(response);
    });
  }, []);

  async function collectDom(tabId?: number): Promise<DomSnapshot | null> {
    if (!tabId) return null;
    try {
      const response = await chrome.tabs.sendMessage(tabId, { type: "COLLECT_DOM" });
      return response as DomSnapshot;
    } catch {
      return null;
    }
  }

  async function analyze() {
    setLoading(true);
    setError("");
    setAnalysis(null);
    setStatus("Collecting visible page context");
    try {
      const dom = await collectDom(tab.tabId);
      setStatus("Crawling and analyzing website");
      const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: tab.url, dom_snapshot: dom ? JSON.stringify(dom) : undefined })
      });
      if (!response.ok) throw new Error(`Backend returned ${response.status}`);
      const data = (await response.json()) as AnalysisResponse;
      setAnalysis(data);
      setStatus(data.ai_source === "gemini" ? "Gemini analysis complete" : "Local analysis complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setStatus("Check backend connection");
    } finally {
      setLoading(false);
    }
  }

  function saveApiBaseUrl(value: string) {
    setApiBaseUrl(value);
    chrome.storage.sync.set({ apiBaseUrl: value });
  }

  return (
    <main className="min-h-[640px] w-[420px] overflow-hidden bg-[#f8fafc] text-slate-950">
      <section className="relative border-b border-white/70 bg-[radial-gradient(circle_at_top_left,#dff7ef,transparent_30%),linear-gradient(135deg,#f8fafc,#eaf2ff_55%,#fff7ed)] px-5 pb-5 pt-4">
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
          <span className="rounded-full border border-white/80 bg-white/70 px-3 py-1 text-xs font-medium text-slate-700 shadow-sm backdrop-blur">
            MV3
          </span>
        </div>

        <div className="mt-5 rounded-lg border border-white/80 bg-white/70 p-4 shadow-sm backdrop-blur-xl">
          <div className="flex items-start gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-emerald-100 text-emerald-700">
              <Globe2 size={19} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{tab.title || "Current tab"}</p>
              <p className="mt-1 truncate text-xs text-slate-500">{tab.url || "No active website detected"}</p>
            </div>
          </div>
          <input
            value={apiBaseUrl}
            onChange={(event) => saveApiBaseUrl(event.target.value)}
            className="mt-4 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs outline-none transition focus:border-slate-400"
            aria-label="Backend API URL"
          />
          <button
            onClick={analyze}
            disabled={loading || !tab.url || tab.url.startsWith("chrome://")}
            className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-semibold text-white shadow-glow transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {loading ? <Loader2 className="animate-spin" size={17} /> : <Sparkles size={17} />}
            Analyze Website
          </button>
          <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
            <Activity size={14} />
            {status}
          </p>
          {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
        </div>
      </section>

      <section className="max-h-[360px] overflow-y-auto px-5 py-4">
        <AnimatePresence mode="wait">
          {analysis ? (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
              <ResultHeader analysis={analysis} />
              <PaletteCard colors={analysis.theme_colors} logo={analysis.logo_url || analysis.favicon_url} />
              <MetricGrid analysis={analysis} />
              <JsonCard title="Recommendations" value={analysis.improvement_suggestions} />
              {analysis.pdf_url ? (
                <a
                  href={analysis.pdf_url}
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
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-3">
              <EmptyCard icon={<Sparkles size={18} />} title="AI business intelligence" text="Category, offerings, audience, trust, SEO, UX, and conversion analysis." />
              <EmptyCard icon={<Palette size={18} />} title="Brand extraction" text="Logo, favicon, color palette, CTA language, and visual personality." />
              <EmptyCard icon={<ShieldCheck size={18} />} title="PDF-ready reporting" text="Generates a polished local report with screenshots and recommendations." />
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </main>
  );
}

function ResultHeader({ analysis }: { analysis: AnalysisResponse }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Analysis</p>
      <h2 className="mt-2 text-base font-semibold">{analysis.website_name}</h2>
      <p className="mt-2 text-sm leading-5 text-slate-600">{analysis.short_summary}</p>
    </div>
  );
}

function PaletteCard({ colors, logo }: { colors: string[]; logo: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Brand System</p>
        {logo ? <img src={logo} className="h-8 max-w-[92px] rounded object-contain" alt="Detected logo" /> : null}
      </div>
      <div className="mt-3 flex gap-2">
        {colors.length ? colors.slice(0, 7).map((color) => <span key={color} title={color} className="h-8 flex-1 rounded-md border border-black/5" style={{ background: color }} />) : <p className="text-xs text-slate-500">No CSS colors detected.</p>}
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
      <p className="mt-2 break-words text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function JsonCard({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-semibold">{title}</p>
      <div className="mt-2 space-y-2">
        {Object.entries(value).slice(0, 5).map(([key, item]) => (
          <p key={key} className="text-xs leading-5 text-slate-600">
            <span className="font-semibold text-slate-800">{key.replaceAll("_", " ")}:</span> {Array.isArray(item) ? item.join(", ") : String(item)}
          </p>
        ))}
      </div>
    </div>
  );
}

function EmptyCard({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-700">{icon}</div>
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">{text}</p>
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
