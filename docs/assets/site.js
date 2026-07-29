// 画面が狭いときのメニュー開閉と、埋め込みや表の見た目の調整。
(function () {
  "use strict";

  // メニューの開閉
  var toggle = document.querySelector(".nav-toggle");
  var sidebar = document.getElementById("sitenav");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      var open = sidebar.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // YouTube などの埋め込みを、縦横比を保つ入れ物で包む
  document.querySelectorAll(".content iframe").forEach(function (frame) {
    var src = frame.getAttribute("src") || "";
    if (src.indexOf("youtube.com/embed") === -1) return;
    if (frame.parentElement && frame.parentElement.classList.contains("embed-wrap")) return;
    var wrap = document.createElement("div");
    wrap.className = "embed-wrap";
    frame.parentNode.insertBefore(wrap, frame);
    wrap.appendChild(frame);
    frame.setAttribute("loading", "lazy");
    frame.setAttribute("allowfullscreen", "");
  });

  // 幅の広い表は、横スクロールできる入れ物で包む
  document.querySelectorAll(".content table").forEach(function (table) {
    if (table.parentElement && table.parentElement.classList.contains("table-wrap")) return;
    var wrap = document.createElement("div");
    wrap.className = "table-wrap";
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
  });

  // 外部サイトへのリンクは新しいタブで開く
  document.querySelectorAll('.content a[href^="http"]').forEach(function (a) {
    if (a.hostname && a.hostname !== location.hostname) {
      a.setAttribute("target", "_blank");
      a.setAttribute("rel", "noopener noreferrer");
    }
  });
})();
