export interface ReportSummary {
  filename: string;
  title: string;
  size_bytes: number;
  modified_at: string;
  is_markdown: boolean;
}

export interface ReportDetail {
  filename: string;
  title: string;
  content: string;
  size_bytes: number;
  modified_at: string;
}
