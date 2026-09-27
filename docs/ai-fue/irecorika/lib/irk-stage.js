/* iRecorika 演奏画面の共通部品
 *
 * 画面を3つに分ける。中央は笛の板の範囲（板を画面に置くなら、その真下）で、12本の笛の帯を描く。
 * 左右は板の外側で、指で触れる操作面（パッド）を置く。
 *
 * パッドの数は、画面に触れる指の数で決まる。画面が上向きなら上側の8本の指が触れるので
 * 片側4つ、下向きなら親指だけが触れるので片側2つにする。アプリは片側4つずつの機能を、
 * 大事な順に並べて渡す。親指の持ち方では、それぞれの先頭の2つだけが出る。
 *
 * 使い方
 *   const stage = IRKStage.create({
 *     title: "光る笛", desc: "説明",
 *     pads: { left: [{id:"a", label:"…", sub:"…"}, …], right: […] },
 *     onPad(id, down, info) {}, onPadMove(id, info) {},
 *     panel: "<fieldset>…アプリ固有の設定…</fieldset>",
 *     onStart: async () => {},       // 「始める」を押したとき（音とマイクを開く）
 *     draw(g, geo, now) {},           // 帯の上に独自の描画をする
 *   });
 */
(function (root) {
  "use strict";
  const IRK = root.IRK;

  function h(tag, attrs, html) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === "class") e.className = attrs[k];
      else if (k === "style") e.style.cssText = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function create(opt) {
    const settings = IRK.load();
    const fingers = IRK.fingerCount(settings);
    document.body.classList.add("irk-app");
    document.title = opt.title + " — iRecorika " + IRK.VERSION;

    const stageEl = h("div", { id: "irk-stage" });
    const canvas = h("canvas", { id: "irk-canvas" });
    const center = h("div", { id: "irk-center" });
    stageEl.append(canvas, center);
    document.body.appendChild(stageEl);

    const rotate = h("div", { id: "irk-rotate" },
      "<div style='font-size:40px'>⟲</div><div>スマートフォンを<b>横向き</b>にしてください。</div>"
      + "<div class='note'>自動回転が止まっている場合は、クイック設定で回転を許可してください。</div>"
      + "<button class='btn small' id='irk-allow-portrait'>縦のまま使う</button>");
    document.body.appendChild(rotate);
    rotate.querySelector("#irk-allow-portrait").onclick = () => document.body.classList.add("allow-portrait");

    // ---------------------------------------------------------------- 設定の画面（開始と一時停止）
    const panel = h("div", { id: "irk-panel" });
    panel.innerHTML =
      "<h1>" + opt.title + "</h1><div class='ver'>iRecorika " + IRK.VERSION + "</div>"
      + (opt.desc ? "<p>" + opt.desc + "</p>" : "")
      + "<p class='note'>いまの持ち方：" + IRK.describe(settings) + "（<a href='setup.html'>変える</a>）</p>"
      + "<div class='row'><button class='btn primary' id='irk-go'>始める</button>"
      + "<a class='btn' href='index.html'>一覧へ戻る</a>"
      + (IRK.param("sim") === "1" ? "<span class='note'>模擬入力：板の上を押すか、キーの1〜0・-・^ で笛を鳴らせます</span>" : "")
      + "</div>"
      + (opt.panel || "")
      + "<fieldset><legend>共通の設定</legend>"
      + "<div class='row'><label>音量 <input type='range' id='irk-vol' min='0' max='1' step='0.05'></label>"
      + "<label><input type='checkbox' id='irk-guard'> 保護（スマートフォンの音から笛の音域を抜き、マイクへの回り込みを防ぐ）</label></div>"
      + "</fieldset>";
    document.body.appendChild(panel);
    const vol = panel.querySelector("#irk-vol");
    vol.value = settings.volume;
    vol.oninput = () => { IRK.update({ volume: parseFloat(vol.value) }); if (root.IRKAudio && started) root.IRKAudio.bus().setVolume(parseFloat(vol.value)); };
    const guard = panel.querySelector("#irk-guard");
    guard.checked = settings.guard;
    guard.onchange = () => { IRK.update({ guard: guard.checked }); if (root.IRKAudio && started) root.IRKAudio.bus().setGuard(guard.checked); };

    let started = false;
    panel.querySelector("#irk-go").onclick = async () => {
      await IRK.enterFullscreen();
      IRK.keepAwake();
      if (root.IRKAudio) root.IRKAudio.bus();
      if (!started && opt.onStart) {
        const btn = panel.querySelector("#irk-go");
        btn.textContent = "準備中…";
        try { await opt.onStart(); } catch (e) { console.error(e); }
      }
      started = true;
      panel.querySelector("#irk-go").textContent = "演奏に戻る";
      panel.classList.add("hidden");
      layout();
      if (opt.onResume) opt.onResume();
    };
    function openMenu() {
      panel.classList.remove("hidden");
      if (opt.onPause) opt.onPause();
    }

    // ---------------------------------------------------------------- 配置
    const zones = { left: h("div", { class: "irk-zone" }), right: h("div", { class: "irk-zone" }) };
    stageEl.append(zones.left, zones.right);
    let geo = null;
    const padEls = {};         // id -> 要素
    const padDefs = {};        // id -> 定義
    const padState = {};       // id -> 押されているか
    const meter = h("div", { class: "irk-meter" }, "<i></i>");
    const status = h("span", {}, "");

    function padsFor(side) {
      const list = (opt.pads && opt.pads[side]) || [];
      return fingers === 2 ? list.slice(0, 2) : list.slice(0, 4);
    }

    function buildZone(side, list, withMenu) {
      const z = zones[side];
      z.innerHTML = "";
      const head = h("div", { class: "irk-zone-head" });
      if (withMenu) {
        const mb = h("button", { class: "irk-menu-btn", title: "設定" }, "≡");
        mb.onclick = openMenu;
        head.append(mb, h("span", {}, opt.title));
      } else {
        head.append(meter, status);
      }
      z.appendChild(head);
      const box = h("div", { class: "irk-pads" });
      const n = list.length;
      const layoutMode = settings.padLayout;
      if (n <= 2) { box.style.gridTemplateRows = "repeat(" + Math.max(1, n) + ",1fr)"; }
      else if (layoutMode === "cols") { box.style.gridTemplateColumns = "repeat(" + n + ",1fr)"; }
      else if (layoutMode === "grid") { box.style.gridTemplateColumns = "1fr 1fr"; box.style.gridTemplateRows = "repeat(" + Math.ceil(n / 2) + ",1fr)"; }
      else if (n > 4) { box.style.gridTemplateColumns = "1fr 1fr"; box.style.gridTemplateRows = "repeat(" + Math.ceil(n / 2) + ",1fr)"; }
      else { box.style.gridTemplateRows = "repeat(" + n + ",1fr)"; }
      for (const p of list) {
        const e = h("div", { class: "irk-pad" + (p.empty ? " empty" : "") }, "<div>" + (p.label || "") + "</div>" + (p.sub ? "<div class='sub'>" + p.sub + "</div>" : ""));
        e.dataset.id = p.id;
        padEls[p.id] = e; padDefs[p.id] = p;
        if (padState[p.id]) e.classList.add("on");
        box.appendChild(e);
      }
      z.appendChild(box);
      attachPointer(box);
    }

    function layout() {
      const w = window.innerWidth, hgt = window.innerHeight;
      document.body.classList.toggle("portrait", !IRK.isLandscape());
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(hgt * dpr);
      geo = IRK.geometry(IRK.load(), w, hgt);
      const minW = 48;   // これより狭い側には操作面を置かない（約8mm）
      let L = padsFor("left"), R = padsFor("right");
      let leftOk = geo.left.x1 - geo.left.x0 >= minW, rightOk = geo.right.x1 - geo.right.x0 >= minW;
      if (!leftOk && rightOk) { R = R.concat(L); L = []; }
      if (!rightOk && leftOk) { L = L.concat(R); R = []; }
      zones.left.style.left = geo.left.x0 + "px"; zones.left.style.width = (geo.left.x1 - geo.left.x0) + "px";
      zones.right.style.left = geo.right.x0 + "px"; zones.right.style.width = (geo.right.x1 - geo.right.x0) + "px";
      zones.left.style.display = leftOk ? "" : "none";
      zones.right.style.display = rightOk ? "" : "none";
      buildZone("left", L, leftOk || !rightOk);
      buildZone("right", R, !leftOk && rightOk);
      if (!leftOk && rightOk) {
        // 右側だけのときは、見出しに設定のボタンと音量計を並べる
        zones.right.querySelector(".irk-zone-head").append(meter, status);
      } else if (leftOk && !rightOk) {
        zones.left.querySelector(".irk-zone-head").append(meter, status);
      }
      center.style.left = Math.max(0, geo.plate.x0) + "px";
      center.style.width = Math.max(0, Math.min(w, geo.plate.x1) - Math.max(0, geo.plate.x0)) + "px";
      if (opt.onLayout) opt.onLayout(geo);
    }
    window.addEventListener("resize", layout);
    if (screen.orientation) screen.orientation.addEventListener("change", () => setTimeout(layout, 100));

    // ---------------------------------------------------------------- 指の追跡
    // 指ごとに、いまどのパッドの上にあるかを覚える。指を滑らせて隣のパッドへ移ると、
    // 前のパッドを離して次のパッドを押したことにする（親指で滑らせて切り替えられる）
    const pointers = new Map();   // pointerId -> padId
    function padAt(x, y) {
      const e = document.elementFromPoint(x, y);
      const p = e && e.closest && e.closest(".irk-pad");
      return p && !p.classList.contains("empty") ? p.dataset.id : null;
    }
    function info(id, ev) {
      const r = padEls[id].getBoundingClientRect();
      return { x: (ev.clientX - r.left) / r.width, y: (ev.clientY - r.top) / r.height, pointerId: ev.pointerId };
    }
    function press(id, down, ev) {
      const def = padDefs[id];
      if (!def) return;
      if (def.toggle) {
        if (!down) return;
        padState[id] = !padState[id];
        padEls[id].classList.toggle("on", padState[id]);
        if (opt.onPad) opt.onPad(id, padState[id], info(id, ev));
      } else {
        // 同じパッドを2本の指で押していることもあるので、押している指の数で判定する
        let n = 0; pointers.forEach(v => { if (v === id) n++; });
        const was = !!padState[id];
        padState[id] = n > 0;
        padEls[id].classList.toggle("on", padState[id]);
        if (was !== padState[id] && opt.onPad) opt.onPad(id, padState[id], info(id, ev));
      }
      if (down && navigator.vibrate && settings.vibrate !== false) navigator.vibrate(6);
    }
    function attachPointer(box) {
      box.addEventListener("pointerdown", ev => {
        ev.preventDefault();
        try { box.releasePointerCapture(ev.pointerId); } catch (_) {}
        const id = padAt(ev.clientX, ev.clientY);
        pointers.set(ev.pointerId, id);
        if (id) press(id, true, ev);
      });
    }
    document.addEventListener("pointermove", ev => {
      if (!pointers.has(ev.pointerId)) return;
      const old = pointers.get(ev.pointerId);
      const id = padAt(ev.clientX, ev.clientY);
      if (id !== old) {
        pointers.set(ev.pointerId, id);
        if (old) press(old, false, ev);
        if (id) press(id, true, ev);
      } else if (id && opt.onPadMove) {
        opt.onPadMove(id, info(id, ev));
      }
    });
    const up = ev => {
      if (!pointers.has(ev.pointerId)) return;
      const old = pointers.get(ev.pointerId);
      pointers.delete(ev.pointerId);
      if (old) press(old, false, ev);
    };
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", up);

    // 模擬入力：板の範囲を押すと、その笛を吹いたことにする
    let detector = null;
    let simPointer = null;
    canvas.addEventListener("pointerdown", ev => {
      if (opt.onPlatePointer) opt.onPlatePointer("down", ev, geo);
      if (!detector || !detector.sim) return;
      const slot = IRK.slotAtX(geo, ev.clientX);
      if (slot >= 0) { simPointer = ev.pointerId; detector.simOn(slot); }
    });
    canvas.addEventListener("pointermove", ev => {
      if (opt.onPlatePointer) opt.onPlatePointer("move", ev, geo);
      if (!detector || !detector.sim || simPointer !== ev.pointerId) return;
      const slot = IRK.slotAtX(geo, ev.clientX);
      if (slot >= 0) detector.simOn(slot);
    });
    const simUp = ev => {
      if (opt.onPlatePointer) opt.onPlatePointer("up", ev, geo);
      if (simPointer === ev.pointerId) { simPointer = null; detector.simOff(); }
    };
    canvas.addEventListener("pointerup", simUp);
    canvas.addEventListener("pointercancel", simUp);

    // ---------------------------------------------------------------- 描画
    const hold = new Float32Array(12), flash = new Float32Array(12);
    const holdColor = new Array(12).fill(null);
    const marks = new Array(12).fill(null);   // {color, alpha, label}
    let showLanes = opt.showLanes !== false;

    function draw(now) {
      const g = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const W = canvas.width / dpr, H = canvas.height / dpr;
      g.fillStyle = "#07080c"; g.fillRect(0, 0, W, H);
      if (geo && showLanes) {
        const s = settings;
        for (const l of geo.lanes) {
          const i = l.slot;
          const w = l.x1 - l.x0;
          // 帯の地。板を画面に置くときは、笛の真下がうっすら光る
          g.fillStyle = IRK.slotColor(i, s.placement === "screen" ? 0.10 : 0.06);
          g.fillRect(l.x0 + 1, 0, w - 2, H);
          const m = marks[i];
          if (m) {
            g.fillStyle = m.color || "rgba(255,255,255,0.3)";
            g.globalAlpha = m.alpha === undefined ? 0.35 : m.alpha;
            g.fillRect(l.x0 + 1, 0, w - 2, H);
            g.globalAlpha = 1;
          }
          const v = Math.max(hold[i], flash[i]);
          if (v > 0.01) {
            const col = holdColor[i] || IRK.slotColor(i, 1);
            g.save();
            g.globalAlpha = Math.min(1, v);
            g.shadowColor = col; g.shadowBlur = 30 * v;
            g.fillStyle = col;
            g.fillRect(l.x0 + 1, 0, w - 2, H);
            g.restore();
          }
          flash[i] *= 0.9;
          if (s.showNames !== "none") {
            g.fillStyle = v > 0.5 ? "#000" : "rgba(238,240,246,0.55)";
            g.font = "11px sans-serif"; g.textAlign = "center";
            const nm = IRK.noteName(IRK.slotToMidi(i), s.showNames);
            // 音名は帯の上端（口から遠い側）に書き、中央の文字と重ならないようにする
            g.fillText(nm, l.x, 16);
            if (m && m.label) { g.fillStyle = "#fff"; g.font = "bold 13px sans-serif"; g.fillText(m.label, l.x, 34); }
          }
        }
        // 板の縁
        g.strokeStyle = "rgba(255,255,255,0.12)"; g.lineWidth = 1;
        g.strokeRect(geo.plate.x0 + 0.5, 0.5, geo.plate.x1 - geo.plate.x0 - 1, H - 1);
      }
      if (opt.draw && geo) opt.draw(g, geo, now);
      requestAnimationFrame(draw);
    }

    layout();
    requestAnimationFrame(draw);

    const api = {
      get geo() { return geo; },
      settings, fingers,
      layout,
      hold(slot, v, color) { if (slot >= 0 && slot < 12) { hold[slot] = v; holdColor[slot] = color || null; } },
      clearHold() { hold.fill(0); holdColor.fill(null); },
      flash(slot, v) { if (slot >= 0 && slot < 12) flash[slot] = Math.max(flash[slot], v === undefined ? 1 : v); },
      mark(slot, m) { if (slot >= 0 && slot < 12) marks[slot] = m; },
      clearMarks() { marks.fill(null); },
      setCenter(html) { if (center._html !== html) { center.innerHTML = html; center._html = html; } },
      setStatus(t) { status.textContent = t; },
      setMeter(v) { meter.firstChild.style.width = Math.round(Math.max(0, Math.min(1, v)) * 100) + "%"; },
      setPad(id, label, sub) { const e = padEls[id]; if (!e) return; if (padDefs[id] && padDefs[id].label === label && (padDefs[id].sub || "") === (sub || "")) return; e.innerHTML = "<div>" + label + "</div>" + (sub ? "<div class='sub'>" + sub + "</div>" : ""); if (padDefs[id]) { padDefs[id].label = label; padDefs[id].sub = sub; } },
      setPadOn(id, on) { padState[id] = !!on; if (padEls[id]) padEls[id].classList.toggle("on", !!on); },
      setPadLit(id, on) { if (padEls[id]) padEls[id].classList.toggle("lit", !!on); },
      padOn: id => !!padState[id],
      hasPad: id => !!padEls[id],
      setPads(pads) { opt.pads = pads; layout(); },
      attachDetector(d) {
        detector = d;
        d.on("frame", fr => {
          api.setMeter(fr.cur ? 0.35 + 0.65 * fr.strength : Math.max(0, Math.min(0.3, (fr.level - (fr.noise || -100)) / 40)));
        });
      },
      openMenu, panel, started: () => started,
      showLanes(v) { showLanes = v; },
    };
    return api;
  }

  root.IRKStage = { create: create, h: h };
})(typeof globalThis !== "undefined" ? globalThis : this);
