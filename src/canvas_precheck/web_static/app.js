const state = {
  selectedRun: null,
  config: null,
  progressTimer: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function loadProgress() {
  const progress = await api("/api/runs/progress");
  const total = Number(progress.total || 0);
  const processed = Number(progress.processed || 0);
  const status = progress.status || "idle";
  const pct = total ? Math.round((processed / total) * 100) : 0;
  $("progressCount").textContent = `${processed}/${total || "?"}`;
  $("progressStudent").textContent = progress.current_student
    ? `Currently grading ${progress.current_student}`
    : status === "starting" ? "Preparing submissions..."
      : status === "cancelling" ? "Stopping after the current student..."
      : status === "failed" ? "The run failed."
      : status === "cancelled" ? "The run was cancelled."
      : status === "completed" ? "Run complete."
      : "No active run.";
  $("progressDetail").textContent = `${processed} students graded out of ${total || 0}`;
  $("progressBar").style.width = `${pct}%`;
  document.querySelector(".progressRing").style.setProperty("--progress", `${pct}%`);
  if (!["starting", "running", "cancelling"].includes(status) || (status === "starting" && total === 0 && processed === 0)) {
    setTimeout(hideProgressTile, 900);
  }
  return progress;
}

function showProgressTile() {
  $("progressOverlay").hidden = false;
  $("cancelRunButton").disabled = false;
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = setInterval(() => {
    loadProgress().catch(() => {});
  }, 900);
}

function hideProgressTile() {
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = null;
  $("progressOverlay").hidden = true;
}

function dismissProgressTile() {
  hideProgressTile();
  setStatus("Progress popup dismissed. The run may still be finishing in the background.");
}

async function cancelRun() {
  $("cancelRunButton").disabled = true;
  try {
    const result = await api("/api/runs/cancel", { method: "POST" });
    setStatus(result.message);
    $("progressStudent").textContent = result.message;
  } catch (err) {
    setStatus(err.message);
    $("cancelRunButton").disabled = false;
  }
}

function setStatus(message) {
  $("runStatus").textContent = message;
}

function currentPageFromHash() {
  const page = window.location.hash.replace("#", "");
  return ["setup", "runs", "students", "feedback"].includes(page) ? page : "setup";
}

function showPage(page) {
  const selected = ["setup", "runs", "students", "feedback"].includes(page)
    ? page
    : currentPageFromHash();
  document.querySelectorAll(".page").forEach((el) => {
    el.classList.toggle("active", el.id === `page-${selected}`);
  });
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    link.classList.toggle("active", link.dataset.pageLink === selected);
  });
  const stats = document.querySelector(".statsGrid");
  if (stats) stats.hidden = selected !== "runs";
  if (window.location.hash.replace("#", "") !== selected) {
    window.history.replaceState(null, "", `#${selected}`);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function option(label, value) {
  const opt = document.createElement("option");
  opt.textContent = label;
  opt.value = value;
  return opt;
}

function splitList(value) {
  return value
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function joinList(value) {
  return Array.isArray(value) ? value.join(", ") : "";
}

async function loadHealth() {
  const health = await api("/api/health");
  $("canvasBaseUrlInput").value = health.canvas_base_url || "https://jhu.instructure.com";
  $("canvasStatus").className = `statusChip ${health.canvas_token_set ? "success" : "neutral"}`;
  $("canvasStatus").textContent = health.canvas_token_set ? `Canvas ${health.token_source}` : "Canvas unset";
  $("openaiStatus").className = `statusChip ${health.openai_token_set ? "success" : "neutral"}`;
  $("openaiStatus").textContent = health.openai_token_set ? `OpenAI ${health.openai_token_source}` : "OpenAI optional";
  $("statProvider").textContent = state.config?.llm?.provider || "ollama";
  $("health").textContent = health.canvas_token_set
    ? `Canvas connected via ${health.token_source}: ${health.canvas_base_url}. OpenAI token: ${health.openai_token_set ? health.openai_token_source : "unset"}.`
    : `Canvas token is not set. OpenAI token: ${health.openai_token_set ? health.openai_token_source : "unset"}. Local run viewing still works.`;
}

async function saveCanvasSettings() {
  const token = $("canvasTokenInput").value.trim();
  const baseUrl = $("canvasBaseUrlInput").value.trim();
  if (!token) {
    setStatus("Paste a Canvas token first.");
    return;
  }
  $("saveCanvasSettings").disabled = true;
  try {
    const result = await api("/api/settings/canvas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, base_url: baseUrl }),
    });
    $("canvasTokenInput").value = "";
    setStatus(result.message);
    await loadHealth();
    await loadCourses();
  } catch (err) {
    setStatus(err.message);
  } finally {
    $("saveCanvasSettings").disabled = false;
  }
}

async function saveOpenAISettings() {
  const token = $("openaiTokenInput").value.trim();
  if (!token) {
    setStatus("Paste an OpenAI API token first.");
    return;
  }
  $("saveOpenAISettings").disabled = true;
  try {
    const result = await api("/api/settings/openai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    $("openaiTokenInput").value = "";
    setStatus(result.message);
    await loadHealth();
  } catch (err) {
    setStatus(err.message);
  } finally {
    $("saveOpenAISettings").disabled = false;
  }
}

function renderConfigForm(config) {
  state.config = config;
  $("statProvider").textContent = config.llm?.provider || "ollama";
  $("llmProviderInput").value = config.llm?.provider || "ollama";
  $("llmModelInput").value = config.llm?.model || "qwen2.5:3b";
  $("canonicalInput").value = config.canonical_filename || "";
  $("requiredFilesInput").value = joinList(config.required_files || []);
  $("allowedExtensionsInput").value = joinList(config.allowed_extensions || []);

  const ce = config.content_extract || {};
  $("maxCharsInput").value = ce.max_chars || 12000;
  $("chunkCharsInput").value = ce.chunk_chars || 3000;
  $("maxChunksInput").value = ce.max_chunks || 4;
  $("ocrEnabledInput").value = ce.ocr_enabled === false ? "false" : "true";
  $("preferExtensionsInput").value = joinList(ce.prefer_extensions || []);
  $("postingEnabledInput").checked = Boolean(config.posting?.enabled);

  const prompt = Array.isArray(config.llm_prompts) ? config.llm_prompts[0] : config.llm_prompts;
  $("promptInput").value = prompt?.prompt_template || "";
}

function configFromForm() {
  const config = structuredClone(state.config || {});
  config.llm = config.llm || {};
  config.llm.enabled = true;
  config.llm.provider = $("llmProviderInput").value;
  config.llm.model = $("llmModelInput").value.trim();
  config.canonical_filename = $("canonicalInput").value.trim();
  config.required_files = splitList($("requiredFilesInput").value);
  config.allowed_extensions = splitList($("allowedExtensionsInput").value);
  config.content_extract = config.content_extract || {};
  config.content_extract.enabled = true;
  config.content_extract.max_chars = Number($("maxCharsInput").value || 12000);
  config.content_extract.chunk_chars = Number($("chunkCharsInput").value || 3000);
  config.content_extract.max_chunks = Number($("maxChunksInput").value || 4);
  config.content_extract.ocr_enabled = $("ocrEnabledInput").value === "true";
  config.content_extract.prefer_extensions = splitList($("preferExtensionsInput").value);
  config.posting = config.posting || {};
  config.posting.enabled = $("postingEnabledInput").checked;

  const promptTemplate = $("promptInput").value.trim();
  const existingPrompt = Array.isArray(config.llm_prompts)
    ? config.llm_prompts[0] || {}
    : config.llm_prompts || {};
  config.llm_prompts = [{
    name: existingPrompt.name || "assignment_review",
    prompt_template: promptTemplate,
  }];

  return config;
}

async function loadConfig() {
  const configPath = $("configInput").value || "configs/a6.json";
  try {
    const result = await api(`/api/config?config_path=${encodeURIComponent(configPath)}`);
    renderConfigForm(result.config);
    setStatus(`Loaded ${result.config_path}`);
  } catch (err) {
    setStatus(err.message);
  }
}

async function saveConfig() {
  const configPath = $("configInput").value || "configs/a6.json";
  const config = configFromForm();
  $("saveConfigButton").disabled = true;
  try {
    const result = await api("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config_path: configPath, config }),
    });
    state.config = config;
    setStatus(result.message);
  } catch (err) {
    setStatus(err.message);
  } finally {
    $("saveConfigButton").disabled = false;
  }
}

async function loadCourses() {
  const select = $("courseSelect");
  select.replaceChildren(option("Loading courses...", ""));
  try {
    const courses = await api("/api/courses");
    select.replaceChildren(option("Choose a course", ""));
    courses.forEach((course) => {
      select.appendChild(option(`${course.name} (${course.id})`, course.id));
    });
  } catch (err) {
    select.replaceChildren(option("Canvas courses unavailable", ""));
    setStatus(err.message);
  }
}

async function loadAssignments(courseId) {
  const select = $("assignmentSelect");
  select.replaceChildren(option("Loading assignments...", ""));
  try {
    const assignments = await api(`/api/courses/${courseId}/assignments`);
    select.replaceChildren(option("Choose an assignment", ""));
    assignments.forEach((assignment) => {
      const due = assignment.due_at ? ` due ${assignment.due_at.slice(0, 10)}` : "";
      select.appendChild(option(`${assignment.name} (${assignment.id})${due}`, assignment.id));
    });
  } catch (err) {
    select.replaceChildren(option("Assignments unavailable", ""));
    setStatus(err.message);
  }
}

async function loadRuns() {
  const runs = await api("/api/runs");
  const list = $("runsList");
  list.replaceChildren();
  const totalStudents = runs.reduce((sum, run) => sum + Number(run.student_count || 0), 0);
  $("statRuns").textContent = runs.length;
  $("statStudents").textContent = totalStudents;
  $("statLatest").textContent = runs.length
    ? `${runs[runs.length - 1].course_id}/${runs[runs.length - 1].assignment_id}`
    : "None";
  if (!runs.length) {
    list.innerHTML = `<div class="empty"><strong>No local runs yet</strong><span>Run a small precheck to create your first result set.</span></div>`;
    return;
  }
  runs.forEach((run) => {
    const item = document.createElement("button");
    item.className = "item";
    item.innerHTML = `
      <strong>Course ${escapeHtml(run.course_id)} · Assignment ${escapeHtml(run.assignment_id)}</strong>
      <span class="metaRow">
        <span class="badge ${run.has_summary ? "success" : "warn"}">${run.has_summary ? "Excel ready" : "No Excel"}</span>
        <span class="badge">${escapeHtml(run.student_count)} students</span>
      </span>
      <span>${escapeHtml(run.path)}</span>
    `;
    item.addEventListener("click", () => selectRun(run.course_id, run.assignment_id));
    list.appendChild(item);
  });
}

async function selectRun(courseId, assignmentId) {
  state.selectedRun = { courseId, assignmentId };
  showPage("students");
  $("summaryLink").hidden = false;
  $("summaryLink").href = `/api/runs/${courseId}/${assignmentId}/summary`;
  const students = await api(`/api/runs/${courseId}/${assignmentId}/students`);
  const list = $("studentsList");
  list.replaceChildren();
  if (!students.length) {
    list.innerHTML = `<div class="empty"><strong>No students found</strong><span>This run does not have student output folders yet.</span></div>`;
    return;
  }
  students.forEach((student) => {
    const item = document.createElement("button");
    item.className = "item";
    const statusClass = student.findings_count ? "warn" : "success";
    const statusText = student.findings_count ? `${student.findings_count} findings` : "Clean checks";
    const summary = student.overall ? student.overall.slice(0, 190) : "No LLM summary yet";
    item.innerHTML = `
      <strong>${escapeHtml(student.student_name)}</strong>
      <span class="metaRow">
        <span class="badge">User ${escapeHtml(student.user_id)}</span>
        <span class="badge ${statusClass}">${escapeHtml(statusText)}</span>
        <span class="badge ${student.has_feedback ? "success" : "warn"}">${student.has_feedback ? "Feedback ready" : "No feedback"}</span>
      </span>
      <span>${escapeHtml(summary)}</span>
    `;
    item.addEventListener("click", () => loadStudent(courseId, assignmentId, student.user_id, student.student_name));
    list.appendChild(item);
  });
}

async function loadStudent(courseId, assignmentId, userId, name) {
  const detail = await api(`/api/runs/${courseId}/${assignmentId}/students/${userId}`);
  showPage("feedback");
  $("detailEmpty").hidden = true;
  $("detailContent").hidden = false;
  $("detailName").textContent = `${name} · ${userId}`;
  $("feedbackMarkdown").textContent = detail.feedback_md || "No feedback.md found.";
  $("llmJson").textContent = JSON.stringify(detail.llm || {}, null, 2);
}

async function startRun() {
  const courseId = $("courseSelect").value;
  const assignmentId = $("assignmentSelect").value;
  const limitValue = $("limitInput").value;
  const userValue = $("userInput").value;
  const payload = {
    config_path: $("configInput").value || "configs/a6.json",
    course_id: courseId ? Number(courseId) : null,
    assignment_id: assignmentId ? Number(assignmentId) : null,
    limit: limitValue ? Number(limitValue) : null,
    user_id: userValue ? Number(userValue) : null,
  };

  $("runButton").disabled = true;
  setStatus("Running precheck...");
  showProgressTile();
  try {
    const result = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus(JSON.stringify(result, null, 2));
    await loadRuns();
    if (result.course_id && result.assignment_id) {
      await selectRun(result.course_id, result.assignment_id);
    }
  } catch (err) {
    setStatus(err.message);
  } finally {
    await loadProgress().catch(() => {});
    setTimeout(hideProgressTile, 800);
    $("runButton").disabled = false;
  }
}

async function boot() {
  window.addEventListener("hashchange", () => showPage());
  showPage();

  $("courseSelect").addEventListener("change", (event) => {
    if (event.target.value) loadAssignments(event.target.value);
  });
  $("saveCanvasSettings").addEventListener("click", saveCanvasSettings);
  $("saveOpenAISettings").addEventListener("click", saveOpenAISettings);
  $("loadConfigButton").addEventListener("click", loadConfig);
  $("saveConfigButton").addEventListener("click", saveConfig);
  $("refreshRuns").addEventListener("click", async () => {
    await loadRuns();
    showPage("runs");
  });
  $("runButton").addEventListener("click", startRun);
  $("cancelRunButton").addEventListener("click", cancelRun);
  $("closeProgressButton").addEventListener("click", dismissProgressTile);

  await loadHealth();
  await loadConfig();
  await loadCourses();
  await loadRuns();
}

boot().catch((err) => setStatus(err.message));
