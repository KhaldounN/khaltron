/* Khaltron 9000 top bar — dependency-free component (native 1920x180, scales to container width).
 *
 *   const header = KhaltronHeader.mount(document.getElementById('header'), {
 *     image: 'assets/khaltron-raccoon.jpg',
 *     processes: [{ name: 'Chrome', tag: 'BROWSER', load: 0.7 }, ...up to 6],
 *     onModeChange: (mode) => {},      // 'monitor' | 'gaming'
 *     onPhaseChange: (phase) => {},    // 'watch' | 'sweep' | 'pausing' | 'locked'
 *     onLocked: (processes) => {},     // gaming sequence finished: pause the real processes here
 *     sound: 'assets/khaltron-gaming-mode.mp3', // played when gaming mode turns on; false = silent
 *     volume: 0.8,
 *   });
 *   header.setProcesses([...]); header.engage(); header.disengage(); header.destroy();
 */
(function (global) {
  'use strict';

  var DEFAULT_PROCESSES = [
    { name: 'Chrome', tag: 'BROWSER', load: 0.7 },
    { name: 'Slack', tag: 'CHAT', load: 0.34 },
    { name: 'Outlook', tag: 'MAIL', load: 0.34 },
    { name: 'Teams', tag: 'MEETINGS', load: 0.52 },
    { name: 'OneDrive', tag: 'SYNC', load: 0.18 },
    { name: 'Spotify', tag: 'MUSIC', load: 0.18 }
  ];

  // Timings (ms) for the gaming-mode sequence and idle scanning.
  var TIMING = { idleStep: 1800, firstIdle: 1200, sweepStart: 450, lookToWarn: 380, warnToNext: 260, afterLastWarn: 800, pausingToLocked: 1300 };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  var ICON_WARN = '<svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3z"/><path d="M12 10v5"/></svg>';
  var ICON_PAUSE = '<svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M9 5v14"/><path d="M15 5v14"/></svg>';
  var ICON_PAD = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="11" rx="5"/><path d="M7 11v3M5.5 12.5h3"/><circle cx="16" cy="11.5" r="1"/><circle cx="18" cy="13.5" r="1"/></svg>';

  function motes() {
    var pts = [[300,150,1.6,-1,11],[520,120,1.2,-4,9],[700,100,1.8,-7,12],[1240,110,1.3,-2,10],[1380,140,1.5,-5,13],[1560,160,1.2,-8,9],[200,165,1.4,-3,12],[1700,150,1.6,-6,11],[620,160,1.3,-2.5,10],[1100,80,1.1,-6.5,9],[1840,165,1.3,-1.5,11],[820,90,1,-7.5,10]];
    return pts.map(function (p) { return '<circle class="mote" cx="' + p[0] + '" cy="' + p[1] + '" r="' + p[2] + '" style="animation-delay:' + p[3] + 's;animation-duration:' + p[4] + 's"/>'; }).join('');
  }

  function template(uid, image) {
    var f = function (n) { return 'kh-' + n + '-' + uid; };
    return '' +
      '<div class="layer cam" style="z-index:1"><div class="layer shake">' +
        '<img class="photo" src="' + esc(image) + '" alt="Khaltron 9000, a mechanical raccoon robot with glowing eyes, gripping a steel ledge and looking down">' +
        '<div class="layer darken"></div><div class="layer grade"></div>' +
        '<svg class="layer" aria-hidden="true" width="1920" height="180" viewBox="0 0 1920 180"><defs>' +
          '<filter id="' + f('eg') + '" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="6"/></filter>' +
          '<filter id="' + f('eg2') + '" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
          '<filter id="' + f('lid') + '" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="2"/></filter></defs>' +
          '<circle class="eyeglow tc" cx="931" cy="94" r="10.5" filter="url(#' + f('eg') + ')"/><circle class="eyeglow tc" cx="987" cy="91" r="10.5" filter="url(#' + f('eg') + ')"/>' +
          '<g class="redeye"><circle cx="931" cy="94" r="5.7" fill="#0A0204"/><circle cx="987" cy="91" r="5.7" fill="#0A0204"/>' +
            '<circle cx="931" cy="94" r="4.5" fill="none" stroke="#FF3B3B" stroke-width="1.4" filter="url(#' + f('eg2') + ')"/><circle cx="987" cy="91" r="4.5" fill="none" stroke="#FF3B3B" stroke-width="1.4" filter="url(#' + f('eg2') + ')"/></g>' +
          '<g class="pupil"><circle class="tc" cx="931" cy="94" r="2.6" filter="url(#' + f('eg2') + ')"/><circle class="tc" cx="987" cy="91" r="2.6" filter="url(#' + f('eg2') + ')"/>' +
            '<circle cx="931" cy="94" r="1.2" fill="#fff"/><circle cx="987" cy="91" r="1.2" fill="#fff"/></g>' +
          '<polygon class="lid" points="917,80 946.4,80 946.4,92.6 917,85.2" fill="#08090B" filter="url(#' + f('lid') + ')"/>' +
          '<polygon class="lid" points="972.7,78.2 1001.9,78.2 1001.9,83.4 972.7,90.6" fill="#08090B" filter="url(#' + f('lid') + ')"/>' +
        '</svg></div></div>' +
      '<svg class="layer" aria-hidden="true" width="1920" height="180" viewBox="0 0 1920 180" style="z-index:2;pointer-events:none"><defs>' +
        '<linearGradient id="' + f('beam') + '" gradientUnits="userSpaceOnUse" x1="960" y1="92" x2="960" y2="1092"><stop offset="0%" class="sc" stop-opacity=".4"/><stop offset="45%" class="sc" stop-opacity=".12"/><stop offset="100%" class="sc" stop-opacity="0"/></linearGradient>' +
        '<filter id="' + f('bb') + '" x="-50%" y="-10%" width="200%" height="120%"><feGaussianBlur stdDeviation="5"/></filter>' +
        '<filter id="' + f('lg') + '" x="-200%" y="-10%" width="500%" height="120%"><feGaussianBlur in="SourceGraphic" stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>' +
        '<g class="beam bl"><polygon class="beam-cone" points="931,98 911,1098 951,1098" fill="url(#' + f('beam') + ')" filter="url(#' + f('bb') + ')"/><line class="laser" x1="931" y1="102" x2="931" y2="1060" stroke="#FF6A6A" stroke-width="2" filter="url(#' + f('lg') + ')"/></g>' +
        '<g class="beam br"><polygon class="beam-cone" points="987,95 967,1095 1007,1095" fill="url(#' + f('beam') + ')" filter="url(#' + f('bb') + ')"/><line class="laser" x1="987" y1="99" x2="987" y2="1060" stroke="#FF6A6A" stroke-width="2" filter="url(#' + f('lg') + ')"/></g>' +
        '<g>' + motes() + '</g></svg>' +
      '<div class="brand"><div class="wordmark">KHALTRON 9000</div>' +
        '<div class="mode-line"><span class="dot"></span><span data-kh="modeName"></span></div>' +
        '<div class="banner">' + ICON_WARN.replace(/12/g, '14') + '<span data-kh="banner"></span></div></div>' +
      '<button class="toggle" type="button" aria-pressed="false">' + ICON_PAD + '<span data-kh="btn">GAMING MODE</span></button>' +
      '<div class="layer" data-kh="cards" style="z-index:3"></div>' +
      '<div class="layer vignette"></div>' +
      '<svg class="layer grain" aria-hidden="true" width="1920" height="180" viewBox="0 0 1920 180"><filter id="' + f('film') + '"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="1920" height="180" filter="url(#' + f('film') + ')"/></svg>';
  }

  function cardHTML(p, i) {
    var load = Math.max(0, Math.min(1, Number(p.load) || 0));
    return '<div class="card slot-' + i + ' s-monitored" data-slot="' + i + '">' +
      '<div class="card-head"><span class="pn">' + esc(p.name) + '</span><span class="tag">' + esc(p.tag || '') + '</span></div>' +
      '<div class="bar"><div class="fill" style="width:' + Math.round(load * 100) + '%"></div></div>' +
      '<div class="st st-monitored"><span class="dot"></span><span>MONITORED</span></div>' +
      '<div class="st st-scanning"><span>SCANNING…</span></div>' +
      '<div class="st st-warned">' + ICON_WARN + '<span>WARNED</span></div>' +
      '<div class="st st-paused">' + ICON_PAUSE + '<span>PAUSED</span></div>' +
      '<div class="lock">TERMINATE?</div></div>';
  }

  var uidCounter = 0;

  function mount(container, opts) {
    opts = opts || {};
    var uid = ++uidCounter;
    var processes = (opts.processes || DEFAULT_PROCESSES).slice(0, 6);
    var state = { hunt: false, phase: 'watch', look: 2, warned: -1 };
    var timer = null, alive = true;

    var fit = document.createElement('div');
    fit.className = 'khaltron-fit';
    var root = document.createElement('div');
    root.className = 'khaltron';
    root.innerHTML = template(uid, opts.image || 'assets/khaltron-raccoon.jpg');
    fit.appendChild(root);
    container.appendChild(fit);

    var $ = function (k) { return root.querySelector('[data-kh="' + k + '"]'); };
    var btn = root.querySelector('.toggle');

    // Gaming-mode activation sound (plays on the click that turns it on).
    var sfx = null;
    if (opts.sound !== false && typeof Audio !== 'undefined') {
      sfx = new Audio(opts.sound || 'assets/khaltron-gaming-mode.mp3');
      sfx.preload = 'auto';
    }
    var volume = opts.volume == null ? 0.8 : opts.volume;
    function playSfx() {
      if (!sfx) return;
      try { sfx.volume = volume; sfx.currentTime = 0; var pr = sfx.play(); if (pr && pr.catch) pr.catch(function () {}); } catch (e) {}
    }

    // Scale the 1920x180 canvas to the container width.
    function resize() {
      var s = fit.clientWidth / 1920 || 1;
      root.style.transform = 'scale(' + s + ')';
      fit.style.height = (180 * s) + 'px';
    }
    var ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    if (ro) ro.observe(fit); else global.addEventListener('resize', resize);
    resize();

    function renderCards() {
      $('cards').innerHTML = processes.map(cardHTML).join('');
    }

    function statusOf(i) {
      if (state.phase === 'watch') return 'monitored';
      if (state.phase === 'sweep') return i <= state.warned ? 'warned' : 'scanning';
      return 'paused';
    }

    function render() {
      var ph = state.phase;
      root.className = 'khaltron ' + (state.hunt ? 'mode-hunt' : 'mode-watch') + ' phase-' + ph + ' look-' + state.look;
      $('modeName').textContent = ph === 'watch' ? 'MONITOR MODE // WATCHING' : (ph === 'sweep' ? 'GAMING MODE // ISSUING WARNINGS' : 'GAMING MODE // ALL PROCESSES PAUSED');
      $('banner').textContent = ph === 'sweep' ? 'GAMING MODE ENGAGED — ISSUING WARNINGS' : 'ALL NON-ESSENTIAL PROCESSES PAUSED';
      $('btn').textContent = state.hunt ? 'EXIT GAMING MODE' : 'GAMING MODE';
      btn.setAttribute('aria-pressed', state.hunt ? 'true' : 'false');
      var cards = $('cards').children;
      for (var i = 0; i < cards.length; i++) {
        var targeted = (ph === 'watch' || ph === 'sweep') && i === state.look;
        var cls = 'card slot-' + i + ' s-' + statusOf(i) + (targeted ? ' targeted' : '');
        if (cards[i].className !== cls) cards[i].className = cls;
      }
    }

    function set(patch) {
      var prevPhase = state.phase, prevHunt = state.hunt;
      for (var k in patch) state[k] = patch[k];
      render();
      if (state.hunt !== prevHunt && opts.onModeChange) opts.onModeChange(state.hunt ? 'gaming' : 'monitor');
      if (state.phase !== prevPhase) {
        if (opts.onPhaseChange) opts.onPhaseChange(state.phase);
        if (state.phase === 'locked' && opts.onLocked) opts.onLocked(processes.slice());
      }
    }

    function later(fn, ms) { clearTimeout(timer); timer = setTimeout(function () { if (alive) fn(); }, ms); }

    function idle(delay) {
      var step = function () {
        if (state.phase !== 'watch') return;
        var n = state.look, count = Math.max(1, processes.length);
        if (count > 1) while (n === state.look) n = Math.floor(Math.random() * count);
        set({ look: n });
        later(step, TIMING.idleStep);
      };
      later(step, delay);
    }

    function engage() {
      if (state.hunt) return;
      playSfx();
      set({ hunt: true, phase: 'sweep', look: 0, warned: -1 });
      var last = processes.length - 1;
      var sweep = function (k) {
        set({ look: k });
        later(function () {
          set({ warned: k });
          if (k < last) later(function () { sweep(k + 1); }, TIMING.warnToNext);
          else later(function () {
            set({ phase: 'pausing', look: 'c' });
            later(function () { set({ phase: 'locked' }); }, TIMING.pausingToLocked);
          }, TIMING.afterLastWarn);
        }, TIMING.lookToWarn);
      };
      later(function () { sweep(0); }, TIMING.sweepStart);
    }

    function disengage() {
      set({ hunt: false, phase: 'watch', warned: -1, look: 2 });
      idle(TIMING.firstIdle);
    }

    btn.addEventListener('click', function () { state.hunt ? disengage() : engage(); });

    renderCards();
    render();
    if (opts.startInGamingMode) engage(); else idle(TIMING.firstIdle);

    return {
      engage: engage,
      disengage: disengage,
      setVolume: function (v) { volume = Math.max(0, Math.min(1, v)); },
      setSoundEnabled: function (on) { if (!on) sfx = null; else if (!sfx && typeof Audio !== 'undefined') { sfx = new Audio(opts.sound || 'assets/khaltron-gaming-mode.mp3'); } },
      setProcesses: function (list) { processes = (list || []).slice(0, 6); renderCards(); render(); },
      getState: function () { return { mode: state.hunt ? 'gaming' : 'monitor', phase: state.phase, look: state.look }; },
      destroy: function () { alive = false; if (sfx) { try { sfx.pause(); } catch (e) {} } clearTimeout(timer); if (ro) ro.disconnect(); else global.removeEventListener('resize', resize); fit.remove(); }
    };
  }

  global.KhaltronHeader = { mount: mount, DEFAULT_PROCESSES: DEFAULT_PROCESSES, TIMING: TIMING };
})(typeof window !== 'undefined' ? window : this);
