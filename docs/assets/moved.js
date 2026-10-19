// A page that has moved (explore.html and aquifer.html, now the map): goes
// to its new address at once, keeping the old address's query (its words win
// over the new address's) and #fragment. Without JavaScript the page's meta
// refresh and its link go to the new address alone.
(() => {
  const to = new URL(document.currentScript.dataset.to, location.href);
  for (const [name, value] of new URLSearchParams(location.search)) {
    to.searchParams.set(name, value);
  }
  to.hash = location.hash;
  location.replace(to.href.replaceAll("%2C", ","));
})();
