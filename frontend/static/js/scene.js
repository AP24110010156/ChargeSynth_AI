'use strict';
/* Theme-matched 3D EV asset with restrained continuous cable-energy lines. */
(() => {
  const canvas = document.getElementById('energyScene');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const vehicle = new Image();
  vehicle.decoding = 'async';
  vehicle.src = '/static/assets/hero-ev-charger.png';

  let width = 400;
  let height = 300;
  let visible = true;
  let ready = false;
  let frame = 0;
  let last = 0;
  let elapsed = 0;

  function cubicPoint(t, start, controlA, controlB, end) {
    const u = 1 - t;
    return {
      x: u ** 3 * start.x + 3 * u ** 2 * t * controlA.x + 3 * u * t ** 2 * controlB.x + t ** 3 * end.x,
      y: u ** 3 * start.y + 3 * u ** 2 * t * controlA.y + 3 * u * t ** 2 * controlB.y + t ** 3 * end.y,
    };
  }

  function imageLayout() {
    const naturalRatio = vehicle.naturalWidth / vehicle.naturalHeight || 2.49;
    const drawWidth = Math.min(width * .96, height * 1.92);
    const drawHeight = drawWidth / naturalRatio;
    return {
      x: (width - drawWidth) / 2,
      y: (height - drawHeight) / 2 + height * .025,
      width: drawWidth,
      height: drawHeight,
    };
  }

  function assetPoint(layout, x, y) {
    return { x: layout.x + layout.width * x, y: layout.y + layout.height * y };
  }

  function drawEnergyLines(layout, time) {
    const start = assetPoint(layout, .866, .61);
    const controlA = assetPoint(layout, .855, .96);
    const controlB = assetPoint(layout, .755, .99);
    const end = assetPoint(layout, .704, .565);

    const streams = [
      { offset: -2.2, phase: .2, speed: 3.5, alpha: .38, width: 1.0 },
      { offset: -.7, phase: 1.8, speed: 4.2, alpha: .62, width: 1.35 },
      { offset: .8, phase: 3.6, speed: 3.8, alpha: .52, width: 1.15 },
      { offset: 2.1, phase: 5.1, speed: 4.5, alpha: .32, width: .9 },
    ];

    for (const stream of streams) {
      ctx.beginPath();
      for (let step = 0; step <= 52; step++) {
        const progress = step / 52;
        const point = cubicPoint(progress, start, controlA, controlB, end);
        const next = cubicPoint(Math.min(1, progress + .012), start, controlA, controlB, end);
        const length = Math.hypot(next.x - point.x, next.y - point.y) || 1;
        const normalX = -(next.y - point.y) / length;
        const normalY = (next.x - point.x) / length;
        const taper = Math.sin(Math.PI * progress);
        const wave = stream.offset + Math.sin(progress * 22 - time * stream.speed + stream.phase) * 1.35 * taper;
        const x = point.x + normalX * wave;
        const y = point.y + normalY * wave;
        if (step === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      const pulse = .78 + .22 * Math.sin(time * 2.2 + stream.phase);
      ctx.strokeStyle = `rgba(166,198,151,${stream.alpha * pulse})`;
      ctx.lineWidth = stream.width;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.shadowColor = 'rgba(148,183,133,.55)';
      ctx.shadowBlur = 5;
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
  }

  function draw(time) {
    ctx.clearRect(0, 0, width, height);
    if (!ready) return;
    const layout = imageLayout();
    ctx.drawImage(vehicle, layout.x, layout.y, layout.width, layout.height);
    drawEnergyLines(layout, time);
  }

  function stop() {
    cancelAnimationFrame(frame);
    frame = 0;
    last = 0;
  }

  function tick(now) {
    frame = 0;
    if (!visible || document.hidden || reducedMotion.matches) {
      last = 0;
      return;
    }
    if (now - last >= 1000 / 30) {
      elapsed += last ? Math.min((now - last) / 1000, .1) : 0;
      last = now;
      draw(elapsed);
    }
    frame = requestAnimationFrame(tick);
  }

  function start() {
    if (!ready) return;
    if (reducedMotion.matches) {
      stop();
      draw(0);
      return;
    }
    if (!frame && visible && !document.hidden) frame = requestAnimationFrame(tick);
  }

  vehicle.addEventListener('load', () => {
    ready = true;
    draw(0);
    start();
  });

  const resizeObserver = new ResizeObserver(() => {
    const box = canvas.getBoundingClientRect();
    width = box.width;
    height = box.height;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw(elapsed);
    start();
  });
  resizeObserver.observe(canvas);

  const intersectionObserver = new IntersectionObserver(entries => {
    visible = Boolean(entries[0]?.isIntersecting);
    if (visible) start(); else stop();
  }, { threshold: 0 });
  intersectionObserver.observe(canvas);

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop(); else start();
  });
  reducedMotion.addEventListener('change', () => {
    stop();
    draw(0);
    start();
  });
})();
