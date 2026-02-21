// CommonTrace — Client-side search & tag filtering
(function () {
  const input = document.getElementById('search');
  const traceList = document.getElementById('trace-list');
  const resultsCount = document.getElementById('results-count');
  const noResults = document.getElementById('no-results');

  if (!input || !traceList) return;

  const cards = Array.from(traceList.querySelectorAll('.trace-item'));
  const totalCount = cards.length;

  // i18n: read translated strings from data attributes (fallback to English)
  const i18nShowingAll = (traceList.dataset.i18nShowingAll || 'Showing all __COUNT__ traces').replace('__COUNT__', totalCount);
  const i18nSingular = traceList.dataset.i18nSingular || 'trace';
  const i18nPlural = traceList.dataset.i18nPlural || 'traces';
  const i18nMatching = traceList.dataset.i18nMatching || 'matching';

  // Tag sidebar filtering
  const tagLinks = document.querySelectorAll('.tag-link[data-tag]');
  let activeTag = null;

  tagLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      const tag = this.dataset.tag;

      if (activeTag === tag) {
        activeTag = null;
        this.classList.remove('active');
      } else {
        tagLinks.forEach(function (l) { l.classList.remove('active'); });
        activeTag = tag;
        this.classList.add('active');
      }

      applyFilters();
    });
  });

  // Search input filtering
  let debounceTimer;
  input.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyFilters, 150);
  });

  // Read initial tag from URL hash
  if (window.location.hash) {
    var hashTag = decodeURIComponent(window.location.hash.slice(1));
    tagLinks.forEach(function (link) {
      if (link.dataset.tag === hashTag) {
        activeTag = hashTag;
        link.classList.add('active');
      }
    });
    applyFilters();
  }

  function applyFilters() {
    var query = input.value.trim().toLowerCase();
    var terms = query ? query.split(/\s+/) : [];
    var visibleCount = 0;

    cards.forEach(function (card) {
      var searchText = card.dataset.search || '';
      var cardTags = card.dataset.tags || '';

      var tagMatch = !activeTag || cardTags.split(',').indexOf(activeTag) !== -1;
      var textMatch = terms.length === 0 || terms.every(function (term) {
        return searchText.indexOf(term) !== -1;
      });

      if (tagMatch && textMatch) {
        card.style.display = '';
        visibleCount++;
      } else {
        card.style.display = 'none';
      }
    });

    if (resultsCount) {
      if (!query && !activeTag) {
        resultsCount.textContent = i18nShowingAll;
      } else {
        var label = visibleCount === 1 ? i18nSingular : i18nPlural;
        var parts = [];
        if (query) parts.push('"' + query + '"');
        if (activeTag) parts.push('#' + activeTag);
        resultsCount.textContent = visibleCount + ' ' + label + ' ' + i18nMatching + ' ' + parts.join(' + ');
      }
    }

    if (noResults) {
      noResults.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    if (activeTag) {
      history.replaceState(null, '', '#' + encodeURIComponent(activeTag));
    } else if (!query) {
      history.replaceState(null, '', window.location.pathname);
    }
  }
})();
