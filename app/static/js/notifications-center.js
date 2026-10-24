(() => {
  "use strict";
  const root = document.querySelector("[data-notifications-center]");
  if (!root) return;
  const cards = Array.from(root.querySelectorAll("[data-notification-card]"));
  const search = root.querySelector("[data-notification-search]");
  const filters = Array.from(root.querySelectorAll("[data-notification-filter]"));
  const resultCount = root.querySelector("[data-notification-result-count]");
  const emptyState = root.querySelector("[data-notification-filter-empty]");
  let activeFilter = "all";

  function updateView() {
    const query = (search?.value || "").trim().toLocaleLowerCase();
    let visible = 0;
    cards.forEach((card) => {
      const unread = card.dataset.unread === "true";
      const text = (card.textContent || "").toLocaleLowerCase();
      const matchesFilter = activeFilter === "all" ||
        (activeFilter === "unread" && unread) ||
        (activeFilter === "read" && !unread);
      const show = matchesFilter && (!query || text.includes(query));
      card.hidden = !show;
      if (show) visible += 1;
    });
    if (resultCount) {
      resultCount.textContent = visible + " notification" + (visible === 1 ? "" : "s") +
        " affichée" + (visible === 1 ? "" : "s");
    }
    if (emptyState) emptyState.hidden = visible > 0;
    filters.forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.notificationFilter === activeFilter));
    });
  }

  filters.forEach((button) => button.addEventListener("click", () => {
    activeFilter = button.dataset.notificationFilter || "all";
    updateView();
  }));
  if (search) search.addEventListener("input", updateView);
  updateView();
})();