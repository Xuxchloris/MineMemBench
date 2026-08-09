"use strict";

const state = {
  snapshot: null,
  selectedCampaign: null,
  selected: null,
  detail: null,
  replay: null,
  frame: 0,
  timer: null,
};
const el = (id) => document.getElementById(id);
const text = (tag, value, cls) => {
  const node = document.createElement(tag);
  node.textContent = value;
  if (cls) node.className = cls;
  return node;
};
const fmt = (value) => value === null || value === undefined
  ? "N/A"
  : typeof value === "object" ? JSON.stringify(value) : String(value);
const short = (value, length = 12) => value ? String(value).slice(0, length) : "N/A";
const number = (value, digits = 1) => value === null || value === undefined
  ? "N/A" : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });

async function api(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

function kv(label, value, cls = "") {
  const node = document.createElement("div");
  node.className = `kv ${cls}`;
  node.append(text("span", label), text("strong", fmt(value)));
  return node;
}

function jsonBlock(value, empty = "N/A") {
  if (value === null || value === undefined || (Array.isArray(value) && !value.length)) {
    return text("p", empty, "muted");
  }
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

function overview(snapshot) {
  const scheduled = snapshot.campaigns.reduce((sum, campaign) => sum + campaign.run_count, 0);
  const completed = snapshot.campaigns.reduce((sum, campaign) => sum + campaign.completed_count, 0);
  const tokens = snapshot.campaigns.reduce((sum, campaign) => sum + (campaign.total_tokens || 0), 0);
  const stats = [
    ["Campaigns", snapshot.campaigns.length],
    ["Indexed runs", snapshot.runs.length],
    ["Scheduled", scheduled],
    ["Completed", completed],
    ["Accepted success", snapshot.runs.filter((run) => run.success && ["ok", "standalone"].includes(run.producer_status) && run.fairness_valid !== false).length],
    ["Tokens", tokens || null],
    ["Partial", snapshot.partial_file_count],
    ["Invalid", snapshot.invalid_file_count],
  ];
  el("overview").replaceChildren(...stats.map(([label, value]) => {
    const box = document.createElement("div");
    box.className = "stat";
    box.append(text("span", label, "muted"), text("strong", fmt(value)));
    return box;
  }));
}

function matrixTable(campaign) {
  const table = document.createElement("table");
  table.className = "matrix";
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["Cell", "Backend", "Done", "Success", "Valid", "Tokens", "LLM ms", "Retrieval ms", "E2E ms"].forEach((label) => headerRow.append(text("th", label)));
  head.append(headerRow);
  const body = document.createElement("tbody");
  campaign.matrix.forEach((cell) => {
    const row = document.createElement("tr");
    const success = cell.success_rate === null ? "N/A" : `${Math.round(cell.success_rate * 100)}%`;
    [
      cell.name,
      cell.backend,
      `${cell.completed}/${cell.scheduled}`,
      success,
      `${cell.valid_count}/${cell.completed}`,
      number(cell.total_tokens, 0),
      number(cell.mean_llm_latency_ms),
      number(cell.mean_retrieval_latency_ms),
      number(cell.mean_end_to_end_latency_ms),
    ].forEach((value) => row.append(text("td", value)));
    body.append(row);
  });
  table.append(head, body);
  return table;
}

function campaigns() {
  const root = el("campaigns");
  if (!state.snapshot.campaigns.length) {
    root.replaceChildren(text("p", "No campaign manifests found. Standalone run evidence remains available below.", "empty-inline"));
    return;
  }
  root.replaceChildren(...state.snapshot.campaigns.map((campaign) => {
    const card = document.createElement("article");
    card.className = `campaign-card${state.selectedCampaign === campaign.campaign_id ? " selected" : ""}`;
    const heading = document.createElement("button");
    heading.className = "campaign-heading";
    const title = document.createElement("div");
    title.append(text("p", `${campaign.mode || "unknown"} · ${campaign.status}`, `eyebrow ${campaign.status === "failed" ? "fail" : ""}`));
    title.append(text("h3", campaign.scenario || campaign.relative_path));
    title.append(text("small", `${campaign.semantics_version || "unversioned"} · ${campaign.campaign_id}`, "muted"));
    const progressText = document.createElement("div");
    progressText.className = "campaign-progress-text";
    progressText.append(text("strong", `${number(campaign.progress_percent)}%`), text("small", `${campaign.completed_count}/${campaign.run_count} complete`, "muted"));
    heading.append(title, progressText);
    heading.addEventListener("click", () => {
      state.selectedCampaign = state.selectedCampaign === campaign.campaign_id ? null : campaign.campaign_id;
      campaigns();
      runs();
    });
    const progress = document.createElement("div");
    progress.className = "progress";
    const bar = document.createElement("span");
    bar.style.width = `${Math.max(0, Math.min(100, campaign.progress_percent))}%`;
    progress.append(bar);
    const facts = document.createElement("div");
    facts.className = "campaign-facts";
    facts.append(
      kv("Commit", short(campaign.git_commit)),
      kv("Source", short(campaign.source_fingerprint)),
      kv("Started", campaign.created_at || null),
      kv("Remaining", campaign.remaining_count),
      kv("Errors", campaign.error_count),
      kv("ETA", campaign.eta_seconds === null ? "N/A" : `${number(campaign.eta_seconds)} s`),
      kv("Tokens", campaign.total_tokens),
      kv("Mean LLM", campaign.mean_llm_latency_ms === null ? null : `${number(campaign.mean_llm_latency_ms)} ms`),
    );
    const matrixWrap = document.createElement("div");
    matrixWrap.className = "matrix-wrap";
    matrixWrap.append(matrixTable(campaign));
    card.append(heading, progress, facts, matrixWrap);
    return card;
  }));
}

function scopedRuns() {
  const query = el("filter").value.toLowerCase();
  return state.snapshot.runs.filter((run) => {
    const inCampaign = !state.selectedCampaign || run.campaign_id === state.selectedCampaign;
    const searchable = `${run.scenario} ${run.memory_backend} ${run.seed} ${run.semantics_version} ${run.git_commit}`.toLowerCase();
    return inCampaign && searchable.includes(query);
  });
}

function runs() {
  const items = scopedRuns();
  const campaign = state.snapshot.campaigns.find((item) => item.campaign_id === state.selectedCampaign);
  el("run-scope").textContent = campaign ? `${campaign.scenario} · ${campaign.campaign_id}` : `${items.length} run(s) across all campaigns`;
  el("all-campaigns").classList.toggle("active", !state.selectedCampaign);
  el("runs").replaceChildren(...items.map((run) => {
    const button = document.createElement("button");
    button.className = `run${state.selected === run.run_id ? " selected" : ""}`;
    const top = document.createElement("div");
    top.className = "run-top";
    top.append(text("strong", run.scenario), text("span", run.success ? "SUCCESS" : "FAILURE", run.success ? "pass" : "fail"));
    button.append(
      top,
      text("small", `${run.memory_backend} · seed ${run.seed} · ${run.semantics_version || "unversioned"}`),
      text("small", `commit ${short(run.git_commit, 8)} · ${number(run.total_tokens, 0)} tokens`, "muted block"),
    );
    if (run.partial || run.stale) button.append(text("span", "partial / stale", "badge unknown"));
    if (run.fairness_valid === false) button.append(text("span", "fairness invalid", "badge fail"));
    if (!["ok", "standalone"].includes(run.producer_status)) button.append(text("span", `producer ${run.producer_status}`, "badge fail"));
    button.addEventListener("click", () => selectRun(run.run_id));
    return button;
  }));
}

function primaryLog(run) {
  if (run.run_log) return run.run_log;
  if (run.run_logs && run.run_logs.length) return run.run_logs[run.run_logs.length - 1].run_log;
  return null;
}

function facts(run) {
  const log = primaryLog(run);
  const fairness = run.fairness;
  const difficulty = Object.entries(run.params || {}).map(([key, value]) => `${key}=${fmt(value)}`).join(" · ");
  const runCard = state.snapshot.runs.find((card) => card.run_id === state.selected);
  const values = [
    ["Scenario", run.scenario], ["Backend", run.memory_backend], ["Seed", run.seed],
    ["Mode", run.campaign_mode], ["Task", run.success ? "SUCCESS" : "FAILURE"],
    ["Fairness", fairness ? fairness.valid : null], ["Commit", fairness ? short(fairness.git_commit) : null],
    ["Source fingerprint", fairness ? short(fairness.source_tree_fingerprint) : null],
    ["Model", log ? log.model : null], ["Temperature", log ? log.temperature : null],
    ["Producer status", runCard ? runCard.producer_status : "standalone"],
    ["Difficulty", difficulty || null],
  ];
  el("run-facts").replaceChildren(...values.map(([label, value]) => {
    const node = document.createElement("div");
    node.className = `fact${label === "Difficulty" ? " wide" : ""}`;
    node.append(text("span", label), text("strong", fmt(value)));
    return node;
  }));
}

function renderEvidence(run) {
  const log = primaryLog(run);
  const goal = document.createElement("div");
  goal.append(
    kv("Goal", log ? log.goal : null),
    kv("Primary evaluation", run.success ? "SUCCESS" : "FAILURE", run.success ? "pass" : "fail"),
    kv("Task-success metric", run.metrics ? run.metrics.task_success : null),
    kv("Evaluation evidence", "ScenarioResult.success + metrics + evaluation_ground_truth"),
  );
  el("goal-evaluation").replaceChildren(goal);
  el("memory-history").replaceChildren(jsonBlock(run.injected_events, "No offered long-term memory events recorded."));
  el("observed-actions").replaceChildren(jsonBlock(run.observed_action_results, "No scenario-observed source actions."));
  el("ground-truth").replaceChildren(jsonBlock(run.evaluation_ground_truth, "No typed evaluation ground truth."));
  el("fairness-detail").replaceChildren(jsonBlock(run.fairness, "No fairness record."));
}

function metricView(metrics) {
  el("metrics").replaceChildren(...Object.entries(metrics || {}).sort().map(([key, value]) => {
    const node = document.createElement("div");
    node.className = "metric";
    node.append(text("span", key), text("strong", fmt(value)));
    return node;
  }));
}

function costView(run) {
  const logs = run.run_logs && run.run_logs.length ? run.run_logs.map((entry) => entry.run_log) : (run.run_log ? [run.run_log] : []);
  const prompt = logs.length ? logs.reduce((sum, log) => sum + log.total_prompt_tokens, 0) : null;
  const completion = logs.length ? logs.reduce((sum, log) => sum + log.total_completion_tokens, 0) : null;
  const steps = logs.flatMap((log) => log.steps || []);
  const llmMs = logs.length ? steps.reduce((sum, step) => sum + step.latency_s * 1000, 0) : null;
  el("cost-summary").replaceChildren(
    kv("Prompt tokens", prompt), kv("Completion tokens", completion),
    kv("Total tokens", prompt === null ? null : prompt + completion),
    kv("LLM latency", llmMs === null ? null : `${number(llmMs)} ms`),
    kv("Retrieval latency", run.metrics ? run.metrics.avg_retrieve_latency_ms : null),
    kv("End-to-end latency", run.metrics ? run.metrics.end_to_end_latency_ms : null),
  );
}

function layer(title, value, cls) {
  const box = document.createElement("div");
  box.className = "layer";
  box.append(text("p", title, `eyebrow ${cls || ""}`), jsonBlock(value));
  return box;
}

function renderTimeline() {
  const timeline = state.replay?.timeline || [];
  el("timeline").replaceChildren(...timeline.map((event) => {
    const button = document.createElement("button");
    button.className = `timeline-event ${event.kind}${event.frame_sequence === state.frame ? " active" : ""}`;
    button.textContent = event.label;
    button.title = `${event.evidence_ref || "stored evidence"}${event.timestamp ? ` · ${event.timestamp}` : ""}`;
    button.disabled = event.frame_sequence === null;
    if (event.frame_sequence !== null) button.addEventListener("click", () => setFrame(event.frame_sequence));
    return button;
  }));
}

function renderFrame() {
  const frames = state.replay?.frames || [];
  if (!frames.length) {
    el("frame").replaceChildren(text("p", "No stored action frames.", "muted"));
    el("frame-counter").textContent = "0 / 0";
    el("seek").max = "0";
    return;
  }
  state.frame = Math.max(0, Math.min(state.frame, frames.length - 1));
  const frame = frames[state.frame];
  el("frame-counter").textContent = `${state.frame + 1} / ${frames.length} · ${frame.phase}${frame.session_id ? ` / ${frame.session_id}` : ""}`;
  el("seek").max = String(frames.length - 1);
  el("seek").value = String(state.frame);
  el("jump").value = String(state.frame);
  el("frame").replaceChildren(
    layer("R · MEMORY RETRIEVAL", frame.retrieval),
    layer(`U · UTILIZATION · ${frame.utilization.status.toUpperCase()}`, frame.utilization, frame.utilization.status === "supported" ? "pass" : "unknown"),
    layer("P · PLANNER DECISION", frame.planner),
    layer(`E · REAL ACTIONRESULT · ${frame.outcome.status.toUpperCase()}`, frame.outcome, frame.outcome.status === "failed" ? "fail" : "pass"),
    layer("WORLDSTATE / INVENTORY AT DECISION", frame.world_state),
    layer("SEMANTIC EVENTS", frame.semantic_events),
  );
  renderTimeline();
}

function trajectory() {
  const svg = el("trajectory");
  svg.replaceChildren();
  const points = state.replay?.trajectory || [];
  const markers = state.replay?.trajectory_markers || [];
  el("trajectory-note").textContent = state.replay?.trajectory_disclaimer || "No terrain is reconstructed.";
  const legendKinds = ["target", "entity", "action", "failure", "success"];
  el("trajectory-legend").replaceChildren(...legendKinds.map((kind) => text("span", kind, `legend-item ${kind}`)));
  if (!points.length && !markers.length) return;
  const all = [...points, ...markers];
  const xs = all.map((point) => point.x), zs = all.map((point) => point.z);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
  const sx = (x) => 38 + (x - minX) / (maxX - minX || 1) * 480;
  const sz = (z) => 320 - (z - minZ) / (maxZ - minZ || 1) * 275;
  const ns = "http://www.w3.org/2000/svg";
  if (points.length) {
    const poly = document.createElementNS(ns, "polyline");
    poly.setAttribute("points", points.map((point) => `${sx(point.x)},${sz(point.z)}`).join(" "));
    poly.setAttribute("fill", "none"); poly.setAttribute("stroke", "#63e6d3"); poly.setAttribute("stroke-width", "2");
    svg.append(poly);
  }
  markers.forEach((marker) => {
    const group = document.createElementNS(ns, "g");
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", sx(marker.x)); circle.setAttribute("cy", sz(marker.z));
    circle.setAttribute("r", marker.frame_sequence === state.frame ? "7" : marker.kind === "entity" ? "3" : "5");
    circle.setAttribute("class", `marker ${marker.kind}`);
    const titleNode = document.createElementNS(ns, "title");
    titleNode.textContent = `${marker.kind}: ${marker.label} (${marker.x}, ${marker.z})`;
    group.append(circle, titleNode);
    if (["target", "failure", "success"].includes(marker.kind)) {
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", sx(marker.x) + 8); label.setAttribute("y", sz(marker.z) - 7);
      label.textContent = marker.label.slice(0, 28); group.append(label);
    }
    svg.append(group);
  });
}

function configureJump() {
  const frames = state.replay?.frames || [];
  el("jump").replaceChildren(...frames.map((frame, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${index + 1} · ${frame.phase} · ${frame.planner.action} → ${frame.outcome.status}`;
    return option;
  }));
}

function setFrame(value) {
  state.frame = Number(value);
  renderFrame();
  trajectory();
}

async function selectRun(runId) {
  state.selected = runId;
  runs();
  stopPlay();
  const [detail, replay] = await Promise.all([
    api(`/api/runs/${runId}`),
    api(`/api/replay/${runId}`),
  ]);
  state.detail = detail.result;
  state.replay = replay;
  state.frame = 0;
  el("empty").hidden = true;
  el("detail").hidden = false;
  el("detail-kicker").textContent = `${state.detail.memory_backend} · SEED ${state.detail.seed} · ${state.detail.campaign_mode}`;
  el("detail-name").textContent = state.detail.scenario;
  facts(state.detail);
  renderEvidence(state.detail);
  metricView(state.detail.metrics);
  costView(state.detail);
  configureJump();
  renderFrame();
  trajectory();
  setTab("evidence");
}

function stopPlay() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  el("play").textContent = "Play";
}

function togglePlay() {
  if (state.timer) { stopPlay(); return; }
  const speed = Number(el("speed").value) || 1;
  el("play").textContent = "Pause";
  state.timer = setInterval(() => {
    if (!state.replay || state.frame >= state.replay.frames.length - 1) { stopPlay(); return; }
    setFrame(state.frame + 1);
  }, 900 / speed);
}

function topKList(items) {
  const list = document.createElement("ol");
  list.className = "top-k";
  if (!items.length) return text("p", "No retrieved items", "muted");
  items.forEach((item) => {
    const event = item.event || {};
    list.append(text("li", `${event.event_type || "event"} · ${event.target || event.actor || "N/A"} · score ${fmt(item.score)}`));
  });
  return list;
}

async function compare() {
  if (!state.selected) return;
  const data = await api(`/api/compare?anchor=${encodeURIComponent(state.selected)}`);
  const root = document.createElement("div");
  root.append(text("h3", `Fairness verdict: ${data.verdict.toUpperCase()}`, data.verdict));
  root.append(text("p", `${data.scenario} · seed ${data.seed} · identical difficulty ${JSON.stringify(data.params)}`, "muted"));
  const grid = document.createElement("div");
  grid.className = "compare-grid";
  data.cells.forEach((cell) => {
    const box = document.createElement("article");
    box.className = "compare-cell";
    box.append(text("p", cell.backend.toUpperCase(), "eyebrow"), text("h3", cell.status));
    if (cell.status === "present") {
      box.append(
        kv("Task success", cell.success, cell.success ? "pass" : "fail"),
        kv("Fairness", cell.fairness_valid),
        kv("First action", cell.first_action),
        text("p", "Retrieved top-k", "mini-title"), topKList(cell.retrieved_top_k),
        kv("Preparation", cell.preparation),
        kv("Failure repeated", cell.failure_repetition),
        kv("Steps", cell.steps),
        kv("Tokens", cell.total_tokens),
        kv("LLM latency ms", cell.llm_latency_ms),
        kv("Retrieval latency ms", cell.retrieval_latency_ms),
        kv("E2E latency ms", cell.end_to_end_latency_ms),
        text("p", "Side-by-side replay timeline", "mini-title"),
      );
      const timeline = document.createElement("div");
      timeline.className = "mini-timeline";
      (cell.replay_frames || []).forEach((frame) => timeline.append(text("div", `${frame.sequence + 1}. R${frame.retrieved} → ${frame.action} → ${frame.status}${frame.error ? ` · ${frame.error}` : ""}`)));
      box.append(timeline);
      if (cell.run_ids.length === 1) {
        const open = text("button", "Open this run", "compact");
        open.addEventListener("click", () => selectRun(cell.run_ids[0]));
        box.append(open);
      }
    }
    grid.append(box);
  });
  root.append(grid, text("h3", "Controlled-variable audit"));
  data.fairness_fields.forEach((field) => {
    const row = document.createElement("div");
    row.className = "fairness-row";
    row.append(text("strong", field.field), text("span", field.status.toUpperCase(), field.status), text("code", JSON.stringify(field.values)));
    root.append(row);
  });
  el("compare").replaceChildren(root);
  setTab("compare");
}

function setTab(name) {
  document.querySelectorAll(".tab").forEach((node) => node.classList.toggle("active", node.dataset.tab === name));
  document.querySelectorAll(".tab-body").forEach((node) => { node.hidden = node.id !== `tab-${name}`; });
}

async function refresh() {
  try {
    const snapshot = await api("/api/snapshot");
    state.snapshot = snapshot;
    if (state.selectedCampaign && !snapshot.campaigns.some((item) => item.campaign_id === state.selectedCampaign)) state.selectedCampaign = null;
    overview(snapshot); campaigns(); runs();
    el("live-dot").className = "ok";
    const running = snapshot.campaigns.filter((campaign) => campaign.status === "running").length;
    el("live-text").textContent = snapshot.partial_file_count ? `Live · ${snapshot.partial_file_count} partial` : running ? `Live · ${running} running` : "Live";
  } catch {
    el("live-dot").className = "";
    el("live-text").textContent = "Disconnected";
  }
}

el("filter").addEventListener("input", runs);
el("all-campaigns").addEventListener("click", () => { state.selectedCampaign = null; campaigns(); runs(); });
el("compare-button").addEventListener("click", compare);
document.querySelectorAll(".tab").forEach((node) => node.addEventListener("click", () => setTab(node.dataset.tab)));
el("first").addEventListener("click", () => setFrame(0));
el("prev").addEventListener("click", () => setFrame(state.frame - 1));
el("next").addEventListener("click", () => setFrame(state.frame + 1));
el("last").addEventListener("click", () => setFrame((state.replay?.frames.length || 1) - 1));
el("play").addEventListener("click", togglePlay);
el("speed").addEventListener("change", () => { if (state.timer) { stopPlay(); togglePlay(); } });
el("seek").addEventListener("input", (event) => setFrame(event.target.value));
el("jump").addEventListener("change", (event) => setFrame(event.target.value));

refresh();
const events = new EventSource("/api/events");
events.addEventListener("revision", refresh);
events.onerror = () => { el("live-text").textContent = "Reconnecting"; };
