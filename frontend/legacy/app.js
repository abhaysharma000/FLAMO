/**
 * FLAMO Autonomous AI Operations Agent - Frontend Controller
 * Supporting Real-Time SSE Streams, Hierarchical Swarm Telemetry, and HITL.
 */

let currentTaskId = null;
let pollInterval = null;
let eventSource = null;
let startTime = null;
let timerInterval = null;

// DOM Elements
const goalInput = document.getElementById("taskGoalInput");
const submitBtn = document.getElementById("submitTaskBtn");
const cancelBtn = document.getElementById("cancelTaskBtn");
const missionDashboard = document.getElementById("missionDashboard");
const statusBadge = document.getElementById("statusBadge");
const runtimeCounter = document.getElementById("runtimeCounter");
const activeAgentBadge = document.getElementById("activeAgentBadge");
const llmCallsCount = document.getElementById("llmCallsCount");
const toolCount = document.getElementById("toolCount");
const evidenceCountBadge = document.getElementById("evidenceCountBadge");
const tokenUsageBadge = document.getElementById("tokenUsageBadge");
const costBadge = document.getElementById("costBadge");

const hitlApprovalCard = document.getElementById("hitlApprovalCard");
const hitlActionDesc = document.getElementById("hitlActionDesc");
const hitlApproveBtn = document.getElementById("hitlApproveBtn");
const hitlRejectBtn = document.getElementById("hitlRejectBtn");

const planList = document.getElementById("planList");
const planComplexity = document.getElementById("planComplexity");
const claimsBody = document.getElementById("claimsBody");
const evidenceStatusBadge = document.getElementById("evidenceStatusBadge");
const verificationStatusBadge = document.getElementById("verificationStatusBadge");
const verificationBody = document.getElementById("verificationBody");
const toolActivityList = document.getElementById("toolActivityList");
const toolCallsBadge = document.getElementById("toolCallsBadge");
const finalAnswerContent = document.getElementById("finalAnswerContent");
const copyResultBtn = document.getElementById("copyResultBtn");
const traceEventsList = document.getElementById("traceEventsList");
const traceEventsCount = document.getElementById("traceEventsCount");
const toggleTraceBtn = document.getElementById("toggleTraceBtn");
const pastTasksList = document.getElementById("pastTasksList");
const refreshTasksBtn = document.getElementById("refreshTasksBtn");
const systemStatusText = document.getElementById("systemStatusText");
const modelBadge = document.getElementById("modelBadge");

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  fetchSystemHealth();
  fetchPastTasks();

  // Preset chips
  document.querySelectorAll(".preset-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      goalInput.value = btn.getAttribute("data-query");
      goalInput.focus();
    });
  });

  submitBtn.addEventListener("click", handleDeploy);
  cancelBtn.addEventListener("click", handleCancel);
  refreshTasksBtn.addEventListener("click", fetchPastTasks);
  copyResultBtn.addEventListener("click", handleCopyResult);

  hitlApproveBtn.addEventListener("click", handleHitlApprove);
  hitlRejectBtn.addEventListener("click", handleHitlReject);

  goalInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleDeploy();
    }
  });

  toggleTraceBtn.addEventListener("click", () => {
    if (traceEventsList.style.maxHeight === "600px") {
      traceEventsList.style.maxHeight = "250px";
      toggleTraceBtn.textContent = "Expand Trace Details";
    } else {
      traceEventsList.style.maxHeight = "600px";
      toggleTraceBtn.textContent = "Collapse Trace Details";
    }
  });
});

async function fetchSystemHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error("Health check failed");
    const data = await res.json();
    systemStatusText.textContent = `Engine: ${data.status.toUpperCase()}`;
    if (data.model) {
      modelBadge.textContent = data.model;
    }
  } catch (err) {
    systemStatusText.textContent = "Engine: Offline";
    console.error("Health check error:", err);
  }
}

async function handleDeploy() {
  const goal = goalInput.value.trim();
  if (!goal) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Deploying...";
  cancelBtn.style.display = "inline-block";

  try {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: goal }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to create task");
    }

    const task = await res.json();
    currentTaskId = task.id;
    startTaskMonitoring(task);
  } catch (err) {
    alert(`Error: ${err.message}`);
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<span class="btn-icon">⚡</span> Deploy Agent';
    cancelBtn.style.display = "none";
  }
}

function startTaskMonitoring(initialTask) {
  missionDashboard.style.display = "block";
  startTime = Date.now();
  renderTaskState(initialTask);

  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    runtimeCounter.textContent = `${elapsed}s`;
  }, 100);

  // Close existing SSE stream if any
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  // Connect to live Server-Sent Events (SSE) stream
  try {
    eventSource = new EventSource(`/api/tasks/${initialTask.id}/events`);
    eventSource.onmessage = (event) => {
      try {
        const traceEvent = JSON.parse(event.data);
        handleLiveTraceEvent(traceEvent);
      } catch (e) {
        console.debug("SSE parse error:", e);
      }
    };
    eventSource.onerror = () => {
      // Fallback to polling if SSE encounters network issues
      if (!pollInterval) {
        pollInterval = setInterval(pollTaskStatus, 1000);
      }
    };
  } catch (e) {
    pollInterval = setInterval(pollTaskStatus, 1000);
  }

  // Periodic poll to ensure task state sync
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollTaskStatus, 1200);
}

function handleLiveTraceEvent(event) {
  // Update active specialist badge based on node
  if (event.node) {
    const nodeMap = {
      research_agent: "Research Agent",
      browser_agent: "Browser Agent",
      document_agent: "Document Agent",
      verifier: "Verification Agent",
      planner: "Planner",
      executor: "Executor",
      recovery: "Recovery Engine",
      supervisor: "Supervisor",
    };
    activeAgentBadge.textContent = nodeMap[event.node] || event.node;
  }
  // Re-fetch full task when meaningful milestones occur
  if (["plan_created", "tool_completed", "verification_completed", "task_completed", "task_failed", "human_approval_required"].includes(event.event_type)) {
    pollTaskStatus();
  }
}

async function pollTaskStatus() {
  if (!currentTaskId) return;

  try {
    const [taskRes, traceRes] = await Promise.all([
      fetch(`/api/tasks/${currentTaskId}`),
      fetch(`/api/tasks/${currentTaskId}/trace`),
    ]);

    if (!taskRes.ok) return;

    const task = await taskRes.json();
    renderTaskState(task);

    if (traceRes.ok) {
      const traces = await traceRes.json();
      renderTraces(traces);
    }

    // Handle HITL State
    if (task.status === "awaiting_approval") {
      hitlApprovalCard.style.display = "flex";
      hitlActionDesc.textContent = task.pending_action
        ? `Action: ${JSON.stringify(task.pending_action)}`
        : "The agent requires authorization for a sensitive workspace or browser operation.";
    } else {
      hitlApprovalCard.style.display = "none";
    }

    // Stop monitoring if terminal state reached
    if (["completed", "failed", "cancelled"].includes(task.status)) {
      if (pollInterval) clearInterval(pollInterval);
      if (timerInterval) clearInterval(timerInterval);
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<span class="btn-icon">⚡</span> Deploy Agent';
      cancelBtn.style.display = "none";
      if (task.duration_seconds) {
        runtimeCounter.textContent = `${task.duration_seconds.toFixed(1)}s`;
      }
      fetchPastTasks();
    }
  } catch (err) {
    console.error("Polling error:", err);
  }
}

async function handleHitlApprove() {
  if (!currentTaskId) return;
  hitlApproveBtn.disabled = true;
  try {
    await fetch(`/api/tasks/${currentTaskId}/approve`, { method: "POST" });
    pollTaskStatus();
  } catch (err) {
    alert("Approval error: " + err.message);
  } finally {
    hitlApproveBtn.disabled = false;
  }
}

async function handleHitlReject() {
  if (!currentTaskId) return;
  hitlRejectBtn.disabled = true;
  try {
    await fetch(`/api/tasks/${currentTaskId}/reject`, { method: "POST" });
    pollTaskStatus();
  } catch (err) {
    alert("Rejection error: " + err.message);
  } finally {
    hitlRejectBtn.disabled = false;
  }
}

async function handleCancel() {
  if (!currentTaskId) return;
  cancelBtn.disabled = true;
  cancelBtn.textContent = "Cancelling...";
  try {
    await fetch(`/api/tasks/${currentTaskId}/cancel`, { method: "POST" });
  } catch (err) {
    console.error("Cancel failed:", err);
  }
}

function renderTaskState(task) {
  // 1. Status Badge
  statusBadge.className = `status-pill status-${task.status}`;
  statusBadge.textContent = task.status.toUpperCase();

  // 2. Metrics & Telemetry
  toolCount.textContent = task.total_tool_calls || 0;
  evidenceCountBadge.textContent = task.evidence_count || 0;

  if (task.metrics) {
    llmCallsCount.textContent = task.metrics.llm_calls || 0;
    tokenUsageBadge.textContent = task.metrics.token_usage || "Not available from provider";
    costBadge.textContent = task.metrics.estimated_cost || "$0.00";
  }

  // 3. Execution Plan
  if (task.plan && task.plan.steps && task.plan.steps.length > 0) {
    planComplexity.textContent = `Complexity: ${task.plan.estimated_complexity.toUpperCase()}`;
    let html = "";
    task.plan.steps.forEach((step, idx) => {
      let icon = "○";
      let iconClass = "status-icon-pending";
      let isCurrent = idx === task.current_step_index && !["completed", "failed"].includes(task.status);

      if (step.status === "completed") {
        icon = "✓";
        iconClass = "status-icon-completed";
      } else if (isCurrent) {
        icon = "→";
        iconClass = "status-icon-in_progress";
      } else if (step.status === "failed") {
        icon = "⚠";
        iconClass = "status-icon-failed";
      }

      const activeClass = isCurrent ? "active" : step.status === "completed" ? "completed" : "";

      html += `
        <div class="plan-step-item ${activeClass}">
          <span class="plan-step-status-icon ${iconClass}">${icon}</span>
          <div class="step-details">
            <div class="step-title">
              <span>${step.id}. ${step.title}</span>
              ${step.tool_hint ? `<span class="step-tool-hint">${step.tool_hint}</span>` : ""}
            </div>
            <div class="step-desc">${step.description}</div>
            ${step.output ? `<div class="step-desc" style="color:#a7f3d0; margin-top:4px;">Observation: ${step.output}</div>` : ""}
          </div>
        </div>
      `;
    });
    planList.innerHTML = html;
  } else {
    planList.innerHTML = '<div class="empty-state">Synthesizing execution plan...</div>';
  }

  // 4. Evidence & Claims Panel
  if (task.claims && task.claims.length > 0) {
    evidenceStatusBadge.textContent = `${task.claims.length} Claims Evaluated`;
    let claimsHtml = "";
    task.claims.forEach((c) => {
      const statusClass = `status-${c.status.toLowerCase().replace('_', '-')}`;
      claimsHtml += `
        <div class="claim-item">
          <div class="claim-header">
            <span class="tag-badge ${statusClass}">${c.status}</span>
            <span style="font-size:0.75rem; color:#94a3b8;">Conf: ${Math.round((c.confidence || 0.8) * 100)}%</span>
          </div>
          <div class="claim-text">${c.statement}</div>
          ${c.reasoning ? `<div class="claim-reasoning">↳ ${c.reasoning}</div>` : ""}
        </div>
      `;
    });
    claimsBody.innerHTML = claimsHtml;
  } else {
    claimsBody.innerHTML = '<div class="empty-state">No research claims to extract for this task.</div>';
    evidenceStatusBadge.textContent = "No Claims";
  }

  // 5. Verification Card
  if (task.verification_result) {
    const vr = task.verification_result;
    verificationStatusBadge.textContent = vr.is_valid ? "PASSED (100%)" : `FLAGGED (${Math.round(vr.score * 100)}%)`;
    verificationStatusBadge.style.color = vr.is_valid ? "#10b981" : "#f43f5e";

    let vhtml = `<div style="font-size:0.85rem; font-weight:600; margin-bottom:4px;">${vr.critique}</div>`;
    if (vr.checks_passed && vr.checks_passed.length > 0) {
      vr.checks_passed.forEach((cp) => {
        vhtml += `<div class="check-item check-pass"><span>✓</span> ${cp}</div>`;
      });
    }
    if (vr.checks_failed && vr.checks_failed.length > 0) {
      vr.checks_failed.forEach((cf) => {
        vhtml += `<div class="check-item check-fail"><span>✕</span> ${cf}</div>`;
      });
    }
    verificationBody.innerHTML = vhtml;
  } else {
    verificationStatusBadge.textContent = "Pending";
    verificationStatusBadge.style.color = "#94a3b8";
    verificationBody.innerHTML = '<div class="empty-state">Verification will trigger automatically upon execution completion.</div>';
  }

  // 6. Final Verified Answer
  if (task.final_answer) {
    finalAnswerContent.innerHTML = formatMarkdown(task.final_answer);
  } else if (task.status === "failed") {
    finalAnswerContent.innerHTML = `<div style="color: #f43f5e;">Task failed: ${task.errors.join("; ") || "Unknown error"}</div>`;
  } else {
    finalAnswerContent.innerHTML = '<div class="empty-state pulse-text">Agent reasoning in progress...</div>';
  }
}

function renderTraces(traces) {
  traceEventsCount.textContent = traces.length;

  // Filter tool activities
  const toolEvents = traces.filter((t) => ["tool_started", "tool_completed", "tool_failed"].includes(t.event_type));
  toolCallsBadge.textContent = `${toolEvents.filter((t) => t.event_type !== "tool_started").length} Executions`;

  if (toolEvents.length > 0) {
    let tHtml = "";
    toolEvents.forEach((te) => {
      const isErr = te.event_type === "tool_failed";
      const isStart = te.event_type === "tool_started";
      const icon = isErr ? "✕" : isStart ? "▶" : "✓";
      const color = isErr ? "#f43f5e" : isStart ? "#38bdf8" : "#10b981";

      tHtml += `
        <div class="tool-activity-item">
          <div class="tool-act-header">
            <span style="color: ${color}; font-weight: bold;">${icon}</span>
            <span class="tool-act-name">${te.tool || "tool"}</span>
            <span class="tool-act-time font-mono">${te.duration_ms ? `${te.duration_ms}ms` : ""}</span>
          </div>
          <div class="tool-act-output font-mono">${JSON.stringify(te.details || te.error || {})}</div>
        </div>
      `;
    });
    toolActivityList.innerHTML = tHtml;
  }

  // Render Full Trace Timeline
  let traceHtml = "";
  traces.forEach((tr) => {
    traceHtml += `
      <div class="trace-item">
        <span class="trace-badge font-mono">${tr.event_type}</span>
        <span class="trace-node">[${tr.node}]</span>
        ${tr.tool ? `<span class="trace-tool">&lt;${tr.tool}&gt;</span>` : ""}
        <span class="trace-detail">${JSON.stringify(tr.details || {})}</span>
      </div>
    `;
  });
  traceEventsList.innerHTML = traceHtml;
}

async function fetchPastTasks() {
  try {
    const res = await fetch("/api/tasks?limit=10");
    if (!res.ok) return;
    const data = await res.json();
    if (!data.tasks || data.tasks.length === 0) {
      pastTasksList.innerHTML = '<div class="empty-state">No previous tasks recorded.</div>';
      return;
    }

    let html = "";
    data.tasks.forEach((t) => {
      html += `
        <div class="history-item" onclick="loadTask('${t.id}')">
          <div style="font-weight: 500; font-size: 0.85rem; max-width: 70%; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
            ${t.goal}
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <span class="status-pill status-${t.status}" style="font-size: 0.7rem; padding: 2px 8px;">${t.status.toUpperCase()}</span>
            <span class="font-mono" style="font-size: 0.75rem; color: #94a3b8;">${t.duration_seconds ? `${t.duration_seconds.toFixed(1)}s` : ""}</span>
          </div>
        </div>
      `;
    });
    pastTasksList.innerHTML = html;
  } catch (err) {
    console.error("Error loading past tasks:", err);
  }
}

function loadTask(taskId) {
  currentTaskId = taskId;
  fetch(`/api/tasks/${taskId}`)
    .then((r) => r.json())
    .then((task) => {
      missionDashboard.style.display = "block";
      renderTaskState(task);
      fetch(`/api/tasks/${taskId}/trace`)
        .then((r) => r.json())
        .then(renderTraces);
      window.scrollTo({ top: 300, behavior: "smooth" });
    });
}

function handleCopyResult() {
  const text = finalAnswerContent.innerText;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    copyResultBtn.textContent = "✓ Copied!";
    setTimeout(() => {
      copyResultBtn.textContent = "📋 Copy";
    }, 2000);
  });
}

function formatMarkdown(text) {
  if (!text) return "";
  let out = text
    .replace(/^### (.*$)/gim, '<h3 style="font-size:1.1rem; color:#f8fafc; margin:10px 0 6px;">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 style="font-size:1.2rem; color:#f8fafc; margin:14px 0 8px;">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 style="font-size:1.35rem; color:#f8fafc; margin:16px 0 10px;">$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong style="color:#fdba74;">$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/\n\n/gim, "<br/><br/>");
  return out;
}
