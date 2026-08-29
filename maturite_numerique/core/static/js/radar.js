/* Rend les graphiques radar (Chart.js) déclarés par le composant _radar.html. */
(function () {
  if (typeof Chart === "undefined") return;

  function hexToRgba(hex, alpha) {
    var h = (hex || "#3e90f0").replace("#", "");
    if (h.length === 3) {
      h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    }
    var r = parseInt(h.substr(0, 2), 16);
    var g = parseInt(h.substr(2, 2), 16);
    var b = parseInt(h.substr(4, 2), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
  }

  document.querySelectorAll("[data-radar]").forEach(function (canvas) {
    var holder = document.getElementById(canvas.dataset.radar);
    if (!holder) return;
    var conf = JSON.parse(holder.textContent);
    var dark = !!conf.dark;
    var lineColor = dark ? "rgba(255,255,255,0.28)" : "rgba(20,32,46,0.12)";
    var labelColor = dark ? "rgba(255,255,255,0.92)" : "#46536a";

    new Chart(canvas, {
      type: "radar",
      data: {
        labels: conf.labels,
        datasets: (conf.series || []).map(function (s) {
          return {
            label: s.nom,
            data: s.valeurs,
            borderColor: dark ? "#ffffff" : s.couleur,
            backgroundColor: dark ? "rgba(255,255,255,0.16)" : hexToRgba(s.couleur, 0.15),
            pointBackgroundColor: dark ? "#ffffff" : s.couleur,
            borderWidth: 2,
          };
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          r: {
            min: 0,
            max: 5,
            ticks: { stepSize: 1, display: !dark, color: labelColor, backdropColor: "transparent" },
            grid: { color: lineColor },
            angleLines: { color: lineColor },
            pointLabels: { color: labelColor, font: { size: 12 } },
          },
        },
        plugins: {
          legend: { display: (conf.series || []).length > 1, labels: { color: labelColor } },
        },
      },
    });
  });
})();
