const initReportTableSorting = () => {
  const normalizeSortValue = (rawValue) => {
    const value = (rawValue ?? "").toString().trim();
    if (!value) {
      return { type: "empty", value: "" };
    }

    if (/^\d{2}-\d{2}-\d{4}$/.test(value)) {
      const [day, month, year] = value.split("-");
      return { type: "date", value: `${year}-${month}-${day}` };
    }

    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return { type: "date", value };
    }

    if (/^\d{1,2}:\d{2}$/.test(value)) {
      const [hours, minutes] = value.split(":");
      return { type: "time", value: `${hours.padStart(2, "0")}:${minutes}` };
    }

    const numericCandidate = value.replace(/\./g, "").replace(",", ".").replace("%", "");
    if (/^-?\d+(\.\d+)?$/.test(numericCandidate)) {
      return { type: "number", value: Number.parseFloat(numericCandidate) };
    }

    return { type: "text", value: value.toLowerCase() };
  };

  const compareSortValues = (leftRaw, rightRaw, direction) => {
    const left = normalizeSortValue(leftRaw);
    const right = normalizeSortValue(rightRaw);

    if (left.type === "empty" && right.type !== "empty") {
      return direction === "asc" ? -1 : 1;
    }
    if (left.type !== "empty" && right.type === "empty") {
      return direction === "asc" ? 1 : -1;
    }

    if (left.value < right.value) {
      return direction === "asc" ? -1 : 1;
    }
    if (left.value > right.value) {
      return direction === "asc" ? 1 : -1;
    }
    return 0;
  };

  document.querySelectorAll("table.report-table, table.sortable-table").forEach((table) => {
    if (table.dataset.sortInitialized === "true") {
      return;
    }

    const headRow = table.querySelector("thead tr");
    const body = table.querySelector("tbody");
    if (!headRow || !body) {
      return;
    }

    table.dataset.sortInitialized = "true";

    const headers = Array.from(headRow.querySelectorAll("th"));
    const sortState = [];

    const cleanHeaderLabel = (header) => header.textContent.replace(/\s*[▲▼]$/, "").trim();

    const renderIndicators = () => {
      headers.forEach((header, index) => {
        const active = sortState.find((item) => item.index === index);
        const label = cleanHeaderLabel(header);
        header.textContent = active ? `${label} ${active.direction === "asc" ? "▲" : "▼"}` : label;
      });
    };

    const sortTable = () => {
      if (!sortState.length) {
        return;
      }

      const rows = Array.from(body.querySelectorAll("tr"))
        .filter((row) => row.querySelectorAll("td").length)
        .map((row, position) => ({ row, position }));

      rows.sort((left, right) => {
        for (const rule of sortState) {
          const leftCell = left.row.children[rule.index];
          const rightCell = right.row.children[rule.index];
          const leftValue = leftCell?.dataset.sortValue ?? leftCell?.textContent ?? "";
          const rightValue = rightCell?.dataset.sortValue ?? rightCell?.textContent ?? "";
          const comparison = compareSortValues(leftValue, rightValue, rule.direction);
          if (comparison !== 0) {
            return comparison;
          }
        }
        return left.position - right.position;
      });

      rows.forEach(({ row }) => body.appendChild(row));
    };

    headers.forEach((header, index) => {
      header.style.cursor = "pointer";
      header.title = "Klik om te sorteren, Shift+klik voor extra sortering";
      header.addEventListener("click", (event) => {
        const existing = sortState.find((item) => item.index === index);

        if (!event.shiftKey) {
          sortState.length = 0;
        } else {
          for (let i = sortState.length - 1; i >= 0; i -= 1) {
            if (sortState[i].index === index) {
              sortState.splice(i, 1);
            }
          }
        }

        sortState.push({
          index,
          direction: existing?.direction === "asc" ? "desc" : "asc",
        });

        renderIndicators();
        sortTable();
      });
    });
  });
};

const initDashboardPage = () => {
  initReportTableSorting();

  const showToast = (message, variant = "info") => {
    const container = document.getElementById("appToastContainer");
    if (!container) {
      return;
    }
    const toast = document.createElement("div");
    const bgClass = variant === "error" ? "bg-danger" : variant === "success" ? "bg-success" : "bg-info";
    toast.className = `toast show align-items-center text-white ${bgClass} border-0 mb-2`;
    toast.setAttribute("role", "alert");
    toast.setAttribute("aria-live", "assertive");
    toast.setAttribute("aria-atomic", "true");
    toast.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" aria-label="Close"></button>
      </div>
    `;
    const closeButton = toast.querySelector(".btn-close");
    if (closeButton) {
      closeButton.addEventListener("click", () => toast.remove());
    }
    container.appendChild(toast);
    window.setTimeout(() => {
      toast.remove();
    }, 5000);
  };

  const syncPanel = document.getElementById("syncStatusPanel");
  const syncPayloadNode = document.getElementById("latest-sync-payload");
  if (syncPanel) {
    const statusUrl = syncPanel.dataset.statusUrl;
    const statusText = document.getElementById("syncStatusText");
    const startedAt = document.getElementById("syncStartedAt");
    const finishedAt = document.getElementById("syncFinishedAt");
    const progressWrap = document.getElementById("syncProgressWrap");
    const stageText = document.getElementById("syncStageText");
    const progressBar = document.getElementById("syncProgressBar");
    const messageNode = document.getElementById("syncMessage");
    const recordsNode = document.getElementById("syncRecords");

    const formatDateTime = (value) => {
      if (!value) {
        return "";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      const pad = (number) => String(number).padStart(2, "0");
      return `${pad(date.getDate())}-${pad(date.getMonth() + 1)}-${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
    };

    let currentSyncRun = syncPayloadNode ? JSON.parse(syncPayloadNode.textContent || "null") : null;

    const renderSyncRun = (syncRun) => {
      if (!syncRun) {
        if (statusText) statusText.textContent = "Er is nog geen refresh uitgevoerd vanuit de applicatie.";
        if (startedAt) startedAt.textContent = "";
        if (finishedAt) finishedAt.textContent = "";
        if (stageText) stageText.textContent = "";
        if (messageNode) messageNode.textContent = "";
        if (recordsNode) recordsNode.textContent = "";
        if (progressWrap) progressWrap.classList.add("d-none");
        return;
      }

      const statusLabels = {
        started: "Started",
        success: "Success",
        failed: "Failed",
      };
      if (statusText) {
        statusText.textContent = `Laatste refresh: ${statusLabels[syncRun.status] || syncRun.status}.`;
      }
      if (startedAt) {
        startedAt.textContent = syncRun.started_at ? `Gestart: ${formatDateTime(syncRun.started_at)}` : "";
      }
      if (finishedAt) {
        finishedAt.textContent = syncRun.finished_at ? `Klaar: ${formatDateTime(syncRun.finished_at)}` : "";
      }
      const progress = syncRun.progress || {};
      if (stageText) {
        stageText.textContent = progress.message || "";
      }
      if (messageNode) {
        messageNode.textContent = syncRun.message || "";
      }
      if (recordsNode) {
        recordsNode.textContent = `Records synced: ${syncRun.records_synced ?? 0}`;
      }
      if (progressBar) {
        const hasPercent = Number.isFinite(progress.percent);
        const width = hasPercent ? Math.max(0, Math.min(100, progress.percent)) : 100;
        progressBar.style.width = `${width}%`;
        progressBar.textContent = hasPercent ? `${width}%` : "Bezig...";
        progressBar.classList.toggle("progress-bar-animated", syncRun.is_running);
      }
      if (progressWrap) {
        progressWrap.classList.toggle("d-none", !syncRun.is_running);
      }
    };

    renderSyncRun(currentSyncRun);

    if (statusUrl) {
      let polling = null;
      let reloadScheduled = false;
      const pollStatus = async () => {
        try {
          const response = await fetch(statusUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
          });
          if (!response.ok) {
            return;
          }
          const payload = await response.json();
          const nextSyncRun = payload.sync_run || null;
          const previousStatus = currentSyncRun?.status || null;
          const nextStatus = nextSyncRun?.status || null;
          const sameSync = currentSyncRun && nextSyncRun && currentSyncRun.id === nextSyncRun.id;

          renderSyncRun(nextSyncRun);

          if (sameSync && previousStatus === "started" && nextStatus === "success") {
            showToast("Refresh completed. Dashboard wordt opnieuw geladen.", "success");
            if (!reloadScheduled) {
              reloadScheduled = true;
              window.setTimeout(() => {
                const url = new URL(window.location.href);
                url.searchParams.set("_refreshed", String(nextSyncRun.id));
                window.location.href = url.toString();
              }, 1200);
            }
          } else if (sameSync && previousStatus === "started" && nextStatus === "failed") {
            showToast(`Refresh failed: ${nextSyncRun.message || "Onbekende fout"}`, "error");
          }

          currentSyncRun = nextSyncRun;

          if (!(nextSyncRun && nextSyncRun.is_running) && polling) {
            window.clearInterval(polling);
            polling = null;
          }
        } catch (_error) {
          // Ignore transient polling errors; next interval can recover.
        }
      };

      if (currentSyncRun && currentSyncRun.is_running) {
        polling = window.setInterval(pollStatus, 5000);
      }

      const refreshForm = syncPanel.parentElement?.querySelector('form[action$="/refresh/"]');
      if (refreshForm) {
        refreshForm.addEventListener("submit", () => {
          showToast("Refresh started. Deze pagina werkt de status automatisch bij.", "info");
          if (!polling) {
            window.setTimeout(() => {
              pollStatus();
              polling = window.setInterval(pollStatus, 5000);
            }, 1000);
          }
        });
      }
    }
  }

  const chartNode = document.getElementById("controlBreakdownChart");
  if (chartNode && typeof Chart !== "undefined") {
    const labels = JSON.parse(chartNode.dataset.labels || "[]");
    const values = JSON.parse(chartNode.dataset.values || "[]");

    if (labels.length) {
      new Chart(chartNode, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Deviations",
              data: values,
              borderRadius: 8,
              backgroundColor: ["#ffd166", "#4ecdc4", "#ff6b6b", "#8ecae6", "#c77dff"],
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: {
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
            },
            y: {
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
            },
          },
        },
      });
    }
  }
};

window.initReportTableSorting = initReportTableSorting;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initDashboardPage);
} else {
  initDashboardPage();
}
