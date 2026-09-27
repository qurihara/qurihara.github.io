/* iRecorika 音楽理論の部品（調・和音・コード進行・曲）
 *
 * 照合笛の12本は G#6 から G7 までの半音階で、音域は11半音（1オクターブに半音足りない）。
 * 1オクターブの長音階が収まる調は A♭ 長調だけである（A♭6〜G7 の7音）。そのため
 * 伴奏と練習の既定は A♭ 長調にしている。曲は音域が11半音以内のものだけを収めた。
 */
(function (root) {
  "use strict";

  const MAJOR = [0, 2, 4, 5, 7, 9, 11];
  const MINOR = [0, 2, 3, 5, 7, 8, 10];
  const FLAT_NAMES = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"];
  const KEYS = [8, 9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7].map(pc => ({ pc, name: FLAT_NAMES[pc] + " 長調" }));

  function inScale(midi, keyPc, scale) {
    return (scale || MAJOR).indexOf(((midi - keyPc) % 12 + 12) % 12) >= 0;
  }
  /* 調の中で steps 度ぶん下の音を返す（steps=2 で3度下、5 で6度下）。
   * 調の外の音なら、半音で近似する（3度下は長3度、6度下は短6度…の平均的な値） */
  function diatonicBelow(midi, keyPc, steps, scale) {
    scale = scale || MAJOR;
    const rel = ((midi - keyPc) % 12 + 12) % 12;
    const deg = scale.indexOf(rel);
    if (deg < 0) return midi - (steps === 2 ? 4 : steps === 5 ? 9 : steps * 2);
    const octBase = midi - rel;
    let d = deg - steps, oct = 0;
    while (d < 0) { d += scale.length; oct -= 12; }
    return octBase + oct + scale[d];
  }

  // 調の中の和音（ローマ数字の度数 → 根音の半音と和音の種類）
  const DEGREES = {
    "I": [0, ""], "ii": [2, "m"], "iii": [4, "m"], "IV": [5, ""], "V": [7, ""], "vi": [9, "m"], "vii": [11, "m7b5"],
    "I7": [0, "7"], "IV7": [5, "7"], "V7": [7, "7"], "IM7": [0, "M7"], "IVM7": [5, "M7"], "ii7": [2, "m7"], "iii7": [4, "m7"], "vi7": [9, "m7"],
    "II7": [2, "7"], "III7": [4, "7"], "VI7": [9, "7"], "bVII": [10, ""], "bVI": [8, ""], "iv": [5, "m"], "Vsus4": [7, "sus4"],
  };
  function degreeChord(deg, keyPc) {
    const d = DEGREES[deg] || DEGREES.I;
    return { rootPc: (keyPc + d[0]) % 12, quality: d[1], degree: deg };
  }
  const QUALITY_NAME = { "": "", m: "m", "7": "7", M7: "M7", m7: "m7", sus4: "sus4", dim: "dim", aug: "aug", add9: "add9", "6": "6", m7b5: "m7(♭5)" };
  function chordName(rootPc, quality) { return FLAT_NAMES[((rootPc % 12) + 12) % 12] + (QUALITY_NAME[quality] !== undefined ? QUALITY_NAME[quality] : quality); }
  function chordPcs(rootPc, quality) {
    const iv = (root.IRKAudio && root.IRKAudio.CHORDS[quality]) || [0, 4, 7];
    return iv.map(x => (rootPc + x) % 12);
  }

  // よく知られたコード進行（1つの和音が1小節）
  const PROGRESSIONS = [
    { name: "カノン進行", seq: ["I", "V", "vi", "iii", "IV", "I", "IV", "V"] },
    { name: "王道進行", seq: ["IVM7", "V7", "iii7", "vi"] },
    { name: "小室進行", seq: ["vi", "IV", "V", "I"] },
    { name: "イチロクニーゴー", seq: ["I", "vi", "ii", "V"] },
    { name: "ブルース（12小節）", seq: ["I7", "I7", "I7", "I7", "IV7", "IV7", "I7", "I7", "V7", "IV7", "I7", "V7"] },
    { name: "丸サ進行", seq: ["IVM7", "III7", "vi7", "I7"] },
    { name: "スリーコード", seq: ["I", "IV", "V", "I"] },
  ];

  // ---------------------------------------------------------------- 曲
  /* 曲は、ハ長調で書いた音名と拍の長さで表す。「C:1」は ド を1拍。「'」で1オクターブ上、
   * 「,」で1オクターブ下、「R」は休み。演奏するときは、音域が笛の12本（MIDI 92〜103）に
   * 収まるように全体を移調する。 */
  const SONGS = [
    { id: "kirakira", name: "きらきら星", bpm: 90,
      mel: "C:1 C:1 G:1 G:1 A:1 A:1 G:2 F:1 F:1 E:1 E:1 D:1 D:1 C:2 G:1 G:1 F:1 F:1 E:1 E:1 D:2 G:1 G:1 F:1 F:1 E:1 E:1 D:2 C:1 C:1 G:1 G:1 A:1 A:1 G:2 F:1 F:1 E:1 E:1 D:1 D:1 C:2" },
    { id: "kaeru", name: "かえるの合唱", bpm: 100,
      mel: "C:1 D:1 E:1 F:1 E:1 D:1 C:2 E:1 F:1 G:1 A:1 G:1 F:1 E:2 C:2 C:2 C:2 C:2 C:0.5 C:0.5 D:0.5 D:0.5 E:0.5 E:0.5 F:0.5 F:0.5 E:1 D:1 C:2" },
    { id: "mary", name: "メリーさんの羊", bpm: 100,
      mel: "E:1.5 D:0.5 C:1 D:1 E:1 E:1 E:2 D:1 D:1 D:2 E:1 G:1 G:2 E:1.5 D:0.5 C:1 D:1 E:1 E:1 E:2 D:1 D:1 E:1.5 D:0.5 C:4" },
    { id: "tulip", name: "チューリップ", bpm: 100,
      mel: "C:1 D:1 E:2 C:1 D:1 E:2 G:1 E:1 D:1 C:1 D:1 E:1 D:2 C:1 D:1 E:2 C:1 D:1 E:2 G:1 E:1 D:1 C:1 D:1 E:1 C:2 G:1 G:1 E:1 G:1 A:1 A:1 G:2 E:1 E:1 D:1 D:1 C:4" },
    { id: "joy", name: "喜びの歌（第九）", bpm: 110,
      mel: "E:1 E:1 F:1 G:1 G:1 F:1 E:1 D:1 C:1 C:1 D:1 E:1 E:1.5 D:0.5 D:2 E:1 E:1 F:1 G:1 G:1 F:1 E:1 D:1 C:1 C:1 D:1 E:1 D:1.5 C:0.5 C:2" },
    { id: "london", name: "ロンドン橋", bpm: 110,
      mel: "G:1.5 A:0.5 G:1 F:1 E:1 F:1 G:2 D:1 E:1 F:2 E:1 F:1 G:2 G:1.5 A:0.5 G:1 F:1 E:1 F:1 G:2 D:2 G:2 E:1 C:3" },
    { id: "bunbun", name: "ぶんぶんぶん", bpm: 110,
      mel: "G:1 F:1 E:2 D:1 E:1 F:1 D:1 C:2 R:2 E:1 F:1 G:1 E:1 D:1 E:1 F:1 D:1 E:1 F:1 G:1 E:1 D:1 E:1 F:1 D:1 G:1 F:1 E:2 D:1 E:1 F:1 D:1 C:2" },
    { id: "saints", name: "聖者の行進", bpm: 120,
      mel: "C:1 E:1 F:1 G:4 R:1 C:1 E:1 F:1 G:4 R:1 C:1 E:1 F:1 G:2 E:2 C:2 E:2 D:4 R:2 E:1 E:1 D:1 C:3 C:1 E:2 G:2 G:1 F:3 R:1 E:1 F:1 G:2 E:2 C:2 D:2 C:4" },
    { id: "musunde", name: "むすんでひらいて", bpm: 100,
      mel: "E:1 E:1 D:1 C:1 C:2 D:1 D:1 E:1 D:1 C:2 G:1 G:1 F:1 E:1 E:2 D:1 D:1 E:1 D:1 C:2" },
    { id: "scale", name: "長音階の上り下り（練習）", bpm: 80,
      mel: "C:1 D:1 E:1 F:1 G:1 A:1 B:1 R:1 B:1 A:1 G:1 F:1 E:1 D:1 C:2" },
    { id: "chrom", name: "半音階の上り下り（12本すべて）", bpm: 80, absolute: true,
      mel: "G#:1 A:1 A#:1 B:1 C':1 C#':1 D':1 D#':1 E':1 F':1 F#':1 G':1 F#':1 F':1 E':1 D#':1 D':1 C#':1 C':1 B:1 A#:1 A:1 G#:2" },
  ];
  const PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

  /* 曲の文字列を [{midi|null, beats}] にする（ハ長調・C4=60 を基準にした仮の高さ） */
  function parseMelody(text) {
    const out = [];
    for (const tok of text.trim().split(/\s+/)) {
      const m = tok.match(/^([A-GR])([#b]?)([',]*):([\d.]+)$/);
      if (!m) throw new Error("曲の書き方が読めない: " + tok);
      const beats = parseFloat(m[4]);
      if (m[1] === "R") { out.push({ midi: null, beats }); continue; }
      let midi = 60 + PC[m[1]] + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0);
      for (const c of m[3]) midi += c === "'" ? 12 : -12;
      out.push({ midi, beats });
    }
    return out;
  }
  /* 笛の12本（lo〜hi）に収まる移調の幅を探す。候補が複数あれば、主音が A♭ に近いもの（A♭ 長調）を選ぶ */
  function fitShift(notes, lo, hi, preferPc) {
    lo = lo === undefined ? 92 : lo; hi = hi === undefined ? 103 : hi;
    const ms = notes.filter(n => n.midi !== null).map(n => n.midi);
    const mn = Math.min.apply(null, ms), mx = Math.max.apply(null, ms);
    if (mx - mn > hi - lo) return null;
    const cands = [];
    for (let s = lo - mn; s <= hi - mx; s++) cands.push(s);
    const want = preferPc === undefined ? 8 : preferPc;
    cands.sort((a, b) => {
      const da = Math.min(((a - want) % 12 + 12) % 12, ((want - a) % 12 + 12) % 12);
      const db = Math.min(((b - want) % 12 + 12) % 12, ((want - b) % 12 + 12) % 12);
      return da - db || a - b;
    });
    return cands[0];
  }
  /* 曲を笛の音域へ移調して返す。absolute の曲は書いた高さのまま（G#=G#6 として）置く */
  function songNotes(song) {
    const notes = parseMelody(song.mel);
    let shift;
    if (song.absolute) shift = 92 - 68;       // G#4(68) を G#6(92) に
    else shift = fitShift(notes);
    if (shift === null) throw new Error("音域が12本に収まらない: " + song.name);
    let t = 0;
    return {
      keyPc: ((0 + shift) % 12 + 12) % 12,
      notes: notes.map(n => { const r = { midi: n.midi === null ? null : n.midi + shift, beats: n.beats, start: t }; t += n.beats; return r; }),
      totalBeats: t,
    };
  }

  const api = { MAJOR, MINOR, FLAT_NAMES, KEYS, inScale, diatonicBelow, DEGREES, degreeChord, chordName, chordPcs,
                PROGRESSIONS, SONGS, parseMelody, fitShift, songNotes };
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IRKTheory = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
