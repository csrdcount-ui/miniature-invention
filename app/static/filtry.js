// Licznik wyników na żywo w panelu filtrów listy umów.
// Bez tego skryptu wszystko działa: formularz to zwykłe GET, licznik pokazuje stan po ostatnim filtrowaniu.
(function () {
  var form = document.getElementById("filtry");
  var licznik = document.getElementById("licznik");
  var przycisk = document.getElementById("pokaz-wyniki");
  if (!form || !licznik || !window.fetch || !window.URLSearchParams) return;
  var timer = null;
  var nr = 0;
  function odswiez() {
    var moj = ++nr;
    var params = new URLSearchParams(new FormData(form));
    fetch(form.dataset.licznik + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || moj !== nr) return; // starsza odpowiedź przyszła później: pomijamy
        licznik.textContent = d.count === 0
          ? "Pasuje: 0 umów. Zmień filtry, żeby coś zobaczyć."
          : "Pasuje: " + d.text + ".";
        if (przycisk) przycisk.textContent = d.count === 0 ? "Filtruj" : "Pokaż " + d.text;
      })
      .catch(function () {});
  }
  function zaplanuj() {
    clearTimeout(timer);
    timer = setTimeout(odswiez, 400);
  }
  form.addEventListener("change", zaplanuj);
  form.addEventListener("input", zaplanuj);
})();
