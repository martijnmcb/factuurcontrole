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

  const initControl5RouteModal = () => {
    const modal = document.getElementById("control5RouteModal");
    if (!modal) {
      return;
    }

    const titleNode = document.getElementById("control5ModalTitle");
    const subtitleNode = document.getElementById("control5ModalSubtitle");
    const loadingNode = document.getElementById("control5ModalLoading");
    const errorNode = document.getElementById("control5ModalError");
    const headNode = document.getElementById("control5ModalHead");
    const bodyNode = document.getElementById("control5ModalBody");

    const closeModal = () => {
      modal.classList.add("d-none");
      modal.setAttribute("aria-hidden", "true");
    };

    const openModal = () => {
      modal.classList.remove("d-none");
      modal.setAttribute("aria-hidden", "false");
    };

    modal.querySelectorAll("[data-close-control5-modal]").forEach((node) => {
      node.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.classList.contains("d-none")) {
        closeModal();
      }
    });

    document.querySelectorAll(".control-5-route-row").forEach((row) => {
      row.style.cursor = "pointer";
      row.addEventListener("click", async () => {
        const detailUrl = row.dataset.detailUrl;
        const routeNummer = row.dataset.routeNummer || "";
        const routeDate = row.dataset.routeDate || "";
        if (!detailUrl) {
          return;
        }

        openModal();
        if (titleNode) titleNode.textContent = `Route ${routeNummer}`;
        if (subtitleNode) subtitleNode.textContent = routeDate;
        if (loadingNode) {
          loadingNode.textContent = "Ritdetails laden...";
          loadingNode.classList.remove("d-none");
        }
        if (errorNode) {
          errorNode.textContent = "";
          errorNode.classList.add("d-none");
        }
        if (headNode) headNode.innerHTML = "";
        if (bodyNode) bodyNode.innerHTML = "";

        try {
          const response = await fetch(detailUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const payload = await response.json();
          if (titleNode) titleNode.textContent = `Route ${payload.route_nummer || routeNummer}`;
          if (subtitleNode) subtitleNode.textContent = payload.route_date || routeDate;
          if (headNode) {
            headNode.innerHTML = `<tr>${(payload.headers || []).map((header) => `<th>${header}</th>`).join("")}</tr>`;
          }
          if (bodyNode) {
            const rows = payload.rows || [];
            if (!rows.length) {
              bodyNode.innerHTML = `<tr><td colspan="${(payload.headers || []).length || 1}" class="text-center text-light-emphasis">Geen ritdetails gevonden.</td></tr>`;
            } else {
              bodyNode.innerHTML = rows
                .map((detailRow) => `<tr>${detailRow.map((value) => `<td>${value ?? ""}</td>`).join("")}</tr>`)
                .join("");
            }
          }
          initReportTableSorting();
        } catch (_error) {
          if (errorNode) {
            errorNode.textContent = "Ritdetails konden niet worden geladen.";
            errorNode.classList.remove("d-none");
          }
        } finally {
          if (loadingNode) {
            loadingNode.classList.add("d-none");
          }
        }
      });
    });
  };

  initControl5RouteModal();

  document.querySelectorAll(".auto-dismiss-alert").forEach((alertNode) => {
    window.setTimeout(() => {
      alertNode.remove();
    }, 5000);
  });

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
    let autoHideTimer = null;
    const closeButton = document.getElementById("syncStatusClose");
    if (closeButton) {
      closeButton.addEventListener("click", () => {
        syncPanel.classList.add("d-none");
      });
    }

    const statusUrl = syncPanel.dataset.statusUrl;
    const statusText = document.getElementById("syncStatusText");
    const outcomeBadge = document.getElementById("syncOutcomeBadge");
    const noDataBadge = document.getElementById("syncNoDataBadge");
    const startedAt = document.getElementById("syncStartedAt");
    const finishedAt = document.getElementById("syncFinishedAt");
    const progressWrap = document.getElementById("syncProgressWrap");
    const spinner = document.getElementById("syncSpinner");
    const progressHint = document.getElementById("syncProgressHint");
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
        syncPanel.classList.add("d-none");
        if (statusText) statusText.textContent = "Er is nog geen refresh uitgevoerd vanuit de applicatie.";
        if (outcomeBadge) outcomeBadge.classList.add("d-none");
        if (noDataBadge) noDataBadge.classList.add("d-none");
        if (startedAt) startedAt.textContent = "";
        if (finishedAt) finishedAt.textContent = "";
        if (spinner) spinner.classList.add("d-none");
        if (progressHint) progressHint.textContent = "";
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
      if (syncRun.is_running) {
        syncPanel.classList.remove("d-none");
      }
      if (statusText) {
        statusText.textContent = `Laatste refresh: ${statusLabels[syncRun.status] || syncRun.status}.`;
      }
      const noNewData = (syncRun.message || "").toLowerCase().includes("no new current data");
      if (outcomeBadge) {
        outcomeBadge.classList.toggle("d-none", syncRun.status !== "success");
      }
      if (noDataBadge) {
        noDataBadge.classList.toggle("d-none", !noNewData);
      }
      if (startedAt) {
        startedAt.textContent = syncRun.started_at ? `Gestart: ${formatDateTime(syncRun.started_at)}` : "";
      }
      if (finishedAt) {
        finishedAt.textContent = syncRun.finished_at ? `Klaar: ${formatDateTime(syncRun.finished_at)}` : "";
      }
      if (spinner) {
        spinner.classList.toggle("d-none", !syncRun.is_running);
      }
      if (progressHint) {
        if (syncRun.is_running) {
          progressHint.textContent = "Refresh loopt. Je kunt deze pagina verlaten; de status blijft doorlopen op de server.";
        } else if (syncRun.status === "success" && noNewData) {
          progressHint.textContent = "Refresh voltooid. Er was geen nieuwe data om op te halen.";
        } else if (syncRun.status === "success") {
          progressHint.textContent = "Refresh voltooid. De lokale data is bijgewerkt.";
        } else if (syncRun.status === "failed") {
          progressHint.textContent = "Refresh mislukt.";
        } else {
          progressHint.textContent = "";
        }
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
        progressBar.classList.toggle("progress-bar-striped", syncRun.is_running);
        progressBar.classList.toggle("bg-success", syncRun.status === "success");
        progressBar.classList.toggle("bg-danger", syncRun.status === "failed");
      }
      if (progressWrap) {
        progressWrap.classList.toggle("d-none", !syncRun.is_running && syncRun.status !== "success" && syncRun.status !== "failed");
      }

      if (autoHideTimer) {
        window.clearTimeout(autoHideTimer);
        autoHideTimer = null;
      }
      if (syncRun.status === "success" || syncRun.status === "failed") {
        autoHideTimer = window.setTimeout(() => {
          syncPanel.classList.add("d-none");
        }, 5000);
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
          syncPanel.classList.remove("d-none");
          if (outcomeBadge) outcomeBadge.classList.add("d-none");
          if (noDataBadge) noDataBadge.classList.add("d-none");
          if (statusText) statusText.textContent = "Laatste refresh: Started.";
          if (progressWrap) progressWrap.classList.remove("d-none");
          if (spinner) spinner.classList.remove("d-none");
          if (progressHint) progressHint.textContent = "Refresh loopt. Je kunt deze pagina verlaten; de status blijft doorlopen op de server.";
          if (stageText) stageText.textContent = "Starting refresh";
          if (progressBar) {
            progressBar.style.width = "0%";
            progressBar.textContent = "0%";
            progressBar.classList.add("progress-bar-animated", "progress-bar-striped");
            progressBar.classList.remove("bg-success", "bg-danger");
          }
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

  const control13ChartNode = document.getElementById("control13AgeChart");
  const control13LabelsNode = document.getElementById("control13-age-labels");
  const control13ValuesNode = document.getElementById("control13-age-values");
  if (control13ChartNode && control13LabelsNode && control13ValuesNode && typeof Chart !== "undefined") {
    const labels = JSON.parse(control13LabelsNode.textContent || "[]");
    const values = JSON.parse(control13ValuesNode.textContent || "[]");

    if (labels.length) {
      new Chart(control13ChartNode, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Aantal voertuigen",
              data: values,
              borderRadius: 8,
              backgroundColor: "#8ecae6",
              hoverBackgroundColor: "#b7e1f7",
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          responsive: true,
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: {
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
              title: {
                display: true,
                text: "Leeftijd (jaren)",
                color: "#edf6ff",
              },
            },
            y: {
              beginAtZero: true,
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
              title: {
                display: true,
                text: "Aantal voertuigen",
                color: "#edf6ff",
              },
            },
          },
        },
      });
    }
  }

  const control20ChartNode = document.getElementById("control20CostChart");
  const control20LabelsNode = document.getElementById("control20-cost-labels");
  const control20ValuesNode = document.getElementById("control20-cost-values");
  if (control20ChartNode && control20LabelsNode && control20ValuesNode && typeof Chart !== "undefined") {
    const labels = JSON.parse(control20LabelsNode.textContent || "[]");
    const values = JSON.parse(control20ValuesNode.textContent || "[]");

    if (labels.length) {
      new Chart(control20ChartNode, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Kosten per rit",
              data: values,
              borderRadius: 8,
              backgroundColor: "#4ecdc4",
              hoverBackgroundColor: "#81e6dc",
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          responsive: true,
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: {
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
              title: {
                display: true,
                text: "Datum",
                color: "#edf6ff",
              },
            },
            y: {
              beginAtZero: true,
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
              title: {
                display: true,
                text: "Kosten per rit",
                color: "#edf6ff",
              },
            },
          },
        },
      });
    }
  }

  const control20MonthlyChartNode = document.getElementById("control20MonthlyCostChart");
  const control20MonthlyLabelsNode = document.getElementById("control20-monthly-cost-labels");
  const control20MonthlyValuesNode = document.getElementById("control20-monthly-cost-values");
  if (control20MonthlyChartNode && control20MonthlyLabelsNode && control20MonthlyValuesNode && typeof Chart !== "undefined") {
    const labels = JSON.parse(control20MonthlyLabelsNode.textContent || "[]");
    const values = JSON.parse(control20MonthlyValuesNode.textContent || "[]");

    if (labels.length) {
      new Chart(control20MonthlyChartNode, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Gewogen gemiddelde kosten",
              data: values,
              borderColor: "#ffd166",
              backgroundColor: "rgba(255, 209, 102, 0.2)",
              pointBackgroundColor: "#ffd166",
              pointRadius: 4,
              tension: 0.25,
              fill: true,
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          responsive: true,
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: {
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
              title: {
                display: true,
                text: "Maand",
                color: "#edf6ff",
              },
            },
            y: {
              beginAtZero: true,
              ticks: { color: "#edf6ff" },
              grid: { color: "rgba(255,255,255,0.08)" },
              title: {
                display: true,
                text: "Gewogen gemiddelde kosten per rit",
                color: "#edf6ff",
              },
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
