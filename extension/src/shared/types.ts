export interface AnalysisResponse {
  website_name: string;
  website_url: string;
  short_summary: string;
  detailed_summary: string;
  category_analysis: Record<string, unknown>;
  business_analysis: Record<string, unknown>;
  branding_analysis: Record<string, unknown>;
  logo_analysis: Record<string, unknown>;
  ui_ux_analysis: Record<string, unknown>;
  seo_analysis: Record<string, unknown>;
  trust_analysis: Record<string, unknown>;
  technical_analysis: Record<string, unknown>;
  content_analysis: Record<string, unknown>;
  competitor_estimation: Record<string, unknown>;
  improvement_suggestions: Record<string, unknown>;
  theme_colors: string[];
  logo_url: string;
  favicon_url: string;
  screenshot_url: string;
  pdf_url: string;
  ai_source: string;
}

export interface DomSnapshot {
  title: string;
  url: string;
  description: string;
  headings: string[];
  visibleText: string;
  links: Array<{ text: string; href: string }>;
}
