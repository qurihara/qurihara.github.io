/* iRecorika 共通部品（設定・笛の並び・音名・全画面）
 *
 * すべてのアプリがこれを最初に読み込む。版の番号はここの VERSION だけで管理し、
 * 各ページはこれを題と見出しに出す。
 *
 * 持ち方の考え方
 * --------------
 * スマートフォンを横に持ち、ハーモニカのように長辺を口に当てる。照合笛の12本は
 * スマートフォンの長辺に沿って並び、1本の笛の長さ（約66mm）がスマートフォンの短辺
 * （73.2mm）とほぼ同じになる。持ち方は次の2つの選択の組み合わせで4通りある。
 *   placement … 笛の板を画面の上に置く（screen）か、裏面に置く（back）か
 *   facing    … 画面を上に向ける（up）か、下に向ける（down）か
 * 手は親指2本が下側、残りの8本が上側に来る。したがって画面を上に向けると8本の指が
 * 画面に触れ、下に向けると親指2本だけが画面に触れる。
 *
 * 画面上の座標
 * ------------
 * 横向きの画面で、12本の笛は縦の帯（レーン）として左右に並ぶ。笛は画面の短辺を
 * ほぼ覆うので、帯は画面の上端から下端まで伸びる。帯の位置は、板の中心の位置
 * （plateCenterMm、画面の左端から測る）と、1ミリあたりの画素数で決まる。
 */
(function (root) {
  "use strict";

  const VERSION = "v1";
  const STORE_KEY = "irecorika.settings.v1";

  // 照合笛 v9 の寸法（fue/matching_flutes.py と fue/mini10.py から求めた値）
  const FLUTE = {
    count: 12,
    widthMm: 7.0,            // 笛1本の幅
    pitchMm: 6.7,            // 隣の笛との中心間隔（幅7mmから重なり0.3mmを引いたもの）
    plateSpanMm: 82.7,       // 板の、笛が並ぶ方向の長さ
    plateLenMm: 80.2,        // 板の、笛の長軸方向の長さ（番号の帯を含む）
    bodyLenMm: 66.0,         // 笛の本体の長さ
    firstCenterMm: 4.5,      // 板の縁から最初の笛の中心まで（余白1mm＋幅の半分）
    lowMidi: 92,             // スロット0 = G#6
    freqs: [1661.2, 1760.0, 1864.7, 1975.5, 2093.0, 2217.5, 2349.3, 2489.0, 2637.0, 2793.8, 2960.0, 3136.0],
  };

  const NOTE_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const NOTE_FLAT = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"];
  const NOTE_DOREMI = ["ド", "ド#", "レ", "レ#", "ミ", "ファ", "ファ#", "ソ", "ソ#", "ラ", "ラ#", "シ"];

  // 1CSS画素の長さ[mm]。Pixel 7 は 1080×2400 画素・416ppi・devicePixelRatio 2.625 で、
  // 1CSS画素 = 2.625/416 インチ = 0.1603mm になる。他の機種は Android の標準（160dpi）で見積もる。
  function defaultMmPerPx() {
    const ua = (typeof navigator !== "undefined" && navigator.userAgent) || "";
    if (/Pixel 7(?! Pro)/.test(ua)) return 0.1603;
    return 25.4 / 160;
  }

  const DEFAULTS = {
    placement: "screen",     // screen | back
    facing: "up",            // up | down
    lowSide: "left",         // 低い音の笛が画面のどちら側にあるか
    fingers: "auto",         // auto | 8 | 2（auto は facing から決める）
    padLayout: "rows",       // rows（縦に積む）| cols（横に並べる）| grid（2×2）
    mmPerPx: null,           // null なら defaultMmPerPx()
    plateCenterMm: null,     // null なら画面の中央
    centsOffset: 0,          // 笛全体の音程のずれ[セント]（印刷の材料や温度で揺れる分）
    onMarginDb: 14,          // 暗騒音から何dB上を「鳴っている」とするか
    echoCancel: false,       // マイクのエコーキャンセル
    guard: true,             // スマートフォンの音から笛の音域を抜いて、マイクへの回り込みを防ぐ
    showNames: "sharp",      // sharp | flat | doremi | none
    volume: 0.8,
  };

  function load() {
    let s = {};
    try { s = JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch (_) { s = {}; }
    return Object.assign({}, DEFAULTS, s);
  }
  function save(s) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(s)); } catch (_) {}
  }
  function update(patch) {
    const s = Object.assign(load(), patch);
    save(s);
    return s;
  }
  function reset() {
    try { localStorage.removeItem(STORE_KEY); } catch (_) {}
    return load();
  }

  /* 画面に触れる指の数。親指2本が下、残り8本が上なので、画面が上向きなら8本、下向きなら2本 */
  function fingerCount(s) {
    if (s.fingers === "8") return 8;
    if (s.fingers === "2") return 2;
    return s.facing === "down" ? 2 : 8;
  }

  /* 笛の並びを画面の座標[CSS画素]で返す。
   * 戻り値 … { mmPerPx, plate:{x0,x1}, lanes:[{slot,x,x0,x1}], left:{x0,x1}, right:{x0,x1} }
   * lanes[slot] はスロット番号（0=G#6 … 11=G7）の順に並ぶ。低い音が右側なら x は右から左へ進む。 */
  function geometry(s, width, height) {
    const mmPerPx = s.mmPerPx || defaultMmPerPx();
    const screenMm = width * mmPerPx;
    const centerMm = (s.plateCenterMm === null || s.plateCenterMm === undefined) ? screenMm / 2 : s.plateCenterMm;
    const plate0Mm = centerMm - FLUTE.plateSpanMm / 2;
    const lanes = [];
    for (let i = 0; i < FLUTE.count; i++) {
      const k = s.lowSide === "right" ? FLUTE.count - 1 - i : i;
      const cMm = plate0Mm + FLUTE.firstCenterMm + k * FLUTE.pitchMm;
      const x = cMm / mmPerPx;
      const half = FLUTE.pitchMm / 2 / mmPerPx;
      lanes.push({ slot: i, x: x, x0: x - half, x1: x + half });
    }
    const px0 = plate0Mm / mmPerPx, px1 = (plate0Mm + FLUTE.plateSpanMm) / mmPerPx;
    return {
      mmPerPx: mmPerPx, width: width, height: height,
      plate: { x0: px0, x1: px1 },
      lanes: lanes,
      left: { x0: 0, x1: Math.max(0, Math.min(width, px0)) },
      right: { x0: Math.max(0, Math.min(width, px1)), x1: width },
    };
  }

  /* 画面の x 座標から、その真上（または真裏）にある笛のスロットを返す。無ければ -1 */
  function slotAtX(geo, x) {
    for (const l of geo.lanes) if (x >= l.x0 && x < l.x1) return l.slot;
    return -1;
  }

  // ---------------------------------------------------------------- 音名と周波数
  function midiToFreq(m) { return 440 * Math.pow(2, (m - 69) / 12); }
  function freqToMidiFloat(f) { return 69 + 12 * Math.log2(f / 440); }
  function noteName(midi, style) {
    const pc = ((midi % 12) + 12) % 12;
    const oct = Math.floor(midi / 12) - 1;
    style = style || "sharp";
    if (style === "doremi") return NOTE_DOREMI[pc];
    if (style === "none") return "";
    return (style === "flat" ? NOTE_FLAT : NOTE_SHARP)[pc] + oct;
  }
  function pcName(pc, style) {
    pc = ((pc % 12) + 12) % 12;
    if (style === "doremi") return NOTE_DOREMI[pc];
    return (style === "sharp" ? NOTE_SHARP : NOTE_FLAT)[pc];
  }
  function slotToMidi(slot) { return FLUTE.lowMidi + slot; }
  function midiToSlot(m) { const s = m - FLUTE.lowMidi; return (s >= 0 && s < FLUTE.count) ? s : -1; }

  /* 周波数を最寄りの笛に当てる。centsOffset は笛全体のずれ。範囲外は null */
  function freqToSlot(f, centsOffset) {
    if (!f || !isFinite(f)) return null;
    const mf = freqToMidiFloat(f) - (centsOffset || 0) / 100;
    const m = Math.round(mf);
    const slot = midiToSlot(m);
    if (slot < 0) return null;
    return { slot: slot, midi: m, cents: Math.round((mf - m) * 100) };
  }

  // 12本の笛それぞれの色（色相環を低い音から高い音へ一周させる）
  function slotColor(slot, alpha) {
    const h = Math.round(slot * 360 / 12);
    return "hsla(" + h + ",90%,60%," + (alpha === undefined ? 1 : alpha) + ")";
  }

  // ---------------------------------------------------------------- 画面
  // 全画面と向きの固定は、環境によっては応答が返らないことがあるので、待つのは0.8秒までにする
  const within = (p, ms) => Promise.race([p, new Promise(r => setTimeout(r, ms))]);
  async function enterFullscreen() {
    const el = document.documentElement;
    try {
      if (!document.fullscreenElement && el.requestFullscreen) await within(el.requestFullscreen({ navigationUI: "hide" }), 800);
    } catch (_) {}
    try {
      if (screen.orientation && screen.orientation.lock) await within(screen.orientation.lock("landscape-primary"), 800);
    } catch (_) {}
  }
  function exitFullscreen() {
    try { if (document.fullscreenElement) document.exitFullscreen(); } catch (_) {}
  }
  function isLandscape() { return window.innerWidth >= window.innerHeight; }

  /* 画面を消さないようにする。演奏中に画面が暗くなると困るため */
  let wakeLock = null;
  async function keepAwake() {
    try { if (navigator.wakeLock && !wakeLock) wakeLock = await navigator.wakeLock.request("screen"); } catch (_) {}
  }
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && wakeLock) { wakeLock = null; keepAwake(); }
    });
  }

  /* URLの引数。sim=1 なら、マイクの代わりに画面の笛を押したりキーを打ったりして音を入れる */
  function param(name) {
    if (typeof location === "undefined") return null;
    const frag = new URLSearchParams(location.hash.replace(/^#/, ""));
    const q = new URLSearchParams(location.search);
    return frag.has(name) ? frag.get(name) : q.get(name);
  }

  /* 傾きと揺れ。重力の向きから、演奏者から見た左右の傾き（roll）と前後の傾き（pitch）を求める。
   *   roll  … 画面の右側（演奏者の右手の側）が下がると正[度]
   *   pitch … 口から遠い側が上がると正[度]
   *   shake … 重力を除いた加速度の大きさ[m/s²]
   * 横向き（landscape-primary）では、端末の長軸 y が画面の左を向く。右側が下がると y が上を向くので、
   * 重力の反作用である accelerationIncludingGravity.y が正になる。向きが逆（角度270）なら符号を返す。
   * 画面を下に向けると、口の側が画面の上辺になるので pitch の符号を返す。 */
  const motion = (function () {
    const subs = [];
    let started = false, last = { roll: 0, pitch: 0, shake: 0, ok: false };
    let gx = 0, gy = 0, gz = 9.8;   // 重力の低域成分
    function handler(ev) {
      const a = ev.accelerationIncludingGravity;
      if (!a || a.x === null) return;
      gx += (a.x - gx) * 0.2; gy += (a.y - gy) * 0.2; gz += (a.z - gz) * 0.2;
      const g = Math.sqrt(gx * gx + gy * gy + gz * gz) || 9.8;
      const angle = (screen.orientation && screen.orientation.angle) || 0;
      const s = load();
      let roll, pitch;
      if (angle === 90 || angle === 270) {
        const k = angle === 90 ? 1 : -1;
        roll = Math.asin(Math.max(-1, Math.min(1, k * gy / g))) * 180 / Math.PI;
        pitch = Math.asin(Math.max(-1, Math.min(1, k * gx / g))) * 180 / Math.PI;
      } else {
        roll = Math.asin(Math.max(-1, Math.min(1, -gx / g))) * 180 / Math.PI;
        pitch = Math.asin(Math.max(-1, Math.min(1, gy / g))) * 180 / Math.PI;
      }
      if (s.facing === "down") pitch = -pitch;
      const lin = ev.acceleration && ev.acceleration.x !== null ? ev.acceleration
        : { x: a.x - gx, y: a.y - gy, z: a.z - gz };
      const shake = Math.sqrt(lin.x * lin.x + lin.y * lin.y + lin.z * lin.z);
      last = { roll, pitch, shake, ok: true, raw: { x: a.x, y: a.y, z: a.z }, lin };
      subs.forEach(f => f(last));
    }
    async function start(cb) {
      if (cb) subs.push(cb);
      if (started) return true;
      try {
        if (typeof DeviceMotionEvent !== "undefined" && DeviceMotionEvent.requestPermission) {
          const r = await DeviceMotionEvent.requestPermission();
          if (r !== "granted") return false;
        }
      } catch (_) { return false; }
      window.addEventListener("devicemotion", handler);
      started = true;
      return true;
    }
    return { start, last: () => last };
  })();

  function describe(s) {
    const p = s.placement === "screen" ? "笛を画面の上に置く" : "笛を裏面に置く";
    const f = s.facing === "up" ? "画面を上に向ける" : "画面を下に向ける";
    return p + "・" + f + "・画面に触れる指 " + fingerCount(s) + "本";
  }

  const api = {
    VERSION, FLUTE, DEFAULTS, load, save, update, reset, fingerCount, geometry, slotAtX,
    midiToFreq, freqToMidiFloat, noteName, pcName, slotToMidi, midiToSlot, freqToSlot, slotColor,
    enterFullscreen, exitFullscreen, isLandscape, keepAwake, param, describe, defaultMmPerPx, motion,
    NOTE_SHARP, NOTE_FLAT, NOTE_DOREMI,
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IRK = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
