/* iRecorika 音の部品（笛の検出・音源・リズムの時計）
 *
 * 笛の検出
 * --------
 * CipherFlute の復号ページと同じく、[* 笛の音域の中でいちばん強い FFT の山] を追う
 * （docs/cipher/fft_peak.js の peakInBand をそのまま使う）。自己相関は G#6 を取り違えるので使わない。
 * 演奏に使うので、復号ページより窓を短くしている（既定 2048 点、48kHz で約43ms）。
 * 音域の外を見ないので、スマートフォンが鳴らす伴奏を笛の音域の外に置けば、
 * 伴奏がマイクに回り込んでも検出は乱れにくい。これを「保護」と呼び、既定で有効にしている。
 *
 * 保護
 * ----
 * スマートフォンから出す音は、すべて「笛の音域を抜く」経路を通す。1350Hz より下を通す
 * 低域通過と、3350Hz より上を通す高域通過を並べて足し合わせ、その間（笛の 1600〜3250Hz）を
 * 24dB/オクターブで落とす。笛と同じ高さの音をそのまま鳴らしたいとき（まねっこの手本など）は
 * 保護を通らない経路（rawOut）へつなぎ、そのあいだは検出を止める。
 */
(function (root) {
  "use strict";
  const IRK = root.IRK || (typeof require === "function" ? require("./irk-common.js") : null);

  const BAND_LO = 1600, BAND_HI = 3250;   // 検出に使う音域[Hz]。G#6 の半音弱下から G7 の半音弱上まで

  // ================================================================ 検出の判定（純粋な処理）
  /* 1フレームごとに、山の強さ・周波数・際立ち（山と音域の中央値の差）を受け取り、
   * 笛が鳴り始めた・変わった・止んだ、を判定する。ブラウザに依存しないので node で検査できる。 */
  function NoteTracker(opts) {
    opts = Object.assign({
      marginDb: 14,          // 暗騒音からこれだけ上なら鳴っているとみなす
      releaseDb: 6,          // 鳴っている間は、これだけ下がるまで鳴り続けとみなす
      minProminenceDb: 10,   // 山が音域の中央値よりこれだけ高くなければ、雑音とみなす
      onFrames: 2,           // この回数続けて同じ笛が読めたら鳴り始めとする
      offFrames: 3,          // この回数続けて読めなかったら止んだとする
      noiseWindowMs: 8000,   // 暗騒音を見積もる期間
      centsOffset: 0,
    }, opts || {});
    const hist = [];        // [t, level]
    let noise = null;
    let cur = null;         // 鳴っている笛 {slot, midi, freq, cents, level, t0}
    let cand = null, candCount = 0, missCount = 0;

    function estimateNoise(t, level) {
      if (!isFinite(level)) return;
      hist.push([t, level]);
      while (hist.length && hist[0][0] < t - opts.noiseWindowMs) hist.shift();
      if (hist.length < 8) { noise = noise === null ? level : Math.min(noise, level); return; }
      const s = hist.map(h => h[1]).sort((a, b) => a - b);
      const p10 = s[Math.floor(0.1 * (s.length - 1))];
      noise = p10;
    }

    /* noNoise を真にすると、そのフレームを暗騒音の見積もりに使わない（検出を止めている間など） */
    function feed(t, level, freq, prominence, noNoise) {
      // 暗騒音は[* 鳴っていないフレームだけ]から見積もる。吹き続けると8秒の窓が笛の音で埋まり、
      // 暗騒音が笛の強さまで上がって、鳴っているのに止んだと判定してしまうため
      if (!noNoise && !cur) estimateNoise(t, level);
      const onDb = (noise === null ? -100 : noise) + opts.marginDb;
      const need = cur ? onDb - opts.releaseDb : onDb;
      const tonal = prominence === undefined || prominence >= opts.minProminenceDb;
      let hit = null;
      if (isFinite(level) && level >= need && tonal) {
        hit = IRK.freqToSlot(freq, opts.centsOffset);
      }
      const events = [];
      if (hit) {
        missCount = 0;
        if (cur && hit.slot === cur.slot) {
          cur.freq = freq; cur.cents = hit.cents; cur.level = level;
          cand = null; candCount = 0;
        } else {
          if (cand && cand.slot === hit.slot) candCount++;
          else { cand = hit; candCount = 1; }
          if (candCount >= opts.onFrames) {
            const prev = cur;
            cur = { slot: hit.slot, midi: hit.midi, freq: freq, cents: hit.cents, level: level, t0: t };
            if (prev) events.push({ type: "off", slot: prev.slot, midi: prev.midi, t: t, durMs: t - prev.t0, changed: true });
            events.push({ type: "on", slot: cur.slot, midi: cur.midi, freq: freq, cents: hit.cents, level: level, t: t, legato: !!prev });
            cand = null; candCount = 0;
          }
        }
      } else {
        cand = null; candCount = 0;
        if (cur) {
          missCount++;
          if (missCount >= opts.offFrames) {
            events.push({ type: "off", slot: cur.slot, midi: cur.midi, t: t, durMs: t - cur.t0 });
            cur = null; missCount = 0;
          }
        }
      }
      return events;
    }

    return {
      feed: feed,
      current: () => cur,
      noise: () => noise,
      onDb: () => (noise === null ? null : noise + opts.marginDb),
      set: (k, v) => { opts[k] = v; },
      reset: () => { hist.length = 0; noise = null; cur = null; cand = null; candCount = 0; missCount = 0; },
    };
  }

  // ================================================================ 音の文脈
  let _ctx = null;
  function ctx() {
    if (!_ctx) {
      const AC = root.AudioContext || root.webkitAudioContext;
      _ctx = new AC({ latencyHint: "interactive" });
    }
    if (_ctx.state === "suspended") _ctx.resume();
    return _ctx;
  }

  // ================================================================ マイクによる検出
  /* 使い方
   *   const det = IRKAudio.Detector({ onNote(ev){}, onOff(ev){}, onFrame(fr){} });
   *   await det.start();     // 利用者の操作（タップ）の中で呼ぶ
   * sim=1 のときはマイクを開かず、det.simOn(slot) / det.simOff() で発振器の音を入れる。 */
  function Detector(opts) {
    opts = opts || {};
    const s = IRK.load();
    const sim = opts.sim !== undefined ? opts.sim : IRK.param("sim") === "1";
    const tracker = NoteTracker({ marginDb: s.onMarginDb, centsOffset: s.centsOffset });
    const st = { running: false, analyser: null, data: null, timer: null, stream: null,
                 muteUntil: 0, simOsc: null, simGain: null, last: null, t0: 0 };
    const listeners = { note: [], off: [], frame: [] };
    if (opts.onNote) listeners.note.push(opts.onNote);
    if (opts.onOff) listeners.off.push(opts.onOff);
    if (opts.onFrame) listeners.frame.push(opts.onFrame);

    async function start() {
      if (st.running) return true;
      const ac = ctx();
      st.analyser = new AnalyserNode(ac, { fftSize: opts.fftSize || 2048, smoothingTimeConstant: 0,
                                           minDecibels: -140, maxDecibels: 0 });
      st.data = new Float32Array(st.analyser.frequencyBinCount);
      if (sim) {
        // 模擬の入力。弱い雑音を常に流して、暗騒音の見積もりを実機に近づける
        const noise = ac.createBufferSource();
        noise.buffer = noiseBuffer(ac, 2);
        noise.loop = true;
        const ng = new GainNode(ac, { gain: 0.002 });
        noise.connect(ng).connect(st.analyser);
        noise.start();
        st.simGain = new GainNode(ac, { gain: 0 });
        st.simGain.connect(st.analyser);
        if (opts.simAudible) st.simGain.connect(new GainNode(ac, { gain: 0.15 })).connect(ac.destination);
      } else {
        try {
          st.stream = await navigator.mediaDevices.getUserMedia({ audio: {
            echoCancellation: !!s.echoCancel, noiseSuppression: false, autoGainControl: false } });
        } catch (e) {
          return false;
        }
        ac.createMediaStreamSource(st.stream).connect(st.analyser);
      }
      st.running = true;
      st.t0 = performance.now();
      st.timer = setInterval(tick, 12);
      return true;
    }
    function stop() {
      if (!st.running) return;
      clearInterval(st.timer);
      if (st.stream) st.stream.getTracks().forEach(t => t.stop());
      st.running = false;
    }

    function tick() {
      const ac = ctx();
      st.analyser.getFloatFrequencyData(st.data);
      const binHz = ac.sampleRate / st.analyser.fftSize;
      const pk = root.FftPeak.peakInBand(st.data, binHz, BAND_LO, BAND_HI);
      // 際立ち … 山が音域の中央値からどれだけ抜きん出ているか。息の擦れや拍手は平たいので低い
      const k0 = Math.ceil(BAND_LO / binHz), k1 = Math.floor(BAND_HI / binHz);
      const band = Array.prototype.slice.call(st.data, k0, k1 + 1).filter(isFinite).sort((a, b) => a - b);
      const median = band.length ? band[band.length >> 1] : -140;
      const now = performance.now();
      const level = pk ? pk.level : -140;
      const freq = pk ? pk.freq : 0;
      const prominence = level - median;
      let events = [];
      // 検出を止めている間（スマートフォンが笛と同じ高さの音を鳴らしている間）は、鳴っていないとして扱う
      if (now >= st.muteUntil) events = tracker.feed(now, level, freq, prominence);
      else events = tracker.feed(now, -140, 0, 0, true);
      const cur = tracker.current();
      const noise = tracker.noise();
      const strength = cur && noise !== null ? Math.max(0, Math.min(1, (level - noise - 6) / 30)) : 0;
      const fr = { t: now, level, freq, prominence, noise, onDb: tracker.onDb(), cur, strength,
                   spectrum: st.data, binHz, muted: now < st.muteUntil };
      st.last = fr;
      for (const ev of events) {
        if (ev.type === "on") listeners.note.forEach(f => f(ev));
        else listeners.off.forEach(f => f(ev));
      }
      listeners.frame.forEach(f => f(fr));
    }

    function simOn(slot) {
      if (!sim || !st.running) return;
      const ac = ctx();
      const f = IRK.FLUTE.freqs[slot];
      if (!st.simOsc) {
        st.simOsc = new OscillatorNode(ac, { type: "sine", frequency: f });
        st.simOsc.connect(st.simGain);
        st.simOsc.start();
      }
      st.simOsc.frequency.setValueAtTime(f, ac.currentTime);
      st.simGain.gain.setTargetAtTime(0.3, ac.currentTime, 0.005);
    }
    function simOff() {
      if (!sim || !st.running || !st.simGain) return;
      st.simGain.gain.setTargetAtTime(0, ctx().currentTime, 0.005);
    }
    // 模擬の入力はキーボードでも入れられる（1〜0、-、^ の12個がスロット0〜11）
    if (sim && typeof document !== "undefined") {
      const codes = ["Digit1", "Digit2", "Digit3", "Digit4", "Digit5", "Digit6", "Digit7", "Digit8", "Digit9", "Digit0", "Minus", "Equal"];
      let held = -1;
      document.addEventListener("keydown", e => {
        const i = codes.indexOf(e.code);
        if (i >= 0 && !e.repeat) { held = i; simOn(i); }
      });
      document.addEventListener("keyup", e => {
        const i = codes.indexOf(e.code);
        if (i >= 0 && i === held) { held = -1; simOff(); }
      });
    }

    return {
      start, stop, simOn, simOff, sim,
      on: (type, f) => listeners[type].push(f),
      mute: ms => { st.muteUntil = Math.max(st.muteUntil, performance.now() + ms); },
      running: () => st.running,
      last: () => st.last,
      tracker,
      analyser: () => st.analyser,
      stream: () => st.stream,
    };
  }

  // ================================================================ 音源
  const noiseCache = new WeakMap();
  function noiseBuffer(ac, sec) {
    let b = noiseCache.get(ac);
    if (b) return b;
    const n = Math.floor(ac.sampleRate * (sec || 1));
    b = ac.createBuffer(1, n, ac.sampleRate);
    const d = b.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    noiseCache.set(ac, b);
    return b;
  }

  let _bus = null;
  /* 出力の経路。guardIn に入れた音は保護（笛の音域を抜く）を通り、rawOut に入れた音は素通しになる */
  function bus() {
    if (_bus) return _bus;
    const ac = ctx();
    const s = IRK.load();
    const master = new GainNode(ac, { gain: s.volume });
    const comp = new DynamicsCompressorNode(ac, { threshold: -12, ratio: 4, attack: 0.003, release: 0.15 });
    master.connect(comp).connect(ac.destination);
    const guardIn = new GainNode(ac, { gain: 1 });
    const guarded = new GainNode(ac, { gain: s.guard ? 1 : 0 });
    const direct = new GainNode(ac, { gain: s.guard ? 0 : 1 });
    const lp1 = new BiquadFilterNode(ac, { type: "lowpass", frequency: 1350, Q: 0.707 });
    const lp2 = new BiquadFilterNode(ac, { type: "lowpass", frequency: 1350, Q: 0.707 });
    const hp1 = new BiquadFilterNode(ac, { type: "highpass", frequency: 3350, Q: 0.707 });
    const hp2 = new BiquadFilterNode(ac, { type: "highpass", frequency: 3350, Q: 0.707 });
    guardIn.connect(lp1).connect(lp2).connect(guarded);
    guardIn.connect(hp1).connect(hp2).connect(guarded);
    guardIn.connect(direct);
    guarded.connect(master);
    direct.connect(master);
    _bus = {
      master, guardIn, rawOut: master,
      setGuard(on) {
        guarded.gain.setTargetAtTime(on ? 1 : 0, ac.currentTime, 0.02);
        direct.gain.setTargetAtTime(on ? 0 : 1, ac.currentTime, 0.02);
      },
      setVolume(v) { master.gain.setTargetAtTime(v, ac.currentTime, 0.02); },
    };
    return _bus;
  }

  const VOICES = {
    sine: "正弦波（やわらかい）", triangle: "三角波（笛に近い）", organ: "オルガン", pad: "ストリングス風",
    square: "8ビット", brass: "金管風", pluck: "撥弦（ギター風）", bell: "鐘", bass: "ベース",
  };
  let organWave = null;

  /* 1つの音を作る。戻り値は {freqParams, out, stop(t)}。out を好きな行き先へつなぐ */
  function buildVoice(type, freq, t) {
    const ac = ctx();
    const out = new GainNode(ac, { gain: 1 });
    const oscs = [], freqParams = [];
    const addOsc = (wave, ratio, gain, detune) => {
      const o = new OscillatorNode(ac, { frequency: freq * ratio, detune: detune || 0 });
      if (typeof wave === "string") o.type = wave; else o.setPeriodicWave(wave);
      const g = new GainNode(ac, { gain: gain });
      o.connect(g);
      oscs.push(o); freqParams.push({ p: o.frequency, ratio: ratio });
      return g;
    };
    let tail = null;
    switch (type) {
      case "triangle": addOsc("triangle", 1, 0.9).connect(out); break;
      case "organ": {
        if (!organWave) organWave = ac.createPeriodicWave(new Float32Array([0, 1, 0.55, 0.3, 0.2, 0.1, 0.08]), new Float32Array(7));
        addOsc(organWave, 1, 0.6).connect(out);
        break;
      }
      case "pad": {
        const f = new BiquadFilterNode(ac, { type: "lowpass", frequency: Math.min(4000, freq * 3), Q: 0.5 });
        addOsc("sawtooth", 1, 0.25, -8).connect(f);
        addOsc("sawtooth", 1, 0.25, 8).connect(f);
        f.connect(out);
        break;
      }
      case "square": addOsc("square", 1, 0.3).connect(out); break;
      case "brass": {
        const f = new BiquadFilterNode(ac, { type: "lowpass", frequency: freq * 1.5, Q: 1 });
        f.frequency.setValueAtTime(freq * 1.2, t);
        f.frequency.linearRampToValueAtTime(freq * 5, t + 0.08);
        f.frequency.linearRampToValueAtTime(freq * 3, t + 0.3);
        addOsc("sawtooth", 1, 0.45).connect(f);
        f.connect(out);
        break;
      }
      case "pluck": {
        const f = new BiquadFilterNode(ac, { type: "lowpass", frequency: freq * 8, Q: 2 });
        f.frequency.setValueAtTime(freq * 8, t);
        f.frequency.exponentialRampToValueAtTime(Math.max(80, freq * 1.2), t + 0.4);
        addOsc("sawtooth", 1, 0.5).connect(f);
        f.connect(out);
        break;
      }
      case "bell": {
        const car = new OscillatorNode(ac, { type: "sine", frequency: freq });
        const mod = new OscillatorNode(ac, { type: "sine", frequency: freq * 3.5 });
        const idx = new GainNode(ac, { gain: freq * 4 });
        idx.gain.setValueAtTime(freq * 4, t);
        idx.gain.exponentialRampToValueAtTime(freq * 0.2, t + 1.2);
        mod.connect(idx).connect(car.frequency);
        const g = new GainNode(ac, { gain: 0.6 });
        car.connect(g).connect(out);
        oscs.push(car, mod);
        freqParams.push({ p: car.frequency, ratio: 1 }, { p: mod.frequency, ratio: 3.5 });
        break;
      }
      case "bass": {
        addOsc("triangle", 1, 0.8).connect(out);
        addOsc("sine", 0.5, 0.5).connect(out);
        break;
      }
      default: addOsc("sine", 1, 0.9).connect(out);
    }
    oscs.forEach(o => o.start(t));
    return {
      out, freqParams,
      stop(t2) { oscs.forEach(o => { try { o.stop(t2); } catch (_) {} }); },
    };
  }

  // 音色ごとの包絡（アタック・ディケイ・サステイン・リリース[秒]）
  const ENV = {
    sine: [0.01, 0.1, 0.8, 0.12], triangle: [0.01, 0.1, 0.8, 0.12], organ: [0.005, 0.05, 0.9, 0.06],
    pad: [0.25, 0.3, 0.8, 0.5], square: [0.005, 0.05, 0.7, 0.05], brass: [0.04, 0.2, 0.7, 0.15],
    pluck: [0.003, 0.6, 0.0, 0.3], bell: [0.002, 1.5, 0.0, 0.8], bass: [0.005, 0.2, 0.7, 0.1],
  };

  /* 音を1つ鳴らす。dur を省くと鳴らしっぱなしにし、戻り値の release() で止める。
   * opts … {type, vel(0..1), when, dur, dest（既定は保護つきの経路）} */
  function note(midi, opts) {
    opts = opts || {};
    const ac = ctx();
    const type = opts.type || "triangle";
    const t = opts.when || ac.currentTime;
    const vel = opts.vel === undefined ? 0.7 : opts.vel;
    const [a, d, sus, r] = ENV[type] || ENV.sine;
    const v = buildVoice(type, IRK.midiToFreq(midi), t);
    const env = new GainNode(ac, { gain: 0 });
    v.out.connect(env).connect(opts.dest || bus().guardIn);
    env.gain.setValueAtTime(0, t);
    env.gain.linearRampToValueAtTime(vel, t + a);
    env.gain.setTargetAtTime(vel * sus, t + a, d / 3 + 0.001);
    let released = false;
    const release = (when) => {
      if (released) return; released = true;
      const tr = Math.max(when || ac.currentTime, t + a);
      env.gain.cancelScheduledValues(tr);
      env.gain.setTargetAtTime(0, tr, r / 3 + 0.001);
      v.stop(tr + r * 2 + 0.05);
    };
    if (opts.dur !== undefined) release(t + opts.dur);
    else if (sus === 0) release(t + a + d);
    return { release, voice: v, env };
  }

  /* 吹いた音についていく単音の声。音の高さと大きさを滑らかに変えられる */
  function MonoVoice(type, dest) {
    const ac = ctx();
    let v = null, env = null, curType = type || "triangle", curMidi = 60;
    function ensure() {
      if (v) return;
      const t = ac.currentTime;
      v = buildVoice(curType, IRK.midiToFreq(curMidi), t);
      env = new GainNode(ac, { gain: 0 });
      v.out.connect(env).connect(dest || bus().guardIn);
    }
    return {
      setType(t) { if (t === curType) return; curType = t; if (v) { const old = v, oe = env; oe.gain.setTargetAtTime(0, ac.currentTime, 0.02); old.stop(ac.currentTime + 0.2); v = null; env = null; } },
      setMidi(m, glide) {
        curMidi = m; ensure();
        const f = IRK.midiToFreq(m);
        for (const fp of v.freqParams) fp.p.setTargetAtTime(f * fp.ratio, ac.currentTime, glide || 0.01);
      },
      setLevel(g, tc) { ensure(); env.gain.setTargetAtTime(g, ac.currentTime, tc === undefined ? 0.02 : tc); },
      bend(cents) { if (!v) return; const f = IRK.midiToFreq(curMidi + cents / 100); for (const fp of v.freqParams) fp.p.setTargetAtTime(f * fp.ratio, ac.currentTime, 0.02); },
      midi: () => curMidi,
    };
  }

  // ================================================================ 打楽器
  const DRUMS = {
    kick: "バスドラム", snare: "スネア", hat: "ハイハット", ohat: "オープンハイハット", clap: "クラップ",
    tomL: "タム（低）", tomH: "タム（高）", crash: "シンバル", cowbell: "カウベル", shaker: "シェイカー", rim: "リム",
  };
  function drum(name, when, vel, dest) {
    const ac = ctx();
    const t = when || ac.currentTime;
    const v = vel === undefined ? 0.9 : vel;
    const out = dest || bus().guardIn;
    const env = (g, a, dcy) => { g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(v * a, t + 0.002); g.gain.exponentialRampToValueAtTime(0.0001, t + dcy); };
    const noiseSrc = (dur) => { const n = new AudioBufferSourceNode(ac, { buffer: noiseBuffer(ac, 1) }); n.start(t, Math.random() * 0.5); n.stop(t + dur); return n; };
    const tone = (f0, f1, dur, typ, a) => {
      const o = new OscillatorNode(ac, { type: typ || "sine", frequency: f0 });
      o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + dur * 0.5);
      const g = new GainNode(ac); env(g, a, dur); o.connect(g).connect(out); o.start(t); o.stop(t + dur + 0.05);
    };
    const noise = (type, freq, q, dur, a) => {
      const f = new BiquadFilterNode(ac, { type: type, frequency: freq, Q: q });
      const g = new GainNode(ac); env(g, a, dur);
      noiseSrc(dur + 0.05).connect(f).connect(g).connect(out);
    };
    switch (name) {
      case "kick": tone(150, 45, 0.45, "sine", 1.0); break;
      case "snare": tone(220, 160, 0.12, "triangle", 0.5); noise("bandpass", 1200, 0.7, 0.2, 0.9); break;
      case "hat": noise("highpass", 7500, 0.7, 0.05, 0.5); break;
      case "ohat": noise("highpass", 7000, 0.7, 0.35, 0.45); break;
      case "clap":
        for (let i = 0; i < 3; i++) { const tt = t + i * 0.012; const f = new BiquadFilterNode(ac, { type: "bandpass", frequency: 1100, Q: 1 }); const g = new GainNode(ac); g.gain.setValueAtTime(0, tt); g.gain.linearRampToValueAtTime(v * 0.8, tt + 0.002); g.gain.exponentialRampToValueAtTime(0.0001, tt + (i === 2 ? 0.18 : 0.03)); const n = new AudioBufferSourceNode(ac, { buffer: noiseBuffer(ac, 1) }); n.start(tt, Math.random() * 0.5); n.stop(tt + 0.25); n.connect(f).connect(g).connect(out); }
        break;
      case "tomL": tone(140, 90, 0.35, "sine", 0.9); break;
      case "tomH": tone(220, 150, 0.3, "sine", 0.9); break;
      case "crash": noise("highpass", 5000, 0.5, 1.2, 0.5); break;
      case "cowbell": {
        const f = new BiquadFilterNode(ac, { type: "bandpass", frequency: 800, Q: 3 });
        const g = new GainNode(ac); env(g, 0.6, 0.3);
        [540, 800].forEach(fr => { const o = new OscillatorNode(ac, { type: "square", frequency: fr }); o.connect(f); o.start(t); o.stop(t + 0.35); });
        f.connect(g).connect(out);
        break;
      }
      case "shaker": noise("highpass", 6000, 0.8, 0.09, 0.45); break;
      case "rim": tone(1000, 800, 0.03, "square", 0.3); noise("bandpass", 900, 2, 0.03, 0.5); break;
    }
  }

  // ================================================================ 拍の時計
  /* 16分音符ごとに onStep(step, when) を呼ぶ。先読みして音を予約するので、画面が重くても拍がずれない */
  function Clock(onStep) {
    let bpm = 100, running = false, timer = null, next = 0, step = 0;
    const spb = 4;     // 1拍あたりの刻み
    function schedule() {
      const ac = ctx();
      while (next < ac.currentTime + 0.12) {
        onStep(step, next);
        next += 60 / bpm / spb;
        step++;
      }
    }
    return {
      start(atStep) { if (running) return; running = true; step = atStep || 0; next = ctx().currentTime + 0.06; schedule(); timer = setInterval(schedule, 25); },
      stop() { running = false; clearInterval(timer); },
      setBpm(b) { bpm = Math.max(30, Math.min(260, b)); },
      bpm: () => bpm, running: () => running, step: () => step,
      stepSec: () => 60 / bpm / spb,
    };
  }

  // ================================================================ 和音
  const CHORDS = {
    "": [0, 4, 7], m: [0, 3, 7], "7": [0, 4, 7, 10], M7: [0, 4, 7, 11], m7: [0, 3, 7, 10],
    sus4: [0, 5, 7], dim: [0, 3, 6], aug: [0, 4, 8], add9: [0, 4, 7, 14], "6": [0, 4, 7, 9], m7b5: [0, 3, 6, 10],
  };
  /* 根音の高さの近くに、和音を密集した形で並べる（base 付近から上へ） */
  function voicing(rootPc, quality, baseMidi) {
    const iv = CHORDS[quality] || CHORDS[""];
    let r = baseMidi + ((rootPc - baseMidi) % 12 + 12) % 12;
    return iv.map(x => r + x);
  }

  const api = { BAND_LO, BAND_HI, NoteTracker, ctx, Detector, bus, note, MonoVoice, VOICES, drum, DRUMS, Clock, CHORDS, voicing, noiseBuffer };
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IRKAudio = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
