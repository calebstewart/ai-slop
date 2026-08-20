/* ai-slop's client-side behaviour: filtering the catalog, and copying commands.
 *
 * Plain browser JavaScript, no dependencies and no build step. Two things only,
 * both of which sharpen a page that is already complete without them:
 *
 *   - the catalog filter, which narrows a grid whose cards are all in the HTML;
 *   - a copy button on install commands, injected rather than authored.
 *
 * Nothing here is load-bearing. Every card, every command and every link works
 * with this file absent or broken, which is why the controls it drives are
 * revealed by it rather than hidden by it — there is never a dead control.
 *
 * There is deliberately no site-wide search. This site has around twenty pages
 * reachable in at most three clicks from the catalog; a search index would be
 * more machinery than the problem deserves.
 */
(function () {
  "use strict";

  var COPY_RESET_MS = 2000;

  /* ------------------------------------------------------------- matching */

  /* Rank a candidate against a query as [tier, position], lower being better.
   *
   * Tiers rather than one blended score: someone typing "pr" wants pr-status
   * first, ahead of anything that merely contains a p and then an r, and no
   * weighting of a fuzzy score arranges that reliably.
   *
   *   0 exact   1 prefix   2 after a separator   3 mid-word   4 subsequence
   *
   * Note there is no tier for an empty query: callers must not rank an
   * unfiltered list, because with nothing to match on the tie-breakers below
   * would sort by name length and reorder the catalog for no visible reason.
   * The one caller checks for an empty query first.
   */
  function rank(haystack, needle) {
    var at = haystack.indexOf(needle);
    if (at === 0) return haystack.length === needle.length ? [0, 0] : [1, 0];
    if (at > 0) {
      var before = haystack.charAt(at - 1);
      var boundary = before === "-" || before === " " || before === "/" || before === ".";
      return [boundary ? 2 : 3, at];
    }

    /* Subsequence fallback, so "wsk" finds writing-skills. */
    var h = 0;
    var n = 0;
    var first = -1;
    while (h < haystack.length && n < needle.length) {
      if (haystack.charAt(h) === needle.charAt(n)) {
        if (first < 0) first = h;
        n++;
      }
      h++;
    }
    return n === needle.length ? [4, first < 0 ? 0 : first] : null;
  }

  function byRank(a, b) {
    if (a.tier !== b.tier) return a.tier - b.tier;
    if (a.at !== b.at) return a.at - b.at;
    if (a.name.length !== b.name.length) return a.name.length - b.name.length;
    return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
  }

  /* --------------------------------------------------------- catalog filter */

  function setupFilter() {
    var catalog = document.querySelector(".catalog");
    if (!catalog) return;

    var input = catalog.querySelector("#skill-search");
    var grid = catalog.querySelector("#card-grid");
    var count = catalog.querySelector("#result-count");
    var empty = catalog.querySelector("#empty-state");
    var reset = catalog.querySelector("#filter-reset");
    var filters = catalog.querySelector(".filters");
    if (!input || !grid) return;

    var cards = [].slice.call(grid.children);
    var authored = cards.slice();

    /* The chips all live in one container and carry their own facet name, so the
     * groups are derived from the chips rather than from DOM structure. That is
     * what lets `trigger: auto` and `tag: github` sit in the same flat row while
     * still filtering independently. */
    var boxes = [].slice.call(catalog.querySelectorAll(".chip input[type=checkbox]"));
    var facets = [];
    for (var b = 0; b < boxes.length; b++) {
      var name = boxes[b].getAttribute("data-facet");
      if (facets.indexOf(name) === -1) facets.push(name);
    }

    /* Nothing ticked in a facet means "no filter" for that facet rather than
     * "no results" — the only reading that leaves the page usable after you tick
     * and untick something. */
    function passesFacet(card, facet) {
      var want = [];
      for (var i = 0; i < boxes.length; i++) {
        if (boxes[i].checked && boxes[i].getAttribute("data-facet") === facet) {
          want.push(boxes[i].value);
        }
      }
      if (!want.length) return true;

      /* The chip's facet name IS the card attribute suffix: a chip declaring
       * data-facet="tag" reads the card's `data-tag`. Keep those in step. */
      var have = (card.getAttribute("data-" + facet) || "").split("|");
      for (var w = 0; w < want.length; w++) {
        if (have.indexOf(want[w]) !== -1) return true; /* OR within a facet */
      }
      return false;
    }

    function render() {
      var query = input.value.trim().toLowerCase();
      var hits = [];

      for (var i = 0; i < cards.length; i++) {
        var card = cards[i];

        var allowed = true;
        for (var f = 0; f < facets.length; f++) {
          if (!passesFacet(card, facets[f])) {
            /* AND across facets. */
            allowed = false;
            break;
          }
        }

        var scored = null;
        if (allowed && query) {
          var name = (card.getAttribute("data-name") || "").toLowerCase();
          scored = rank(name, query);
          if (!scored) {
            /* Not in the name, but maybe in the tagline or the tags. Ranked
             * below every name match so the ordering still makes sense. */
            var text = (card.getAttribute("data-text") || "").toLowerCase();
            var at = text.indexOf(query);
            if (at !== -1) scored = [5, at];
          }
        } else if (allowed) {
          scored = [0, 0];
        }

        card.hidden = !scored;
        if (scored) {
          hits.push({ card: card, tier: scored[0], at: scored[1], name: card.getAttribute("data-name") || "" });
        }
      }

      /* Reorder by relevance only while there is something to be relevant to.
       * With an empty box the authored order is the right order. */
      if (query) {
        hits.sort(byRank);
        for (var h = 0; h < hits.length; h++) grid.appendChild(hits[h].card);
      } else {
        for (var a = 0; a < authored.length; a++) grid.appendChild(authored[a]);
      }

      if (count) {
        count.textContent = hits.length
          ? hits.length + (hits.length === 1 ? " skill" : " skills")
          : "Nothing matches";
      }
      if (empty) empty.hidden = hits.length > 0;

      /* So a filtered view can be linked and survives a reload. */
      var url = new URL(window.location.href);
      if (query) url.searchParams.set("q", input.value.trim());
      else url.searchParams.delete("q");
      window.history.replaceState(null, "", url.toString());
    }

    var initial = new URLSearchParams(window.location.search).get("q");
    if (initial) input.value = initial;

    input.addEventListener("input", render);
    /* One delegated listener on the shared container rather than one per chip. */
    var chipRow = catalog.querySelector(".chips");
    if (chipRow) chipRow.addEventListener("change", render);

    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && input.value) {
        input.value = "";
        render();
      }
    });

    function clearAll() {
      input.value = "";
      for (var i = 0; i < boxes.length; i++) boxes[i].checked = false;
      render();
    }

    if (reset) {
      reset.addEventListener("click", function () {
        clearAll();
        input.focus();
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      var active = document.activeElement;
      if (
        active &&
        (active.tagName === "INPUT" ||
          active.tagName === "TEXTAREA" ||
          active.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      input.focus();
      input.select();
    });

    render();

    /* Revealed last, once every listener is attached, so the controls are never
     * on screen in a state where using them would do nothing. */
    if (filters) filters.hidden = false;
  }

  /* ----------------------------------------------------------- copy buttons */

  function setupCopy() {
    if (!navigator.clipboard) return;
    var blocks = document.querySelectorAll(".snippet");
    for (var i = 0; i < blocks.length; i++) addCopy(blocks[i]);
  }

  function addCopy(block) {
    var code = block.querySelector("code") || block;

    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy this command");

    /* Announced separately, because changing a button's own label mid-press is
     * not reliably read out. */
    var live = document.createElement("span");
    live.className = "visually-hidden";
    live.setAttribute("role", "status");

    var timer = null;

    function say(message, ok) {
      button.textContent = message;
      if (ok) button.classList.add("is-done");
      else button.classList.remove("is-done");
      live.textContent = message;
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        button.textContent = "Copy";
        button.classList.remove("is-done");
        live.textContent = "";
      }, COPY_RESET_MS);
    }

    button.addEventListener("click", function () {
      navigator.clipboard.writeText((code.textContent || "").trim()).then(
        function () {
          say("Copied", true);
        },
        function () {
          /* Says so rather than claiming a success it cannot verify — a
           * clipboard write is refused outside a secure context, among other
           * reasons. */
          say("Copy failed", false);
        }
      );
    });

    block.appendChild(live);
    block.appendChild(button);
  }

  setupFilter();
  setupCopy();
})();
