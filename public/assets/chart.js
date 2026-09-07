/* Bar-chart detail panel: hover on desktop, tap on any device.
   Each .bar carries its full day as data-detail JSON; data-panel points at
   the .chart-detail element to update. One delegated listener set, no deps. */
(function () {
  var canHover = window.matchMedia &&
    window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  function activate(bar) {
    var panel = document.getElementById(bar.getAttribute("data-panel") || "");
    if (!panel) return;
    var svg = bar.closest("svg");
    if (svg) {
      var prev = svg.querySelector(".bar.is-active");
      if (prev && prev !== bar) prev.classList.remove("is-active");
    }
    bar.classList.add("is-active");
    var pairs;
    try { pairs = JSON.parse(bar.getAttribute("data-detail") || "[]"); }
    catch (e) { pairs = []; }
    panel.querySelector(".cd-title").textContent = bar.getAttribute("data-label") || "";
    panel.querySelector(".cd-grid").innerHTML = pairs.map(function (p) {
      return '<div class="cd-stat"><span class="cd-k">' + p[0] +
             '</span><span class="cd-v">' + p[1] + "</span></div>";
    }).join("");
  }

  function barFrom(target) {
    return target.closest ? target.closest(".bar[data-detail]") : null;
  }

  document.addEventListener("pointerover", function (e) {
    if (!canHover) return;
    var bar = barFrom(e.target);
    if (bar) activate(bar);
  });
  document.addEventListener("click", function (e) {
    var bar = barFrom(e.target);
    if (bar) activate(bar);
  });
  document.addEventListener("focusin", function (e) {
    var bar = barFrom(e.target);
    if (bar) activate(bar);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var bar = barFrom(e.target);
    if (bar) { activate(bar); e.preventDefault(); }
  });
})();
