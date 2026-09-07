(function () {
  "use strict";

  function addGuide() {
    var info = document.querySelector(".swagger-ui .info");
    if (!info || document.querySelector(".tr-guide")) return;

    var guide = document.createElement("aside");
    guide.className = "tr-guide";
    guide.innerHTML =
      '<strong>First successful call</strong>' +
      '<span>1</span> Check service status' +
      '<span>2</span> Upload your tender file' +
      '<span>3</span> Download a PDF report automatically';
    info.appendChild(guide);
  }

  var style = document.createElement("style");
  style.textContent =
    ".tr-guide{display:flex;align-items:center;gap:10px;margin:20px 0;padding:14px 16px;border:1px solid #d7ddd8;border-radius:5px;background:#fff;color:#667578;font-size:12px}" +
    ".tr-guide strong{margin-right:6px;color:#17333b;font-size:13px}" +
    ".tr-guide span{display:grid;place-items:center;width:19px;height:19px;border-radius:50%;background:#b7dfbd;color:#17333b;font:600 10px 'DM Mono',monospace}" +
    "@media(max-width:700px){.tr-guide{align-items:flex-start;flex-wrap:wrap}.tr-guide strong{width:100%}}";
  document.head.appendChild(style);

  var observer = new MutationObserver(addGuide);
  observer.observe(document.body, { childList: true, subtree: true });
  addGuide();
}());
