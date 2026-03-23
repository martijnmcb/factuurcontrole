document.addEventListener("DOMContentLoaded", () => {
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
});
