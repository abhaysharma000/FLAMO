import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ResearchReportsPage } from '../src/pages/ResearchReportsPage';
import { ReportDetail, ReportSummary } from '../src/types/report';
import { TaskResponse } from '../src/types/task';

describe('ResearchReportsPage Component', () => {
  const mockReports: ReportSummary[] = [
    {
      filename: 'ai_frameworks_comparison.md',
      title: 'Top 5 AI Agent Frameworks',
      size_bytes: 16000,
      modified_at: '2026-10-11T11:00:00Z',
      is_markdown: true,
    },
  ];

  const mockActiveReport: ReportDetail = {
    filename: 'ai_frameworks_comparison.md',
    title: 'Top 5 AI Agent Frameworks',
    content: '# Executive Summary\n\nLangGraph and CrewAI comparison.',
    size_bytes: 16000,
    modified_at: '2026-10-11T11:00:00Z',
  };

  const mockTaskWithClaims: TaskResponse = {
    id: 'task-research-1',
    goal: 'Research frameworks and verify claims',
    status: 'completed',
    current_step_index: 2,
    completed_steps: [],
    failed_steps: [],
    retry_count: 0,
    created_at: '2026-10-11T11:00:00Z',
    updated_at: '2026-10-11T11:05:00Z',
    errors: [],
    total_tool_calls: 5,
    tool_results: [],
    evidence_count: 2,
    claims: [
      {
        id: 'claim-101',
        statement: 'LangGraph implements stateful cyclic agent graphs.',
        status: 'VERIFIED',
        confidence: 0.95,
        source_urls: ['https://langchain-ai.github.io/langgraph/'],
      },
      {
        id: 'claim-102',
        statement: 'Framework X is deprecated in favor of Framework Y.',
        status: 'CONFLICTING',
        confidence: 0.7,
        reasoning: 'Primary author repo contradicts blog claims.',
        source_urls: ['https://github.com/framework-x/framework-x'],
      },
      {
        id: 'claim-103',
        statement: 'Unverified rumor about a proprietary cloud acquisition.',
        status: 'UNVERIFIED',
        confidence: 0.3,
        reasoning: 'No authoritative source found.',
        source_urls: [],
      },
    ],
    verification_result: {
      is_valid: true,
      score: 0.8,
      status: 'PARTIALLY_VERIFIED',
      checks_passed: [],
      checks_failed: [],
      critique: 'Claims audited',
      evidence_pipeline: {
        evidence_items: [
          {
            id: 'ev-101',
            claim_id: 'claim-101',
            claim_text: 'LangGraph implements stateful cyclic agent graphs.',
            supporting_snippet: 'LangGraph is a library for building stateful, multi-actor applications with LLMs.',
            confidence: 0.95,
            status: 'VERIFIED',
            source: {
              url: 'https://langchain-ai.github.io/langgraph/',
              title: 'LangGraph Docs',
              source_type: 'PRIMARY',
              retrieval_status: 'retrieved', // Full page fetch
            },
          },
          {
            id: 'ev-102',
            claim_id: 'claim-102',
            claim_text: 'Framework X is deprecated in favor of Framework Y.',
            supporting_snippet: 'Brief search snippet mentioning rumors.',
            confidence: 0.6,
            status: 'CONFLICTING',
            source: {
              url: 'https://github.com/framework-x/framework-x',
              title: 'Search Result',
              source_type: 'WEB_SEARCH',
              retrieval_status: 'search_snippet', // Search snippet only
            },
          },
        ],
      },
    },
  };

  it('renders workspace reports and allows downloading', () => {
    const handleDownload = vi.fn();
    render(
      <ResearchReportsPage
        reports={mockReports}
        activeReport={mockActiveReport}
        tasks={[mockTaskWithClaims]}
        selectedTaskId="task-research-1"
        loadingReports={false}
        loadingDetail={false}
        error={null}
        onSelectReport={vi.fn()}
        onDownloadReport={handleDownload}
        onSelectTask={vi.fn()}
        onRefreshReports={vi.fn()}
      />
    );

    expect(screen.getAllByText('Top 5 AI Agent Frameworks').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/LangGraph and CrewAI comparison/)).toBeInTheDocument();

    const downloadBtn = screen.getByText('📥 Download File');
    fireEvent.click(downloadBtn);
    expect(handleDownload).toHaveBeenCalledWith('ai_frameworks_comparison.md');
  });

  it('renders claim-by-claim table with un-upgraded verification statuses', () => {
    render(
      <ResearchReportsPage
        reports={mockReports}
        activeReport={mockActiveReport}
        tasks={[mockTaskWithClaims]}
        selectedTaskId="task-research-1"
        loadingReports={false}
        loadingDetail={false}
        error={null}
        onSelectReport={vi.fn()}
        onDownloadReport={vi.fn()}
        onSelectTask={vi.fn()}
        onRefreshReports={vi.fn()}
      />
    );

    // Switch to Claims Verification Audit view
    fireEvent.click(screen.getByText(/Claim Verification Audit/));

    // Verify all claims rendered with exact status from backend
    expect(screen.getByText('claim-101')).toBeInTheDocument();
    expect(screen.getByText('VERIFIED')).toBeInTheDocument();
    expect(screen.getByText('claim-102')).toBeInTheDocument();
    expect(screen.getByText('CONFLICTING')).toBeInTheDocument();
    expect(screen.getByText('claim-103')).toBeInTheDocument();
    expect(screen.getByText('UNVERIFIED')).toBeInTheDocument();

    // Verify retrieval status distinguishes Full Page Fetch vs Search Snippet
    expect(screen.getByText('Full Page Fetch')).toBeInTheDocument();
    expect(screen.getByText('Search Snippet')).toBeInTheDocument();
  });
});
