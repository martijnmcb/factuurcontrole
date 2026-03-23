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

  document.querySelectorAll(".route-map").forEach((node, index) => {
    if (typeof L === "undefined") {
      return;
    }

    const pointsScriptId = node.dataset.pointsId;
    const pointsScript = pointsScriptId ? document.getElementById(pointsScriptId) : null;
    if (!pointsScript) {
      return;
    }

    const points = JSON.parse(pointsScript.textContent || "[]");
    const map = L.map(node, { scrollWheelZoom: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      referrerPolicy: "strict-origin-when-cross-origin",
    }).addTo(map);

    if (!points.length) {
      map.setView([52.35, 5.75], 10);
      return;
    }

    const latLngs = points.map((point) => [point.lat, point.lng]);
    const colors = ["#ffd166", "#4ecdc4"];
    const color = colors[index % colors.length];
    L.polyline(latLngs, { color, weight: 4, opacity: 0.85 }).addTo(map);

    points.forEach((point) => {
      const marker = L.circleMarker([point.lat, point.lng], {
        radius: 6,
        color,
        weight: 2,
        fillColor: "#081420",
        fillOpacity: 0.95,
      }).addTo(map);
      marker.bindPopup(`<strong>${point.index}. ${point.event_type}</strong><br>${point.label}<br>${point.time}`);
    });

    map.fitBounds(latLngs, { padding: [24, 24] });
  });
});
