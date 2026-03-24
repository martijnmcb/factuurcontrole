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
