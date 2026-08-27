/* Bin day lookup, for the per-council pages under /bin-day/.
 *
 * The page URL carries the council; the visitor carries the address. Nothing
 * about a collection day is baked into the HTML, so this page cannot fossilise
 * a schedule the way a printed calendar does - and it works the same for the
 * zone-keyed councils, where a suburb has no single answer to bake in.
 */
(function () {
  'use strict';

  // api.bin-space.app, NOT app.bin-space.app. The app host routes to the
  // user-shell in the load balancer's url map, so a request there is served by
  // the shell and never reaches this service - the responses come back with no
  // CORS headers at all. Only the api host maps to bin-schedule-backend.
  var API = 'https://api.bin-space.app';

  var page = document.querySelector('.binday-page');
  if (!page) return;

  var pageCouncil = page.getAttribute('data-council') || '';
  var whereInput = document.getElementById('binday-where');
  var streetInput = document.getElementById('binday-street');
  var list = document.getElementById('binday-suggestions');
  var result = document.getElementById('binday-result');
  if (!whereInput || !streetInput || !list || !result) return;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function say(cls, text) {
    clear(result);
    result.appendChild(el('p', cls, text));
  }

  var timer = null;
  var lastQuery = '';
  var seq = 0;

  /* ---- step one: which part of the council -------------------------------

     A council page cannot pre-fill this. A council is not a suburb - Frankston
     council also collects Seaford, Langwarrin and Carrum Downs - and the
     address service needs a suburb or a postcode before it will suggest
     anything, so one of the two has to come from the visitor. Either will do,
     which spares anyone who knows their suburb but not their postcode.  */

  function where() {
    return (whereInput.value || '').trim();
  }

  function whereParam() {
    var value = where();
    return (/^\d{4}$/.test(value) ? '&postcode=' : '&suburb=') + encodeURIComponent(value);
  }

  function whereReady() {
    var value = where();
    return /^\d{4}$/.test(value) || value.length >= 3;
  }

  whereInput.addEventListener('input', function () {
    var ready = whereReady();
    streetInput.disabled = !ready;
    hideSuggestions();
    // A changed suburb makes any showing answer belong to a different address,
    // so it goes rather than sitting there looking current.
    clear(result);

    // Someone who typed the street first and then corrected the suburb has
    // left real text in the street field. Without this the corrected suburb
    // produces nothing until they nudge that field, because only its own input
    // event asks for suggestions.
    lastQuery = '';
    if (timer) clearTimeout(timer);
    if (ready && streetInput.value.trim().length >= 2) {
      timer = setTimeout(suggest, 250);
    }
  });

  // Two text inputs and no submit button: the spec says Enter should not
  // implicitly submit, but nothing here needs that nuance to hold in every
  // browser - a navigation would throw the answer away.
  var form = document.getElementById('binday-form');
  if (form) {
    form.addEventListener('submit', function (e) { e.preventDefault(); });
  }

  /* ---- step two: type-ahead over the addresses in that postcode --------- */

  streetInput.addEventListener('input', function () {
    if (timer) clearTimeout(timer);
    timer = setTimeout(suggest, 250);
  });

  streetInput.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') hideSuggestions();
  });

  function hideSuggestions() {
    clear(list);
    list.hidden = true;
    streetInput.setAttribute('aria-expanded', 'false');
  }

  function suggest() {
    var q = (streetInput.value || '').trim();
    if (!whereReady() || q.length < 2) {
      hideSuggestions();
      return;
    }
    if (q === lastQuery) return;
    lastQuery = q;

    // Every suggest call is numbered so a slow early response cannot land on
    // top of a later, more specific one.
    var mine = ++seq;
    var url = API + '/addresses/suggest?limit=8' + whereParam()
      + '&q=' + encodeURIComponent(q);

    fetch(url).then(function (r) {
      if (!r.ok) throw new Error('suggest ' + r.status);
      return r.json();
    }).then(function (rows) {
      if (mine !== seq) return;
      render(rows || []);
    }).catch(function () {
      if (mine !== seq) return;
      hideSuggestions();
      say('binday-error', 'We could not reach the address lookup just now. Try again in a '
        + 'moment - if it keeps happening, let us know at support@bin-space.app.');
    });
  }

  function render(rows) {
    clear(list);
    if (!rows.length) {
      list.hidden = true;
      streetInput.setAttribute('aria-expanded', 'false');
      return;
    }
    rows.forEach(function (row) {
      var li = el('li', 'binday-suggestion');
      li.setAttribute('role', 'option');
      var btn = el('button', null, row.label);
      btn.type = 'button';
      btn.addEventListener('click', function () { lookup(row); });
      li.appendChild(btn);
      list.appendChild(li);
    });
    list.hidden = false;
    streetInput.setAttribute('aria-expanded', 'true');
  }

  /* ---- step three: the schedule for the chosen address ------------------ */

  // The suggestion's own fields go back verbatim. A council decides for itself
  // which of them it needs - a property-keyed source wants the street number, a
  // bundled locality calendar never reads it - so sending all of them lets the
  // service ask for only what its source uses.
  function lookup(row) {
    hideSuggestions();
    streetInput.value = row.label;
    lastQuery = row.label;
    say('binday-loading', 'Looking up ' + row.label + '…');

    var url = API + '/schedules'
      + '?suburb=' + encodeURIComponent(row.suburb || '')
      + '&postcode=' + encodeURIComponent(row.postcode || '')
      + '&street=' + encodeURIComponent(row.street || '')
      + '&streetNumber=' + encodeURIComponent(row.streetNumber || '')
      + (row.id ? '&gnafId=' + encodeURIComponent(row.id) : '');

    fetch(url).then(function (r) {
      return r.json().then(function (body) { return { ok: r.ok, body: body }; });
    }).then(function (res) {
      if (res.ok) showSchedule(res.body, row);
      else showError(res.body, row);
    }).catch(function () {
      say('binday-error', 'We could not reach the schedule service just now. Try again in '
        + 'a moment - if it keeps happening, let us know at support@bin-space.app.');
    });
  }

  // The only way to reach a lookup is by clicking a suggestion, so none of
  // these may blame the visitor's typing. ADDRESS_NOT_FOUND in particular used
  // to say "try picking it from the list rather than typing it in full", which
  // is advice for a thing they cannot have done.
  //
  // It means the address service offered a property the council's own schedule
  // does not carry. Sometimes the council is right - a CBD tower on a
  // commercial service has no kerbside collection at all - and sometimes it is
  // a gap on our side. We cannot tell which from here, so the message says so
  // and offers the one useful next step.
  function messageFor(code) {
    var council = pageCouncil || 'This council';
    switch (code) {
      case 'NOT_COVERED':
        return 'We do not have a schedule for that address yet. Our coverage page '
          + 'lists every council we know about, including the gaps.';
      case 'ADDRESS_NOT_FOUND':
        return council + '’s schedule does not list that address. That is sometimes '
          + 'correct - not every property is on a kerbside run - and sometimes it is a '
          + 'gap on our side. If your bins do go out, tell us and we will look.';
      case 'AMBIGUOUS_ADDRESS':
        return council + '’s schedule has more than one entry for that address and we '
          + 'cannot tell which one is yours. We would rather ask than guess your bin '
          + 'day.';
      case 'SOURCE_UNAVAILABLE':
        return 'The council’s own schedule service is not answering right now. This is '
          + 'usually temporary - please try again shortly.';
      default:
        return null;
    }
  }

  // A dead end is the most useful moment to hear from someone: they have an
  // address we cannot answer for, which is exactly what we need to fix it.
  function reportLink(row) {
    var subject = 'Bin day lookup - ' + (pageCouncil || 'unknown council');
    var body = 'Hi Bin Space,\n\nThe bin day page for '
      + (pageCouncil || 'this council') + ' could not answer for:\n\n'
      + (row && row.label ? row.label : '(address)')
      + '\n\nMy bins do go out. Here is the day, if I know it: ';
    var a = el('a', null, 'Tell us about this address');
    a.href = 'mailto:support@bin-space.app?subject=' + encodeURIComponent(subject)
      + '&body=' + encodeURIComponent(body);
    var p = el('p');
    p.appendChild(a);
    return p;
  }

  function showError(body, row) {
    var code = body && body.error;
    clear(result);
    result.appendChild(el('p', 'binday-error',
      messageFor(code) || (body && body.message)
        || 'Something went wrong looking that up. Please try again.'));
    if (code === 'NOT_COVERED') {
      var p = el('p');
      var a = el('a', null, 'See what we cover');
      a.href = '/coverage/';
      p.appendChild(a);
      result.appendChild(p);
    } else if (code === 'ADDRESS_NOT_FOUND' || code === 'AMBIGUOUS_ADDRESS') {
      result.appendChild(reportLink(row));
    }
  }

  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                'September', 'October', 'November', 'December'];

  // Dates arrive as plain calendar days (2026-08-27). Handing that to the Date
  // constructor parses it as UTC midnight, which in Australia reads back as the
  // day before, so the parts are used as written instead.
  function formatDate(iso) {
    var bits = (iso || '').split('-');
    if (bits.length !== 3) return iso;
    var d = new Date(+bits[0], +bits[1] - 1, +bits[2]);
    return DAYS[d.getDay()] + ' ' + (+bits[2]) + ' ' + MONTHS[+bits[1] - 1];
  }

  var COLOURS = { red: 1, yellow: 1, green: 1, blue: 1, purple: 1, grey: 1 };

  function showSchedule(data, row) {
    clear(result);

    var collections = data.collections || [];
    var heading = el('h3', 'binday-answer-head',
      collections.length ? 'Next collection at ' + row.label : 'Nothing due at ' + row.label);
    result.appendChild(heading);

    if (!collections.length) {
      result.appendChild(el('p', null, 'No collection is listed for this address in the '
        + 'next seven days. That is unusual - if your bins do go out this week, please '
        + 'tell us at support@bin-space.app.'));
    }

    collections.forEach(function (c) {
      var day = el('div', 'binday-day');
      day.appendChild(el('strong', null, formatDate(c.date)));
      var pills = el('div', 'binday-bins');
      (c.bins || []).forEach(function (bin) {
        var pill = el('span', 'bin-pill');
        var colour = COLOURS[bin.colour] ? bin.colour : 'grey';
        pill.appendChild(el('span', 'dot dot-' + colour));
        pill.appendChild(el('span', null, bin.name));
        pills.appendChild(pill);
      });
      day.appendChild(pills);
      result.appendChild(day);
    });

    // The page is one council; the address decides which council actually
    // collects there. Where they disagree the address wins, and saying so is
    // better than quietly showing a neighbour council's answer under our
    // heading.
    if (data.council && pageCouncil && data.council !== pageCouncil) {
      result.appendChild(el('p', 'binday-note',
        'That address is collected by ' + data.council + ', not ' + pageCouncil
          + '. The days above are the right ones for it.'));
    }

    // stale means the schedule is projected past the last date the council's
    // published calendar actually covers. It is still our best answer, and
    // pretending otherwise is exactly what this site says it does not do.
    if (data.stale) {
      result.appendChild(el('p', 'binday-note',
        'Heads up: this council publishes a yearly calendar and the one we read has run '
          + 'out, so these dates are projected from its pattern rather than confirmed. '
          + 'We are re-reading it. Worth checking against the council’s own calendar '
          + 'if something looks off.'));
    }
  }

  // A click anywhere else is a dismissal; without this the list stays open over
  // the answer it just produced.
  document.addEventListener('click', function (e) {
    if (!list.contains(e.target) && e.target !== streetInput) hideSuggestions();
  });
})();
