/**
 * AegisIoT Enterprise - Frontend App Script
 *
 * Coordinates real-time WebSocket messaging, renders high-performance Canvas charts,
 * communicates with FastAPI REST endpoints, and manages the typewriter multi-agent log console.
 */
document.addEventListener("DOMContentLoaded", () => {
  // ----------------------------------------------------
  // 1. DATA HISTORIES & GLOBAL STATES
  // ----------------------------------------------------
  const MAX_DATA_POINTS = 45;
  const telemetryHistory = {
    temperature: [],
    vibration: [],
    pressure: [],
    flowRate: [],
  };
  let activeAlertState = "NORMAL";
  let agentQueue = [];
  let isTyping = false;
  let loggedMessagesCount = 0;
  // ----------------------------------------------------
  // 2. DOM ELEMENT SELECTORS
  // ----------------------------------------------------
  const dom = {
    // Navigation Tabs
    tabs: document.querySelectorAll(".nav-tab-btn"),
    panels: document.querySelectorAll(".app-tab-panel"),

    // Status beacons
    statusDot: document.querySelector(
      "#global-status-beacon .status-indicator-dot",
    ),
    statusText: document.getElementById("global-status-text"),

    // REST Injector Controls
    btnNormal: document.getElementById("btn-inject-normal"),
    btnBearing: document.getElementById("btn-inject-bearing"),
    btnCoolant: document.getElementById("btn-inject-coolant"),
    btnBlockage: document.getElementById("btn-inject-blockage"),

    // Sensor Counters
    kpiTemp: document.getElementById("kpi-val-temp"),
    kpiVib: document.getElementById("kpi-val-vib"),
    kpiPres: document.getElementById("kpi-val-pres"),
    kpiFlow: document.getElementById("kpi-val-flow"),
    // Z-Score Displays
    zTemp: document.getElementById("kpi-z-temp"),
    zVib: document.getElementById("kpi-z-vib"),
    zPres: document.getElementById("kpi-z-pres"),
    zFlow: document.getElementById("kpi-z-flow"),
    // Card Boxes (for alarm coloring glows)
    cardTemp: document.getElementById("card-sensor-temp"),
    cardVib: document.getElementById("card-sensor-vib"),
    cardPres: document.getElementById("card-sensor-pres"),
    cardFlow: document.getElementById("card-sensor-flow"),
    // Asset Health RUL
    barBearing: document.getElementById("health-bearing-bar"),
    txtBearing: document.getElementById("health-bearing-text"),
    barCoolant: document.getElementById("health-coolant-bar"),
    txtCoolant: document.getElementById("health-coolant-text"),
    barPiping: document.getElementById("health-piping-bar"),
    txtPiping: document.getElementById("health-piping-text"),
    // Agent windows
    logsWindow: document.getElementById("console-logs-window"),
    reportWindow: document.getElementById("report-content-window"),
    reportBadge: document.getElementById("report-badge-severity"),
    // AI Advisor
    recommendation: document.getElementById("recommendation"),
    advisorSeverity: document.getElementById("advisor-severity"),
    ticketBtn: document.getElementById("ticket-btn"),
    ticketOutput: document.getElementById("ticket-output"),
    // Dataset Export
    btnDownload: document.getElementById("btn-download-dataset"),
    exportStatus: document.getElementById("export-status-txt"),
  };
  // ----------------------------------------------------
  // 3. NAVIGATION TAB SYSTEM
  // ----------------------------------------------------
  dom.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      dom.tabs.forEach((t) => t.classList.remove("active"));
      dom.panels.forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      const targetPanel = document.getElementById(tab.getAttribute("data-tab"));
      targetPanel.classList.add("active");
      if (tab.getAttribute("data-tab") === "tab-dashboard") {
        renderAllCharts();
      }
    });
  });
  // ----------------------------------------------------
  // 4. REST API: FAULT INJECTIONS
  // ----------------------------------------------------
  async function injectFaultToServer(mode) {
    try {
      const response = await fetch("/api/inject-fault", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fault_type: mode }),
      });
      const data = await response.json();
      console.log(`[API] Injected fault success:`, data);

      // Toggle active classes immediately on frontend buttons
      clearControlActiveStates();
      if (mode === "NORMAL") dom.btnNormal.classList.add("active");
      else if (mode === "BEARING_WEAR") dom.btnBearing.classList.add("active");
      else if (mode === "COOLANT_LEAK") dom.btnCoolant.classList.add("active");
      else if (mode === "PIPE_BLOCKAGE")
        dom.btnBlockage.classList.add("active");
    } catch (error) {
      console.error("[API] Error injecting fault:", error);
    }
  }
  function clearControlActiveStates() {
    [dom.btnNormal, dom.btnBearing, dom.btnCoolant, dom.btnBlockage].forEach(
      (btn) => {
        btn.classList.remove("active");
      },
    );
  }
  dom.btnNormal.addEventListener("click", () => injectFaultToServer("NORMAL"));
  dom.btnBearing.addEventListener("click", () =>
    injectFaultToServer("BEARING_WEAR"),
  );
  dom.btnCoolant.addEventListener("click", () =>
    injectFaultToServer("COOLANT_LEAK"),
  );
  dom.btnBlockage.addEventListener("click", () =>
    injectFaultToServer("PIPE_BLOCKAGE"),
  );
  // ----------------------------------------------------
  // 5. HIGH-PERFORMANCE CANVAS CHARTING RENDERER
  // ----------------------------------------------------
  function drawSparkline(canvasId, data, glowColor, strokeColor) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    // Fix: Set internal pixel resolution to match displayed CSS size
    canvas.width = canvas.offsetWidth || 400;
    canvas.height = canvas.offsetHeight || 140;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(4, 6, 11, 0.4)";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.03)";
    ctx.lineWidth = 1;
    for (let y = height / 4; y < height; y += height / 4) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    if (data.length < 2) return;
    let min = Math.min(...data);
    let max = Math.max(...data);
    const buffer = (max - min) * 0.15 || 1.0;
    max += buffer;
    min -= buffer;
    const coords = [];
    const paddingLeftRight = 10;
    const stepX = (width - paddingLeftRight * 2) / (MAX_DATA_POINTS - 1);
    for (let i = 0; i < data.length; i++) {
      const x =
        paddingLeftRight + i * stepX + (MAX_DATA_POINTS - data.length) * stepX;
      const y = height - ((data[i] - min) / (max - min)) * height;
      coords.push({ x, y });
    }
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, glowColor);
    gradient.addColorStop(1, "rgba(0, 0, 0, 0.0)");

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(coords[0].x, height);
    coords.forEach((pt) => ctx.lineTo(pt.x, pt.y));
    ctx.lineTo(coords[coords.length - 1].x, height);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2;
    ctx.shadowBlur = 4;
    ctx.shadowColor = strokeColor;
    ctx.beginPath();
    ctx.moveTo(coords[0].x, coords[0].y);
    for (let i = 1; i < coords.length; i++) {
      const xc = (coords[i].x + coords[i - 1].x) / 2;
      const yc = (coords[i].y + coords[i - 1].y) / 2;
      ctx.quadraticCurveTo(coords[i - 1].x, coords[i - 1].y, xc, yc);
    }
    ctx.lineTo(coords[coords.length - 1].x, coords[coords.length - 1].y);
    ctx.stroke();
    ctx.shadowBlur = 0;
    const latest = coords[coords.length - 1];
    ctx.fillStyle = strokeColor;
    ctx.beginPath();
    ctx.arc(latest.x, latest.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    const scale = 4 + Math.sin(Date.now() / 150) * 3;
    ctx.arc(latest.x, latest.y, scale, 0, Math.PI * 2);
    ctx.stroke();
  }
  function renderAllCharts() {
    if (!document.getElementById("tab-dashboard").classList.contains("active"))
      return;
    let themeColor = "rgba(56, 189, 248, 1)";
    let glowColor = "rgba(56, 189, 248, 0.1)";
    if (activeAlertState === "BEARING_WEAR") {
      themeColor = "#f59e0b";
      glowColor = "rgba(245, 158, 11, 0.12)";
    } else if (activeAlertState !== "NORMAL") {
      themeColor = "#ef4444";
      glowColor = "rgba(239, 68, 68, 0.12)";
    }
    drawSparkline(
      "chart-temp",
      telemetryHistory.temperature,
      glowColor,
      themeColor,
    );
    drawSparkline(
      "chart-vib",
      telemetryHistory.vibration,
      glowColor,
      themeColor,
    );
    drawSparkline(
      "chart-pres",
      telemetryHistory.pressure,
      glowColor,
      themeColor,
    );
    drawSparkline(
      "chart-flow",
      telemetryHistory.flowRate,
      glowColor,
      themeColor,
    );
  }
  // ----------------------------------------------------
  // 6. MULTI-AGENT TYPEWRITER CONSOLE & DIAGNOSTICS
  // ----------------------------------------------------
  function appendTerminalLog(agent, msg) {
    if (loggedMessagesCount === 0) {
      dom.logsWindow.innerHTML = "";
    }
    loggedMessagesCount++;
    const timeStr = new Date().toLocaleTimeString();
    const block = document.createElement("div");
    block.className = "agent-log-block";
    let nameClass = "agent-name-system";
    let agentTitle = "System Monitor";
    if (agent === "TRIAGE") {
      nameClass = "agent-name-triage";
      agentTitle = "🤖 L1 Triage Agent";
    } else if (agent === "DIAGNOSTIC") {
      nameClass = "agent-name-diagnostic";
      agentTitle = "🧠 L2 Diagnostic LLM Agent";
    } else if (agent === "DISPATCHER") {
      nameClass = "agent-name-dispatcher";
      agentTitle = "🚨 L3 Dispatcher Agent";
    }
    block.innerHTML = `
            <div class="agent-log-header">
                <span class="${nameClass}">${agentTitle}</span>
                <span class="agent-log-time">[${timeStr}]</span>
            </div>
            <div class="agent-log-msg"></div>
        `;
    dom.logsWindow.appendChild(block);
    dom.logsWindow.scrollTop = dom.logsWindow.scrollHeight;
  }
  function processAgentQueue() {
    if (agentQueue.length === 0) {
      isTyping = false;
      return;
    }
    isTyping = true;
    const currentItem = agentQueue.shift();

    let typedText = "";
    let charIndex = 0;

    appendTerminalLog(currentItem.agent, "");
    const logs = dom.logsWindow.querySelectorAll(".agent-log-msg");
    const activeContainer = logs[logs.length - 1];
    const typingSpeed = 15;

    function typeChar() {
      if (charIndex < currentItem.message.length) {
        typedText += currentItem.message.charAt(charIndex);
        activeContainer.innerHTML = typedText;
        charIndex++;
        setTimeout(typeChar, typingSpeed);
      } else {
        setTimeout(processAgentQueue, 800);
      }
    }
    typeChar();
  }
  function enqueueAgentConverse(agent, message) {
    agentQueue.push({ agent, message });
    if (!isTyping) {
      processAgentQueue();
    }
  }
  async function triggerAgentEscalation(faultType, readings) {
    agentQueue = [];

    if (faultType === "NORMAL") {
      enqueueAgentConverse(
        "TRIAGE",
        "Normalizing operation. Raw sensor streams stabilized within baseline thresholds. System health restored.",
      );
      return;
    }
    // Standard Alert Pipeline Escalations
    enqueueAgentConverse(
      "TRIAGE",
      `⚠️ EDGE ANOMALY BREACH! Python statistical Z-Score exceeded critical threshold index! Ingesting WebSocket packets...`,
    );

    setTimeout(() => {
      enqueueAgentConverse(
        "TRIAGE",
        `Analysis confirmed: The Z-Score deviation is sustained over a 15-tick rolling index. Unsupervised scikit-learn Isolation Forest ML confirms multi-variable anomaly. Routing system parameters to L2 Diagnostic Agent.`,
      );
    }, 1200);
    setTimeout(() => {
      enqueueAgentConverse(
        "DIAGNOSTIC",
        `Received raw sensor package. Current Readings: Temp ${readings.temperature}°C, Vib ${readings.vibration}mm/s, Pres ${readings.pressure}bar, Flow ${readings.flowRate}L/min.`,
      );
      enqueueAgentConverse(
        "DIAGNOSTIC",
        `Running vector search through active blueprints and historical failure logs... Found 96% match. Preparing diagnostic summary and maintenance checklist.`,
      );
    }, 3000);
    setTimeout(() => {
      enqueueAgentConverse(
        "DISPATCHER",
        `🚨 EMERGENCY WARNING! Diagnostic payload compiled.`,
      );
      enqueueAgentConverse(
        "DISPATCHER",
        `Creating Maintenance Order #WO-${Math.floor(1000 + Math.random() * 9000)}. Alert notifications dispatched to engineering staff and secondary PLC safety overrides.`,
      );
    }, 6000);
  }
  /**
   * Queries /api/diagnose REST endpoint to retrieve real-time ML score and tailored diagnostic reports
   */
  async function fetchDiagnosticsAndRender(faultMode, readings) {
    try {
      const response = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          temperature: readings.temperature,
          vibration: readings.vibration,
          pressure: readings.pressure,
          flowRate: readings.flowRate,
        }),
      });
      const data = await response.json();
      renderDiagnosticReport(faultMode, data.recommendation);
    } catch (error) {
      console.error("[API] Error calling diagnose:", error);
    }
  }
  function renderDiagnosticReport(faultMode, rec) {
    // Update the advisor severity badge in the header
    dom.advisorSeverity.textContent = rec.severity;
    dom.advisorSeverity.className = "advisor-badge";
    
    // Map severity to badge class
    const severityMap = {
      "NOMINAL": "normal",
      "WARNING": "warning",
      "HIGH": "high",
      "CRITICAL": "critical"
    };
    
    const badgeClass = severityMap[rec.severity] || "normal";
    dom.advisorSeverity.classList.add(badgeClass);

    // Handle normal state
    if (faultMode === "NORMAL") {
      dom.recommendation.innerHTML = `
        <div class="advisor-empty-state">
          <div class="empty-icon">✓</div>
          <p>All systems operating normally. No anomalies detected.</p>
        </div>
      `;
      return;
    }

    // Build action items as checkboxes
    const actionItems = rec.actions
      .map((act, idx) => `
        <li class="action-item">
          <input type="checkbox" class="action-checkbox" id="action-${idx}" />
          <label for="action-${idx}" class="action-text">${act}</label>
        </li>
      `)
      .join("");

    // Determine section colors based on severity
    const getStatusBadgeClass = (sev) => {
      if (sev === "NOMINAL") return "normal";
      if (sev === "WARNING") return "warning";
      if (sev === "HIGH") return "high";
      return "critical";
    };

    const badgeStatus = getStatusBadgeClass(rec.severity);

    // Render the new card design with all sections
    dom.recommendation.innerHTML = `
      <!-- Status Section -->
      <div class="advisor-section status-section">
        <div class="section-header">
          <span class="section-icon">📊</span>
          <span>Status</span>
        </div>
        <span class="status-badge ${badgeStatus}">${rec.severity}</span>
      </div>

      <!-- Detected Issue Section -->
      <div class="advisor-section issue-section">
        <div class="section-header">
          <span class="section-icon">⚠️</span>
          <span>Detected Issue</span>
        </div>
        <div class="issue-title">${rec.category}</div>
        <div class="issue-description">${rec.summary}</div>
      </div>

      <!-- Likely Cause Section -->
      <div class="advisor-section cause-section">
        <div class="section-header">
          <span class="section-icon">🔍</span>
          <span>Likely Cause</span>
        </div>
        <div class="cause-text">${rec.rootCause || 'Analyzing sensor deviation patterns...'}</div>
        ${rec.affectedSensors ? `
          <div class="cause-details">
            <strong>Affected Sensors:</strong><br/>
            ${rec.affectedSensors.join(', ')}
          </div>
        ` : ''}
      </div>

      <!-- Recommended Actions Section -->
      <div class="advisor-section actions-section">
        <div class="section-header">
          <span class="section-icon">✅</span>
          <span>Recommended Actions</span>
        </div>
        <ul class="actions-list">
          ${actionItems || '<li class="action-item"><span class="action-text">No actions required at this time</span></li>'}
        </ul>
      </div>

      <!-- Priority Section -->
      <div class="advisor-section priority-section">
        <div class="section-header">
          <span class="section-icon">🚨</span>
          <span>Priority</span>
        </div>
        <span class="priority-level ${badgeStatus}">${rec.severity}</span>
        ${rec.estimatedResolution ? `
          <div style="font-size: 0.85rem; color: var(--muted); margin-top: 8px;">
            Estimated resolution time: <strong>${rec.estimatedResolution}</strong>
          </div>
        ` : ''}
      </div>

      <!-- Source Section -->
      <div class="advisor-section">
        <div class="section-header">
          <span class="section-icon">🔗</span>
          <span>Source</span>
        </div>
        <span class="source-badge">${rec.source || 'AI Maintenance Advisor v1.0'}</span>
        ${rec.confidence ? `
          <div style="font-size: 0.85rem; color: var(--muted); margin-top: 8px;">
            Confidence: <strong>${rec.confidence}</strong>
          </div>
        ` : ''}
      </div>

      <!-- Last Updated Section -->
      <div class="advisor-section">
        <div class="section-header">
          <span class="section-icon">🕐</span>
          <span>Last Updated</span>
        </div>
        <div class="updated-text">
          <span class="updated-timestamp">${rec.generatedAt || new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    `;

    // Add event listeners to action checkboxes
    setTimeout(() => {
      const checkboxes = dom.recommendation.querySelectorAll('.action-checkbox');
      checkboxes.forEach((checkbox) => {
        checkbox.addEventListener('change', function() {
          const actionItem = this.closest('.action-item');
          if (this.checked) {
            actionItem.classList.add('completed');
          } else {
            actionItem.classList.remove('completed');
          }
        });
      });
    }, 0);
  }
  // ----------------------------------------------------
  // 7. WEBSOCKET streaming LISTENERS
  // ----------------------------------------------------
  function initWebSocketConnection() {
    // Construct standard WebSocket URL based on current browser domain
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const wsUrl = `${wsProtocol}//${window.location.host}/ws/stream`;

    console.log(`[WS] Connecting to WebSocket stream at ${wsUrl}`);
    const socket = new WebSocket(wsUrl);
    socket.onopen = () => {
      console.log("[WS] WebSocket connection established successfully.");
      // Send standard handshake ping
      socket.send(JSON.stringify({ type: "ping" }));
    };
    socket.onmessage = (event) => {
      // Fix: Parse JSON first before referencing data
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.error("[WS] Failed to parse message:", e);
        return;
      }

      // Skip non-telemetry packets
      if (data.type !== "telemetry") return;
      const payload = data.payload;
      const readings = payload.readings;
      const analytics = payload.analytics;
      const health = payload.health;
      // Ingest telemetry values into local buffers for Canvas lines
      telemetryHistory.temperature.push(readings.temperature);
      telemetryHistory.vibration.push(readings.vibration);
      telemetryHistory.pressure.push(readings.pressure);
      telemetryHistory.flowRate.push(readings.flowRate);
      // Cap rolling window size
      Object.keys(telemetryHistory).forEach((key) => {
        if (telemetryHistory[key].length > MAX_DATA_POINTS) {
          telemetryHistory[key].shift();
        }
      });
      // Update live numeric counters
      dom.kpiTemp.textContent = readings.temperature.toFixed(1);
      dom.kpiVib.textContent = readings.vibration.toFixed(3);
      dom.kpiPres.textContent = readings.pressure.toFixed(1);
      dom.kpiFlow.textContent = readings.flowRate.toFixed(0);
      // Update Z-Scores displays
      const z = analytics.z_scores;
      dom.zTemp.textContent = `Z-Score: ${z.temperature >= 0 ? "+" : ""}${z.temperature}`;
      dom.zVib.textContent = `Z-Score: ${z.vibration >= 0 ? "+" : ""}${z.vibration}`;
      dom.zPres.textContent = `Z-Score: ${z.pressure >= 0 ? "+" : ""}${z.pressure}`;
      dom.zFlow.textContent = `Z-Score: ${z.flowRate >= 0 ? "+" : ""}${z.flowRate}`;
      // Remove warning glow classes
      [dom.cardTemp, dom.cardVib, dom.cardPres, dom.cardFlow].forEach(
        (c) => (c.className = "glass-card kpi-card"),
      );
      // Apply glows based on server-side statistical thresholds
      const alarms = analytics.alarms;
      if (alarms.temperature) dom.cardTemp.classList.add("critical-glow");
      else if (Math.abs(z.temperature) > 1.8)
        dom.cardTemp.classList.add("warning-glow");
      if (alarms.vibration) dom.cardVib.classList.add("critical-glow");
      else if (Math.abs(z.vibration) > 1.8)
        dom.cardVib.classList.add("warning-glow");
      if (alarms.pressure) dom.cardPres.classList.add("critical-glow");
      else if (Math.abs(z.pressure) > 1.8)
        dom.cardPres.classList.add("warning-glow");
      if (alarms.flowRate) dom.cardFlow.classList.add("critical-glow");
      else if (Math.abs(z.flowRate) > 1.8)
        dom.cardFlow.classList.add("warning-glow");
      // Handle Global Failure Mode States Shift triggers
      if (payload.status !== activeAlertState) {
        activeAlertState = payload.status;
        // Sync global status beacon styles
        dom.statusDot.className = "status-indicator-dot";
        if (activeAlertState === "NORMAL") {
          dom.statusDot.classList.add("normal");
          dom.statusText.textContent = "SYSTEM OPERATIONAL";
        } else if (activeAlertState === "BEARING_WEAR") {
          dom.statusDot.classList.add("warning");
          dom.statusText.textContent = "SHAFT BEARING DEGRADED";
        } else {
          dom.statusDot.classList.add("critical");
          dom.statusText.textContent = "CRITICAL MACHINE ALERT";
        }
        // Sync frontend fault injection button configurations
        clearControlActiveStates();
        if (activeAlertState === "NORMAL")
          dom.btnNormal.classList.add("active");
        else if (activeAlertState === "BEARING_WEAR")
          dom.btnBearing.classList.add("active");
        else if (activeAlertState === "COOLANT_LEAK")
          dom.btnCoolant.classList.add("active");
        else if (activeAlertState === "PIPE_BLOCKAGE")
          dom.btnBlockage.classList.add("active");
        // Trigger multi-agent logs
        triggerAgentEscalation(activeAlertState, readings);
      }
      // Redraw sparklines
      renderAllCharts();
      // Sync predictive RUL health progress indicators
      const updateBar = (bar, txt, val) => {
        bar.style.width = `${val}%`;
        bar.className = "progress-bar-fill";
        if (val > 70) {
          bar.classList.add("normal");
          txt.textContent = `${val.toFixed(0)}% RUL (Healthy)`;
        } else if (val > 40) {
          bar.classList.add("warning");
          txt.textContent = `${val.toFixed(0)}% RUL (Maintenance Due)`;
        } else {
          bar.classList.add("critical");
          txt.textContent = `${val.toFixed(0)}% RUL (CRITICAL OUTAGE)`;
        }
      };
      updateBar(dom.barBearing, dom.txtBearing, health.bearing);
      updateBar(dom.barCoolant, dom.txtCoolant, health.coolant);
      updateBar(dom.barPiping, dom.txtPiping, health.piping);
      // Fetch live LLM diagnostics and update report
      fetchDiagnosticsAndRender(activeAlertState, readings);
    };
    socket.onclose = () => {
      console.log(
        "[WS] WebSocket connection closed. Reconnecting in 3 seconds...",
      );
      setTimeout(initWebSocketConnection, 3000);
    };
    socket.onerror = (error) => {
      console.error("[WS] WebSocket Error: ", error);
      socket.close();
    };
  }
  // Initialize WebSockets
  initWebSocketConnection();
  // ----------------------------------------------------
  // 8. MAINTENANCE TICKET GENERATION
  // ----------------------------------------------------
  dom.ticketBtn.addEventListener("click", () => {
    if (activeAlertState === "NORMAL") {
      dom.ticketOutput.innerHTML = `
        <div class="ticket-card">
          <p style="color: var(--muted);">No ticket needed - system is operating normally.</p>
        </div>
      `;
      return;
    }

    const ticketId = `WO-${Math.floor(1000 + Math.random() * 9000)}`;
    const timestamp = new Date().toLocaleString();
    const statusMap = {
      "BEARING_WEAR": "Bearing Degradation",
      "COOLANT_LEAK": "Coolant System Failure",
      "PIPE_BLOCKAGE": "Fluid Flow Obstruction"
    };

    const ticketStatus = statusMap[activeAlertState] || "System Alert";

    dom.ticketOutput.innerHTML = `
      <div class="ticket-card">
        <div class="ticket-row">
          <span>Ticket ID:</span>
          <strong>${ticketId}</strong>
        </div>
        <div class="ticket-row">
          <span>Status:</span>
          <strong>${ticketStatus}</strong>
        </div>
        <div class="ticket-row">
          <span>Priority:</span>
          <strong>High</strong>
        </div>
        <div class="ticket-row">
          <span>Created:</span>
          <strong>${timestamp}</strong>
        </div>
      </div>
    `;
  });
  // ----------------------------------------------------
  // 9. DATASET EXPORT UTILITY
  // ----------------------------------------------------
  dom.btnDownload.addEventListener("click", () => {
    dom.exportStatus.textContent =
      "⚡ Influx compiling data... Preparing download package...";
    dom.exportStatus.style.color = "var(--text-accent)";
    setTimeout(() => {
      // Trigger direct HTTP endpoint routing to compile and download dataset
      window.location.href = "/api/export-dataset";

      dom.exportStatus.textContent = "✓ Dataset export completed successfully!";
      dom.exportStatus.style.color = "var(--state-normal)";
    }, 1200);
  });
});
