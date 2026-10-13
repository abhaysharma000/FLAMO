import React, { useEffect, useState, useRef, useCallback } from 'react';
import { apiClient } from './api/client';
import { Header } from './components/Header';
import { HitlModal } from './components/HitlModal';
import { OperatorLoginModal } from './components/OperatorLoginModal';
import { NavigationPage, Sidebar } from './components/Sidebar';
import { ExecutionTracePage } from './pages/ExecutionTracePage';
import { MemoryExplorerPage } from './pages/MemoryExplorerPage';
import { OverviewPage } from './pages/OverviewPage';
import { ResearchReportsPage } from './pages/ResearchReportsPage';
import { TaskCenterPage } from './pages/TaskCenterPage';
import { HealthResponse } from './types/health';
import { MemoryCategory, MemoryItem } from './types/memory';
import { ReportDetail, ReportSummary } from './types/report';
import { TaskResponse } from './types/task';
import { TraceEvent } from './types/trace';

export const App: React.FC = () => {
  const [currentPage, setCurrentPage] = useState<NavigationPage>('overview');

  // Authentication State
  const [authStatus, setAuthStatus] = useState<{
    auth_enabled: boolean;
    authenticated: boolean;
    username?: string | null;
  }>({ auth_enabled: false, authenticated: true });
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  // Backend state
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState<string | null>(null);

  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeTask, setActiveTask] = useState<TaskResponse | null>(null);
  const [taskSubmitting, setTaskSubmitting] = useState(false);

  const [traces, setTraces] = useState<TraceEvent[]>([]);
  const [tracesLoading, setTracesLoading] = useState(false);
  const [tracesError, setTracesError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [activeReport, setActiveReport] = useState<ReportDetail | null>(null);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportDetailLoading, setReportDetailLoading] = useState(false);
  const [reportsError, setReportsError] = useState<string | null>(null);

  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState<string | null>(null);

  // Human-in-the-Loop Checkpoint State
  const [hitlTask, setHitlTask] = useState<{ id: string; action: any } | null>(null);
  const [hitlProcessing, setHitlProcessing] = useState(false);

  const sseCleanupRef = useRef<(() => void) | null>(null);
  const pollTimerRef = useRef<any>(null);

  // --- Initial Data Fetching ---
  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const data = await apiClient.getHealth();
      setHealth(data);
    } catch (err: any) {
      console.warn('Health check error:', err);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    setTasksLoading(true);
    setTasksError(null);
    try {
      const data = await apiClient.listTasks(50);
      setTasks(data.tasks);
      // If there's an active task, update it
      if (activeTaskId) {
        const found = data.tasks.find((t) => t.id === activeTaskId);
        if (found) {
          setActiveTask(found);
          if (found.status === 'awaiting_approval') {
            setHitlTask({ id: found.id, action: found.pending_action });
          } else {
            setHitlTask(null);
          }
        }
      }
    } catch (err: any) {
      setTasksError(err.message || 'Failed to list tasks');
    } finally {
      setTasksLoading(false);
    }
  }, [activeTaskId]);

  const fetchReports = useCallback(async () => {
    setReportsLoading(true);
    setReportsError(null);
    try {
      const data = await apiClient.listReports();
      setReports(data);
      if (data.length > 0 && !activeReport) {
        // Automatically load first report preview
        loadReportContent(data[0].filename);
      }
    } catch (err: any) {
      setReportsError(err.message || 'Failed to list workspace reports');
    } finally {
      setReportsLoading(false);
    }
  }, [activeReport]);

  const loadReportContent = async (filename: string) => {
    setReportDetailLoading(true);
    try {
      const detail = await apiClient.getReport(filename);
      setActiveReport(detail);
    } catch (err: any) {
      alert(`Failed to load report: ${err.message}`);
    } finally {
      setReportDetailLoading(false);
    }
  };

  const fetchTraces = useCallback(async (taskId: string) => {
    setTracesLoading(true);
    setTracesError(null);
    try {
      const data = await apiClient.getTaskTrace(taskId);
      setTraces(data);
    } catch (err: any) {
      setTracesError(err.message || 'Failed to fetch trace events');
    } finally {
      setTracesLoading(false);
    }
  }, []);

  // --- Authentication Status Lifecycle ---
  const fetchAuthStatus = useCallback(async () => {
    try {
      const status = await apiClient.getAuthStatus();
      setAuthStatus(status);
      if (status.auth_enabled && !status.authenticated) {
        setLoginModalOpen(true);
      } else {
        setLoginModalOpen(false);
      }
    } catch (err: any) {
      console.warn('Failed to check auth status:', err);
    }
  }, []);

  useEffect(() => {
    fetchAuthStatus();
    fetchHealth();
    fetchTasks();
    fetchReports();
  }, [fetchAuthStatus, fetchHealth, fetchTasks, fetchReports]);

  // --- Task Selection & Streaming Lifecycle ---
  const selectTask = useCallback(
    (taskId: string) => {
      setActiveTaskId(taskId);
      const found = tasks.find((t) => t.id === taskId);
      if (found) {
        setActiveTask(found);
        if (found.status === 'awaiting_approval') {
          setHitlTask({ id: found.id, action: found.pending_action });
        }
      }
      fetchTraces(taskId);
    },
    [tasks, fetchTraces]
  );

  // Monitor active task execution with SSE and conservative polling
  useEffect(() => {
    if (!activeTaskId) return;

    const currentTask = activeTask;
    const isRunning = currentTask && ['running', 'planning', 'pending', 'verifying'].includes(currentTask.status);

    // Clean up previous SSE
    if (sseCleanupRef.current) {
      sseCleanupRef.current();
      sseCleanupRef.current = null;
    }
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (isRunning) {
      setIsStreaming(true);
      // Connect SSE
      sseCleanupRef.current = apiClient.connectTaskEvents(
        activeTaskId,
        (event) => {
          setTraces((prev) => {
            if (prev.some((e) => e.id === event.id)) return prev;
            return [...prev, event];
          });
          // Update active task if terminal or milestone event
          if (['task_completed', 'task_failed', 'task_cancelled', 'human_approval_required'].includes(event.event_type)) {
            fetchTasks();
          }
        },
        () => {
          setIsStreaming(false);
        }
      );

      // Conservative fallback polling
      pollTimerRef.current = setInterval(() => {
        apiClient.getTask(activeTaskId).then((updated) => {
          setActiveTask(updated);
          if (updated.status === 'awaiting_approval') {
            setHitlTask({ id: updated.id, action: updated.pending_action });
          } else {
            setHitlTask(null);
          }
          if (['completed', 'failed', 'cancelled'].includes(updated.status)) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
            if (sseCleanupRef.current) {
              sseCleanupRef.current();
              sseCleanupRef.current = null;
            }
            setIsStreaming(false);
            fetchTasks();
            fetchReports();
          }
        }).catch(() => {});
      }, 1500);
    } else {
      setIsStreaming(false);
    }

    return () => {
      if (sseCleanupRef.current) {
        sseCleanupRef.current();
        sseCleanupRef.current = null;
      }
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [activeTaskId, activeTask?.status, fetchTasks, fetchReports]);

  // --- Actions ---
  const handleDeployTask = async (goal: string) => {
    setTaskSubmitting(true);
    setTasksError(null);
    try {
      const created = await apiClient.createTask({ goal });
      setActiveTaskId(created.id);
      setActiveTask(created);
      await fetchTasks();
      fetchTraces(created.id);
    } catch (err: any) {
      setTasksError(err.message || 'Failed to deploy task');
      throw err;
    } finally {
      setTaskSubmitting(false);
    }
  };

  const handleCancelTask = async (taskId: string) => {
    try {
      await apiClient.cancelTask(taskId);
      await fetchTasks();
    } catch (err: any) {
      alert(`Failed to cancel: ${err.message}`);
    }
  };

  const handleResumeTask = async (taskId: string) => {
    try {
      const resumed = await apiClient.resumeTask(taskId);
      setActiveTask(resumed);
      await fetchTasks();
    } catch (err: any) {
      alert(`Resume failed: ${err.message}`);
    }
  };

  const handleApproveHitl = async () => {
    if (!hitlTask) return;
    setHitlProcessing(true);
    try {
      await apiClient.approveTask(hitlTask.id);
      setHitlTask(null);
      await fetchTasks();
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setHitlProcessing(false);
    }
  };

  const handleRejectHitl = async () => {
    if (!hitlTask) return;
    setHitlProcessing(true);
    try {
      await apiClient.rejectTask(hitlTask.id);
      setHitlTask(null);
      await fetchTasks();
    } catch (err: any) {
      alert(`Rejection error: ${err.message}`);
    } finally {
      setHitlProcessing(false);
    }
  };

  const handleDownloadReport = (filename: string) => {
    const url = apiClient.getReportDownloadUrl(filename);
    window.open(url, '_blank');
  };

  const handleSearchMemory = async (query: string, category?: MemoryCategory, limit?: number) => {
    setMemoryLoading(true);
    setMemoryError(null);
    try {
      const items = await apiClient.searchMemory(query, category, limit);
      setMemories(items);
    } catch (err: any) {
      setMemoryError(err.message || 'Memory retrieval failed');
      setMemories([]);
    } finally {
      setMemoryLoading(false);
    }
  };

  const handleStoreMemory = async (content: string, category: MemoryCategory, taskId?: string) => {
    await apiClient.storeMemory({ content, category, task_id: taskId });
  };

  const handleLoginSuccess = (username: string) => {
    setAuthStatus({
      auth_enabled: true,
      authenticated: true,
      username,
    });
    setLoginModalOpen(false);
    fetchHealth();
    fetchTasks();
    fetchReports();
  };

  const handleLogout = async () => {
    try {
      await apiClient.logout();
    } catch (err) {
      console.warn('Logout error:', err);
    }
    setAuthStatus((prev) => ({
      ...prev,
      authenticated: false,
      username: null,
    }));
    if (authStatus.auth_enabled) {
      setLoginModalOpen(true);
    }
  };


  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <Sidebar
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        activeTaskId={activeTaskId}
      />

      <div className="main-wrapper">
        {/* Top Header */}
        <Header
          health={health}
          loading={healthLoading}
          onRefreshHealth={fetchHealth}
          authEnabled={authStatus.auth_enabled}
          operatorUsername={authStatus.username}
          onLogout={handleLogout}
        />

        {/* Page Switcher */}
        <main>
          {currentPage === 'overview' && (
            <OverviewPage
              health={health}
              tasks={tasks}
              loading={tasksLoading}
              error={tasksError}
              onSelectTask={(id) => {
                selectTask(id);
                setCurrentPage('tasks');
              }}
              onRefresh={() => {
                fetchHealth();
                fetchTasks();
              }}
            />
          )}

          {currentPage === 'tasks' && (
            <TaskCenterPage
              activeTask={activeTask}
              tasks={tasks}
              loading={tasksLoading}
              submitting={taskSubmitting}
              error={tasksError}
              onSubmitGoal={handleDeployTask}
              onRefreshActiveTask={() => {
                if (activeTaskId) {
                  apiClient.getTask(activeTaskId).then(setActiveTask);
                  fetchTraces(activeTaskId);
                }
                fetchTasks();
              }}
              onCancelTask={handleCancelTask}
              onResumeTask={handleResumeTask}
              onSelectTask={selectTask}
              onNavigateToTrace={(id) => {
                selectTask(id);
                setCurrentPage('trace');
              }}
              onNavigateToReports={(id) => {
                selectTask(id);
                setCurrentPage('reports');
              }}
            />
          )}

          {currentPage === 'trace' && (
            <ExecutionTracePage
              tasks={tasks}
              selectedTaskId={activeTaskId}
              traces={traces}
              loadingTraces={tracesLoading}
              error={tracesError}
              onSelectTaskId={selectTask}
              onRefreshTraces={() => activeTaskId && fetchTraces(activeTaskId)}
              isStreaming={isStreaming}
            />
          )}

          {currentPage === 'reports' && (
            <ResearchReportsPage
              reports={reports}
              activeReport={activeReport}
              tasks={tasks}
              selectedTaskId={activeTaskId}
              loadingReports={reportsLoading}
              loadingDetail={reportDetailLoading}
              error={reportsError}
              onSelectReport={loadReportContent}
              onDownloadReport={handleDownloadReport}
              onSelectTask={selectTask}
              onRefreshReports={fetchReports}
            />
          )}

          {currentPage === 'memory' && (
            <MemoryExplorerPage
              health={health}
              memories={memories}
              loading={memoryLoading}
              error={memoryError}
              onSearch={handleSearchMemory}
              onStoreMemory={handleStoreMemory}
            />
          )}
        </main>
      </div>

      {/* Human-in-the-Loop Dialog Checkpoint */}
      {hitlTask && (
        <HitlModal
          taskId={hitlTask.id}
          pendingAction={hitlTask.action}
          onApprove={handleApproveHitl}
          onReject={handleRejectHitl}
          loading={hitlProcessing}
        />
      )}

      {/* Single Operator Authentication Modal */}
      <OperatorLoginModal
        isOpen={loginModalOpen}
        onLoginSuccess={handleLoginSuccess}
      />
    </div>
  );
};
