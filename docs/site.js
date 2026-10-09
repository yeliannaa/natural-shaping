"use strict";

(() => {
  const triggers = document.querySelectorAll("[data-lightbox]");
  let returnFocus = null;
  if (triggers.length && typeof HTMLDialogElement !== "undefined") {
    const dialog = document.createElement("dialog");
    dialog.className = "image-dialog";
    dialog.innerHTML = '<div class="dialog-toolbar"><p class="dialog-caption" id="image-caption"></p><button type="button" class="dialog-zoom">放大预览</button><button type="button" class="dialog-close" aria-label="关闭照片预览">关闭 ×</button></div><div class="dialog-viewport"><img class="dialog-image" alt=""></div><p class="dialog-help">点击照片切换放大；放大后可滚动查看。这里展示网页预览文件，非完整分辨率交付文件。</p>';
    dialog.setAttribute("aria-labelledby", "image-caption");
    document.body.append(dialog);
    const photo = dialog.querySelector(".dialog-image");
    const viewport = dialog.querySelector(".dialog-viewport");
    const caption = dialog.querySelector(".dialog-caption");
    const zoom = dialog.querySelector(".dialog-zoom");
    const close = dialog.querySelector(".dialog-close");
    function toggleZoom() {
      const expanded = viewport.classList.toggle("is-zoomed");
      zoom.textContent = expanded ? "适应窗口" : "放大预览";
      zoom.setAttribute("aria-pressed", String(expanded));
      viewport.scrollTo(0, 0);
    }
    triggers.forEach((trigger) => {
      if (trigger.tagName !== "A" && trigger.tagName !== "BUTTON") {
        trigger.tabIndex = 0;
        trigger.setAttribute("role", "button");
        trigger.style.cursor = "zoom-in";
      }
      const open = (event) => {
        if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        const image = trigger.tagName === "IMG" ? trigger : trigger.querySelector("img");
        const url = trigger.getAttribute("data-lightbox-src") || trigger.getAttribute("href") || (image && image.src);
        if (!url) return;
        returnFocus = trigger;
        photo.src = url;
        photo.alt = (image && image.alt) || trigger.getAttribute("data-caption") || "照片预览";
        caption.textContent = trigger.getAttribute("data-caption") || photo.alt;
        viewport.classList.remove("is-zoomed");
        zoom.textContent = "放大预览";
        zoom.setAttribute("aria-pressed", "false");
        dialog.showModal();
        document.body.classList.add("dialog-open");
        close.focus();
      };
      trigger.addEventListener("click", open);
      if (trigger.tagName !== "A" && trigger.tagName !== "BUTTON") trigger.addEventListener("keydown", open);
    });
    close.addEventListener("click", () => dialog.close());
    zoom.addEventListener("click", toggleZoom);
    photo.addEventListener("click", toggleZoom);
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        const bounds = dialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
      }
    });
    dialog.addEventListener("close", () => {
      document.body.classList.remove("dialog-open");
      if (returnFocus) returnFocus.focus();
    });
  }
  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.getAttribute("data-copy-target"));
      if (!target) return;
      const content = target.textContent.trim();
      const originalLabel = button.textContent;
      try {
        let copied = false;
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(content);
            copied = true;
          } catch { /* Some browsers restrict clipboard permission. */ }
        }
        if (!copied) {
          const field = document.createElement("textarea");
          field.value = content;
          field.style.position = "fixed";
          field.style.opacity = "0";
          document.body.append(field);
          field.select();
          copied = document.execCommand("copy");
          field.remove();
          if (!copied) throw new Error("Copy unavailable");
        }
        button.textContent = "已复制";
      } catch {
        button.textContent = "请选中文本复制";
      }
      window.setTimeout(() => { button.textContent = originalLabel; }, 2400);
    });
  });
})();
