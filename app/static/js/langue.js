/* Changement de langue : aucun gestionnaire inline afin de respecter la CSP. */
document.addEventListener("DOMContentLoaded", function () {
  var select = document.getElementById("select-langue");
  if (!select) return;
  select.addEventListener("change", function () {
    var form = select.form;
    if (form) form.requestSubmit();
  });
});
