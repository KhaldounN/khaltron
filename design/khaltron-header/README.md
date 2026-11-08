# Khaltron 9000 — App Header (handoff)

This folder contains a finished, working header for the **Khaltron 9000** app (a laptop-activity monitor).
It's a mechanical raccoon robot gripping a steel ledge, watching the apps running "below" it.
Use this as the source of truth for the header and build the rest of the app's design around it.

Open `index.html` in a browser to see it live. Click **GAMING MODE** (top right).

## Folder contents

| File | What it is |
|---|---|
| `index.html` | Demo page that mounts the header. |
| `khaltron-header.css` | All styles, scoped under `.khaltron`. |
| `khaltron-header.js` | Dependency-free component (`window.KhaltronHeader`). Builds the DOM and runs the state machine. |
| `assets/khaltron-raccoon.jpg` | The robot artwork used in the header (2172×724, 3:1, optimized). |
| `assets/khaltron-raccoon-original.png` | The original full-quality artwork. |
| `screenshots/` | Monitor mode, gaming mode (warning) and gaming mode (frozen). |
| `reference/design-source.dc.html` | The original design file this was built from (reference only, not runnable on its own). |

## Usage

```html
<link rel="stylesheet" href="khaltron-header.css">
<script src="khaltron-header.js"></script>
<div id="header"></div>
<script>
  const header = KhaltronHeader.mount(document.getElementById('header'), {
    image: 'assets/khaltron-raccoon.jpg',
    processes: [                      // up to 6; load is 0–1
      { name: 'Chrome',  tag: 'BROWSER', load: 0.7 },
      { name: 'Slack',   tag: 'CHAT',    load: 0.34 },
      // ...
    ],
    startInGamingMode: false,
    onModeChange:  (mode)  => {},     // 'monitor' | 'gaming'
    onPhaseChange: (phase) => {},     // 'watch' | 'sweep' | 'pausing' | 'locked'
    onLocked: (processes) => {},      // sequence finished: actually pause these processes here
  });

  header.setProcesses(list);  // update cards with live data
  header.engage();            // start gaming mode
  header.disengage();         // back to monitor mode
  header.getState();          // { mode, phase, look }
  header.destroy();
</script>
```

Fonts: Orbitron (wordmark and button) and JetBrains Mono (everything else), from Google Fonts. See the `<link>` in `index.html`.

The header renders at a fixed native size of **1600 × 320 px** and scales down to fit its container's width, keeping that 5:1 shape.
All coordinates below are in that native space.

## Behavior

### Monitor mode (default)
- Cyan theme. The eyes glow and pulse softly.
- Every **1.8 s** the robot looks at a random app card. Its pupils shift slightly, a faint cyan scan beam from each eye points at that card, and the card gets a cyan highlight.
- Every card shows "MONITORED".

### Gaming mode (click the button): plays once, then freezes
1. **Engage (0 ms):** theme turns red. The scene gets a red color grade and darkens 30%, the camera pushes in 6% toward the eyes and shakes, a red vignette pulses, the eyes turn red with angry dark lids, the beams go solid red with a laser line, and the banner reads "GAMING MODE ENGAGED — ISSUING WARNINGS".
2. **Sweep:** the robot glares at each card in order (0 → 5). For each card: look (380 ms), then the card flashes red and shows "⚠ WARNED", then 260 ms before the next one. The card being looked at lifts up, gets red corner brackets and a blinking "TERMINATE?" badge. Cards it hasn't reached yet show "SCANNING…".
3. **Pausing (800 ms after the last warning):** the robot looks straight down, the beams widen to flood every card, and all cards flash and switch to "⏸ PAUSED". The banner reads "ALL NON-ESSENTIAL PROCESSES PAUSED".
4. **Locked (1.3 s later):** **everything stops.** No shaking, pulsing, flicker or blinking, and the dust freezes in mid-air. It stays red and stares down at the apps until the user exits. `onLocked` fires here, which is where the real app should pause the processes.

Clicking **EXIT GAMING MODE** at any point returns to monitor mode.
Timings are in `KhaltronHeader.TIMING`. `prefers-reduced-motion` turns off the looping animations.

## Layout spec (native 1600 × 320)

- **Artwork:** shown at 960 × 320, `left: 320px`. Its left and right 14% fade into the dark background (`radial-gradient(#15181D → #07080A)`). A steel ledge band continues the photo's ledge across the full width at `top: 263px; height: 57px`.
- **Robot eyes (overlay anchors):** left eye **(765, 115)**, right eye **(834, 112)**. The camera push-in uses origin (799, 114).
- **Brand (top-left, 28 px / 16 px):** "KHALTRON 9000" in Orbitron 800 24px, letter-spacing .08em. Below it, a mode line (status dot + text, 12px, .18em). In gaming mode, a red warning banner sits below that.
- **Toggle button (top-right, 28 px / 16 px):** pill, 44 px tall, 1 px accent border, Orbitron 600 13px.
- **App cards:** 6 fixed slots, each 120 × 48 at `top: 268px`, sitting on the ledge between and around the robot's hands:
  slot lefts = **96, 226, 681, 811, 1254, 1384**. Each card has the name (12px, 600), a tag (9px), a 4 px load bar and a status line (9px caps).
- **Beam angles per slot (from the eyes):** 74.5°, 70.9°, 18°, −22°, −70.9°, −74.6°. If you move the slots, recompute these with `atan(dx/dy)` from the eye midpoint (799, 114) to the card's center.

## Design tokens

| Token | Value | Use |
|---|---|---|
| Accent (monitor) | `#35E0FF` | eyes, beams, borders, dots, load bars |
| Accent (gaming) | `#FF3B3B` | same elements in gaming mode |
| Background | `#05070A` / `#07080A` | page and header background |
| Text primary | `#F2F7FB` | wordmark, card names |
| Text secondary | `#B4C3D1`, `#93A5B6` | mode line, tags |
| Card surface | `rgba(6,10,16,.78)` + `backdrop-filter: blur(4px)` | monitor-mode cards |
| Card surface (gaming) | `rgba(26,6,8,.82)` | gaming-mode cards |
| Card radius | 9px | |
| Status colors | monitored `#7FE9FF` · scanning `#C2AEAE` · warned `#FF7A7A` · paused `#FFB3B3` | |
| Fonts | Orbitron 600/800 (display), JetBrains Mono 400/600 (UI) | |

The rest of the app should match: a near-black background, cyan as the single accent color with red reserved for gaming or alert states, monospace caps labels with wide letter-spacing, and thin 1 px glowing borders.

## Notes for the developer
- The app names in the demo are placeholders. Feed real running processes through `setProcesses()`. Only 6 fit, so pick the top 6 by CPU or memory.
- The card positions are tuned to the artwork, so the hands stay visible. If you swap the artwork, re-measure the eye positions and the hand gaps.
- The header is purely visual. Actually pausing or terminating processes is up to the app, using the `onLocked` callback.
