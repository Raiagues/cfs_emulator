// Chapter state, timing and drawings from the Welcome design. One tick is 100 ms.
export class Welcome {
  constructor() {
    this.state = {
      ch: 0,
      found: {},
      sel: null,
      rdBeat: 1,
      rdChat: [],
      rdClock: 602,
      rdChk: null,
      rdChkId: 0,
      rdFlare: false,
      rdTrue: 80,
      rdShield: false,
      rdDead: false,
      rdReveal: false,
      rdDrain: false,
      rdCharge: false,
      rdFlash: 0,
      pk: null,
      rdCap: null,
      hitT: 0,
      pwBeat: 1,
      pwT: 0,
      pwT0: 0,
      pwPlay: false,
      pwPhotos: 0,
      pwCam: false,
      pwSafeOn: false,
      pwBat: 70,
      pwOff: false,
      pwMode: 'normal',
      pwEarly: false,
      pwCap: null,
      pwSh: false,
      saBeat: 1,
      saMode: 'one',
      saRun: true,
      saPhi: 40,
      saBurn: false,
      saBurnT: 0,
      saPass: 0,
      saLog: [],
      saCap: null,
      mis: null,
      fin: {},
      lyBeat: 1,
      lyAt: 'laptop',
      lyLay: false,
      lyBad: false,
      lyDone: {},
      lyCap: null,
      lyA: -1,
      fwPhase: 'quiz',
      fwQ: 0,
      fwAns: {},
      fwWrong: 0,
      fwHint: '',
      fwT: 0,
      fwBeat: 1,
      fwSel: null,
      fwSeen2: {},
      fwCap: null,
      flOn: false,
      flStart: false,
      flStop: false,
      flT: 0,
      flN: 0,
      flGot: 0,
      flLog: [],
      flPills: [],
      flDone: false,
      flWait: 0,
      flSec: 0,
      flSnap: 0,
      osT: 0,
      osJob: false,
      osJob0: 0,
      osBeat: 1,
      osMis: {},
      osOs: 'linux',
      osSeen: {},
      osSw: 0,
      osCap: null,
      bdSel: 'laptop',
      bdSeen: { laptop: true },
      bdTest: 0,
      bdT: 0,
      bdCap: null,
      cfT: 0,
      cfZ: null,
      cfZT: 0,
      cfSeen: {},
      cfCap: null,
      gT: 0,
      gPlay: false,
      gBook: {},
      gPh: [],
      gN: 0,
      gMem: [],
      gGal: [],
      gFly: [],
      gLost: 0,
      gCost: 0,
      gBuf: 0,
      gSeen: {},
      gCap: null,
      gHold: 0,
      gDrop: 0,
      gWasPass: -1,
      gSnap: 0,
      gSnapI: 0,
      ctT: 560,
      ctPlay: false,
      ctSp: 's10',
      ctBand: 's',
      ctK: 4,
      ctBoard: 6,
      ctDown: 0,
      ctAcc: 0,
      ctBuf: 0,
      ctRes: {},
      ctDone: 0,
      ctIn: -1,
      csT: 0,
      csPlay: false,
      csBand: 's',
      csBud: 150,
      csBook: {},
      csCost: 0,
      csTaken: 0,
      csDown: 0,
      csAcc: 0,
      csBuf: 0,
      csUp: false,
      csEnd: false,
      csWin: false,
      csLive: -1,
      sQ: [],
      sT: 560,
      sPlay: false,
      sGd: false,
      sPol: 'stop',
      sMem: 512,
      sLostP: 0,
      sLostT: 0,
      sDown: 0,
      sAcc: { p: 0, t: 0, e: 0 },
      sFull: false,
      sTlmFull: false,
      sDropP: 0,
      sDropT: 0,
      pmode: 'mono',
      crash: null,
      crashT: 0,
      tried: {},
      lmode: 'none',
      plat: 'laptop',
      lchg: null,
      lT: 0,
      fwMode: 'scratch',
      fwToggled: false,
      fw: null,
      fwSeen: {},
      lv: 0,
      focus: null,
      t: 0,
      tk: 0,
      place: null,
      placed: false,
      k: 0,
      auto: false,
      at: 0,
      stVis: { 0: true },
    };
    this._init = Object.assign({}, this.state);
  }
  setState(update) {
    Object.assign(this.state, update);
  }
  setPlace(place) {
    this.setState({ place, placed: true });
  }
  passes() {
    return [
      [24, 7],
      [120, 11],
      [600, 6],
      [696, 12],
      [792, 9],
      [1368, 5],
    ];
  }
  passAt(t) {
    const m = ((t % 1440) + 1440) % 1440,
      P = this.passes();
    for (let i = 0; i < P.length; i++) {
      if (Math.abs(m - P[i][0]) <= P[i][1] / 2) return i;
    }
    return -1;
  }
  clock(t) {
    const m = ((Math.floor(t) % 1440) + 1440) % 1440;
    return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
  }
  ovl(t0, t1) {
    const out = [],
      P = this.passes();
    for (let d = Math.floor(t0 / 1440) - 1; d <= Math.floor(t1 / 1440); d++) {
      P.forEach((x, i) => {
        const a = d * 1440 + x[0] - x[1] / 2,
          b = a + x[1],
          o = Math.min(t1, b) - Math.max(t0, a);
        if (o > 0) out.push([i, o, b <= t1]);
      });
    }
    return out;
  }
  rate(b) {
    return { uhf: 0.072, s: 15, x: 750 }[b];
  }
  tick() {
    const s = this.state,
      p = {},
      ch = s.ch;
    if (ch === 1 && s.pk) this.tickRad(s, p);
    if (ch === 1) this.tickRadBg(s, p);
    if (p.rdCap === undefined && s.rdCap && s.rdCap.n > 0) p.rdCap = Object.assign({}, s.rdCap, { n: s.rdCap.n - 1 });
    if (p.pwCap === undefined && s.pwCap && s.pwCap.n > 0) p.pwCap = Object.assign({}, s.pwCap, { n: s.pwCap.n - 1 });
    if (p.gCap === undefined && s.gCap && s.gCap.n > 0) p.gCap = Object.assign({}, s.gCap, { n: s.gCap.n - 1 });
    if (s.hitT > 0) p.hitT = s.hitT - 1;
    if (ch === 2 && s.pwPlay) this.tickPow(s, p);
    if (ch === 3 && s.gPlay) this.tickGround(s, p);
    if (ch === 4) this.tickSa(s, p);
    if (ch === 7) this.tickFw(s, p);
    if (ch === 5) {
      p.osT = s.osT + 1;
      if (s.osBeat === 1 && s.osJob && !s.osCap && this.osLate(s) >= 6) {
        p.osCap = { t: 'Linux was late: the camera missed its target', c: 'r', n: 50 };
      }
    }
    if (ch === 12) {
      if (s.bdT < 50) p.bdT = s.bdT + 1;
      if (s.bdTest > 0 && s.bdTest < 44) {
        p.bdTest = s.bdTest + 1;
        if (s.bdTest === 18) p.bdCap = this.bdRes(s.bdSel);
      }
    }
    if (p.osCap === undefined && s.osCap && s.osCap.n > 0) p.osCap = Object.assign({}, s.osCap, { n: s.osCap.n - 1 });
    if (p.bdCap === undefined && s.bdCap && s.bdCap.n > 0) p.bdCap = Object.assign({}, s.bdCap, { n: s.bdCap.n - 1 });
    if (ch === 11) {
      if (s.cfT < 100) p.cfT = s.cfT + 1;
      if (s.cfZ) p.cfZT = s.cfZT + 1;
    }
    if (s.cfCap && s.cfCap.n > 0 && p.cfCap === undefined) p.cfCap = Object.assign({}, s.cfCap, { n: s.cfCap.n - 1 });
    if (p.fwCap === undefined && s.fwCap && s.fwCap.n > 0) p.fwCap = Object.assign({}, s.fwCap, { n: s.fwCap.n - 1 });
    if (p.saCap === undefined && s.saCap && s.saCap.n > 0) p.saCap = Object.assign({}, s.saCap, { n: s.saCap.n - 1 });
    if (p.lyCap === undefined && s.lyCap && s.lyCap.n > 0) p.lyCap = Object.assign({}, s.lyCap, { n: s.lyCap.n - 1 });
    if (ch === 4 && s.csPlay) this.tickCost(s, p);
    if (ch === 5 && s.sPlay) this.tickSto(s, p);
    if (s.sDropP > 0) p.sDropP = s.sDropP - 1;
    if (s.sDropT > 0) p.sDropT = s.sDropT - 1;
    if (s.crash) {
      if (s.crashT >= 32) {
        p.crash = null;
        p.crashT = 0;
      } else p.crashT = s.crashT + 1;
    }
    if (s.lchg && s.lT < 10) p.lT = s.lT + 1;
    if (ch === 8 && s.lv >= 3) {
      p.tk = s.tk + 1;
      if (p.tk % 2 === 0) p.t = s.t + 1;
    }
    if (ch === 10 && s.auto) {
      if (s.at >= 27) {
        p.at = 0;
        const nk = Math.min(8, s.k + 1);
        p.k = nk;
        p.stVis = Object.assign({}, s.stVis, { [nk]: true });
        if (nk === 8) p.auto = false;
      } else p.at = s.at + 1;
    }
    if (Object.keys(p).length) this.setState(p);
  }
  // radiation
  say(chat, who, t, clock) {
    const c = chat.concat([{ who, t, time: this.clock(clock) }]);
    return c.slice(-6);
  }
  radAct() {
    const s = this.state;
    if (s.pk) return;
    const b = s.rdBeat,
      ck = s.rdClock + 1;
    if (b === 1 || b === 2 || b === 4)
      this.setState({
        rdClock: ck,
        rdChat: this.say(s.rdChat, 'g', 'Request battery level', ck),
        pk: { dir: 'up', kind: 'ask', p: 0, t: 'Request battery level' },
        rdCap: null,
        rdChk: null,
      });
    else if (b === 3)
      this.setState({
        rdClock: ck,
        rdChat: this.say(s.rdChat, 'g', 'Start imaging: 50 photos', ck),
        pk: { dir: 'up', kind: 'cmd', p: 0, t: 'Start imaging: 50 photos' },
        rdCap: null,
      });
    else if (b === 5)
      this.setState({
        rdClock: ck,
        rdChat: this.say(s.rdChat, 'g', 'Postpone imaging until battery > 50%', ck),
        pk: { dir: 'up', kind: 'charge', p: 0, t: 'Postpone imaging' },
        rdCap: null,
        rdChk: null,
      });
  }
  tickRad(s, p) {
    const pk = Object.assign({}, s.pk);
    if (pk.hold > 0) {
      pk.hold--;
      p.pk = pk;
      return;
    }
    pk.p += 0.04;
    if (pk.kind === 'ans' && pk.p >= 0.5 && pk.hit && !pk.flipped) {
      pk.flipped = true;
      pk.p = 0.5;
      pk.hold = 16;
      p.hitT = 16;
      p.rdCap = { t: 'radiation flipped one bit', c: 'r', x: 720, y: 96, n: 22 };
    }
    if (pk.p < 1) {
      p.pk = pk;
      return;
    }
    const b = s.rdBeat,
      ck = s.rdClock + 1,
      ones = (n) =>
        n
          .toString(2)
          .split('')
          .filter((c) => c === '1').length;
    if (pk.kind === 'ask') {
      p.pk = {
        dir: 'down',
        kind: 'ans',
        p: 0,
        num: s.rdTrue,
        hit: s.rdFlare && (b === 2 || b === 4) && !pk.resend,
        flipped: false,
        hold: 4,
      };
      return;
    }
    if (pk.kind === 'ans') {
      const v = pk.flipped ? pk.num ^ 64 : pk.num;
      p.rdClock = ck;
      const dsum = (n) =>
        String(n)
          .split('')
          .reduce((x, d) => x + Number(d), 0);
      if (s.rdShield) {
        p.rdChk = { v, chk: dsum(pk.num), ok: !pk.flipped, n: 50 };
        p.rdChkId = s.rdChkId + 1;
      }
      if (pk.flipped && s.rdShield) {
        p.rdChat = this.say(s.rdChat, 'w', 'Check failed: message thrown away, asked again', ck);
        p.pk = { dir: 'up', kind: 'ask', p: -1.2, t: 'Request battery level', resend: true };
        p.rdCap = null;
        return;
      }
      p.rdChat = this.say(s.rdChat, 's', 'Battery level: ' + v + '%', ck);
      p.pk = null;
      if (b === 1) {
        p.rdBeat = 2;
        p.rdTrue = 16;
        p.rdClock = ck + 240;
        p.rdCap = { t: '4 hours later', c: 'b', x: 980, y: 300, n: 30 };
      } else if (b === 2) p.rdBeat = 3;
      else if (b === 4) {
        p.rdBeat = 5;
        p.rdCap = null;
      }
      return;
    }
    if (pk.kind === 'cmd') {
      p.pk = null;
      p.rdDrain = true;
      p.rdFlash = 12;
      return;
    }
    if (pk.kind === 'charge') {
      p.pk = null;
      p.rdCharge = true;
      p.rdCap = { t: 'right data, right decision', c: 'g', x: 980, y: 300, n: 60 };
      p.rdBeat = 6;
    }
  }
  tickRadBg(s, p) {
    if (s.rdFlash > 0) p.rdFlash = s.rdFlash - 1;
    if (s.rdChk && s.rdChk.n > 0 && !s.pk) p.rdChk = Object.assign({}, s.rdChk, { n: s.rdChk.n - 1 });
    if (s.rdDrain) {
      const t = Math.max(0, s.rdTrue - 1);
      p.rdTrue = t;
      if (t === 0) {
        p.rdDrain = false;
        p.rdDead = true;
        p.rdChat = this.say(s.rdChat, 'r', 'No telemetry from the satellite', s.rdClock + 3);
        p.rdReveal = true;
        p.rdBeat = 4;
        p.rdCap = { t: 'it was really 16%', c: 'r', x: 980, y: 300, n: 40 };
      }
    }
    if (s.rdCharge && s.rdTrue < 70) p.rdTrue = s.rdTrue + 1;
  }
  // power
  powGeo(t) {
    const deg = 180 + 4 * t,
      th = (deg * Math.PI) / 180,
      c = Math.cos(th),
      sn = Math.sin(th);
    return { x: 590 + 175 * c, y: 230 + 175 * sn, shadow: c > 0 && Math.abs(sn) < 0.686 };
  }
  tickPow(s, p) {
    const t = s.pwT + 1,
      g = this.powGeo(t),
      lit = !g.shadow;
    let off = s.pwOff,
      mode = s.pwMode,
      early = s.pwEarly,
      beat = s.pwBeat,
      cap = null;
    const camOn = s.pwCam && mode === 'normal' && !off;
    const load = off ? 0 : 5 + (camOn ? 8 : 0),
      solar = lit ? 14 : 0;
    let bat = Math.max(0, Math.min(100, s.pwBat + (solar - load) / 6));
    if (g.shadow && !s.pwSh) cap = { t: 'no sun: battery only', c: 'b', n: 16 };
    if (lit && s.pwSh) cap = { t: 'sun: charging', c: 's', n: 16 };
    if (bat <= 0 && !off) {
      off = true;
      mode = 'safe';
      cap = { t: 'battery empty: satellite off', c: 'r', n: 30 };
      if (beat === 2) beat = 3;
    }
    if (off && lit && bat > 6) {
      off = false;
      cap = { t: 'it wakes up in safe mode', c: 'w', n: 26 };
    }
    if (!off && mode === 'normal' && s.pwSafeOn && s.pwCam && bat < 30) {
      mode = 'safe';
      early = true;
      cap = { t: 'below 30%: software stops the camera', c: 'g', n: 30 };
    }
    if (mode === 'safe' && !off && bat >= 60) {
      mode = 'normal';
      cap = { t: 'charged: photos again', c: 'g', n: 24 };
      if (beat === 3 && s.pwSafeOn && early) {
        beat = 4;
        cap = { t: 'it never ran empty', c: 'g', n: 50 };
      }
    }
    if (beat === 1 && t - s.pwT0 >= 90) beat = 2;
    Object.assign(p, {
      pwT: t,
      pwBat: bat,
      pwOff: off,
      pwMode: mode,
      pwEarly: early,
      pwBeat: beat,
      pwSh: g.shadow,
      pwPhotos: s.pwPhotos + (camOn && t % 6 === 0 ? 1 : 0),
    });
    if (cap) p.pwCap = cap;
  }
  // shared: the mission the user picked
  misOf(k) {
    const CAM = 'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 110 7 3.5 3.5 0 010-7z',
      WHL =
        'M12 8a4 4 0 110 8 4 4 0 010-8zM12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1',
      EYE = 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 110 6 3 3 0 010-6z';
    const M = {
      wx: {
        app: 'Photo app',
        key: 'photo_app',
        job: 'every 10 s, take a photo',
        verb: 'take a photo',
        dev: 'Camera',
        icon: CAM,
        veh: 'satellite',
        heat: 'Camera in full sun',
        out: (n) => 'Photo ' + n + ' saved',
      },
      rv: {
        app: 'Drive app',
        key: 'drive_app',
        job: 'every 10 s, drive 1 m',
        verb: 'drive 1 m',
        dev: 'Wheel motor',
        icon: WHL,
        veh: 'rover',
        heat: 'Motor gets too hot',
        out: (n) => 'Drove ' + n + ' m',
      },
      ts: {
        app: 'Star app',
        key: 'star_app',
        job: 'every 10 s, measure a star',
        verb: 'measure the star',
        dev: 'Light sensor',
        icon: EYE,
        veh: 'telescope',
        heat: 'Sensor gets too hot',
        out: (n) => 'Star brightness ' + (812 + ((n * 7) % 9)),
      },
    };
    return M[k] || M.wx;
  }
  mclock(t) {
    const v = Math.floor(t);
    return String(Math.floor(v / 60)).padStart(2, '0') + ':' + String(v % 60).padStart(2, '0');
  }
  along(W, u) {
    const L = [];
    let tot = 0;
    for (let i = 1; i < W.length; i++) {
      const d = Math.hypot(W[i][0] - W[i - 1][0], W[i][1] - W[i - 1][1]);
      L.push(d);
      tot += d;
    }
    let r = u * tot;
    for (let i = 0; i < L.length; i++) {
      if (r <= L[i]) {
        const f = r / L[i];
        return { x: W[i][0] + (W[i + 1][0] - W[i][0]) * f, y: W[i][1] + (W[i + 1][1] - W[i][1]) * f, seg: i };
      }
      r -= L[i];
    }
    return { x: W[W.length - 1][0], y: W[W.length - 1][1], seg: L.length - 1 };
  }
  // frameworks
  tickFw(s, p) {
    if (s.fwPhase === 'quiz' && s.fwQ >= 9) {
      const t = s.fwT + 1;
      p.fwT = t;
      if (t >= 26) {
        p.fwPhase = 'lit';
        p.fwT = 0;
      }
    } else if (s.fwPhase === 'lit') {
      const t = s.fwT + 1;
      p.fwT = t;
      if (t >= 22) {
        p.fwPhase = 'shelf';
        p.fwBeat = 2;
        p.fwCap = { t: 'build them once, reuse them: that is a framework', c: 'g', n: 44 };
      }
    } else if (s.fwPhase === 'shelf' && s.fwBeat === 2) {
      const t = s.fwT + 1;
      p.fwT = t;
      if (t === 70) p.fwCap = { t: 'now pick your mission', c: 's', n: 9999 };
    }
    if (s.fwBeat === 3) this.tickFlow(s, p);
  }
  tickFlow(s, p) {
    if (!s.flStart) return;
    const m = this.misOf(s.mis);
    let pills = s.flPills.map((x) => Object.assign({}, x, { p: Math.min(1, x.p + x.v) }));
    const arr = pills.filter((x) => x.p >= 1);
    pills = pills.filter((x) => x.p < 1);
    let log = s.flLog,
      on = s.flOn,
      t = s.flT,
      n = s.flN,
      got = s.flGot,
      done = s.flDone,
      lg = false,
      snap = s.flSnap > 0 ? s.flSnap - 1 : 0;
    const sec = s.flSec + 0.5;
    const add = (who, txt, ts) => {
      log = log.concat([{ who, t: txt, time: this.mclock(ts === undefined ? sec : ts) }]).slice(-8);
      lg = true;
    };
    arr.forEach((x) => {
      if (x.k === 'start') {
        on = true;
        t = 0;
      } else if (x.k === 'tick') {
        if (on) {
          n += 1;
          pills.push({ k: 'out', w: 'out', p: 0, v: 0.07, t: m.out(n), ts: sec });
          snap = 5;
        }
      } else if (x.k === 'out') {
        got += 1;
        add('s', x.t, x.ts);
      } else if (x.k === 'stop') {
        on = false;
        pills.push({ k: 'ack', w: 'out', p: 0, v: 0.07, t: m.app + ' stopped', ts: sec });
      } else if (x.k === 'ack') {
        add('g', x.t, x.ts);
        done = true;
      }
    });
    if (on) {
      t += 0.5;
      if (t >= 8) {
        t = -2;
        pills.push({ k: 'tick', w: 'tick', p: 0, v: 0.25, t: '10 s' });
      }
    }
    Object.assign(p, { flPills: pills, flOn: on, flT: t, flN: n, flGot: got, flDone: done, flSec: sec, flSnap: snap });
    if (lg) p.flLog = log;
    if (done) {
      const w = s.flWait + 1;
      p.flWait = w;
      if (w === 1) p.fwCap = { t: 'the framework carried every message', c: 'g', n: 34 };
      if (w >= 36) {
        p.fwBeat = 4;
        p.fwCap = { t: 'other frameworks do it in other ways', c: 's', n: 40 };
      }
    }
  }
  // separate apps
  saT(a) {
    const T = [
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      101, 84, 67, 52, 38, 25, 12, 1, -9, -19, -28, -37, -45, -52, -59, -65, -71, -77, -82, -87, -91, -95, -99, -103, -106,
      -109, -112, -115, -117, -119, -122, -124, -125, -127, -129, -130, -132, -133, -134, -135, -136, -137, -138, -139, -140,
      -140, -141, -142, -142, -143, -143, -144, -144, -145, -145, -145, -146, -146, -146, -147, -147, -147, -147, -147, -148,
      -148, -148, -148, -148, -148, -148, -149, -149, -130, -112, -96, -81, -67, -54, -42, -30, -20, -10, -1, 8, 15, 23, 30,
      36, 42, 47, 52, 57, 61, 66, 69, 73, 76, 79, 82, 85, 87, 90, 92, 94, 96, 97, 99, 100, 102, 103, 104, 105, 106, 107, 108,
      109, 110, 110, 111, 112, 112, 113, 113, 114, 114, 115, 115, 115, 116, 116, 116, 117, 117, 117, 117, 117, 118, 118, 118,
      118, 118, 118, 118, 119, 119, 119, 119, 119, 119, 119, 119, 119, 119, 119, 119, 119, 119, 119, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120, 120,
      120, 120, 120, 120,
    ];
    return T[((Math.floor(a) % 360) + 360) % 360];
  }
  tickSa(s, p) {
    if (!s.saRun) return;
    const phi = s.saPhi + 2.5,
      a = ((phi % 360) + 360) % 360,
      a0 = ((s.saPhi % 360) + 360) % 360;
    p.saPhi = phi;
    let log = s.saLog,
      lg = false;
    const add = (who, t) => {
      log = log.concat([{ who, t }]).slice(-4);
      lg = true;
    };
    const burnT = s.saBurn ? s.saBurnT + 1 : 0;
    if (s.saBurn) p.saBurnT = burnT;
    const radio = !(s.saMode === 'one' && s.saBurn && burnT >= 9);
    const inP = Math.abs(a - 180) < 22,
      wasP = Math.abs(a0 - 180) < 22;
    if (inP && !wasP) {
      const n = s.saPass + 1;
      p.saPass = n;
      if (radio) add('g', 'pass ' + n + ' · ' + (s.saBurn ? 'camera stopped · rest OK' : 'battery 76% · all OK'));
      else add('r', 'pass ' + n + ' · no answer');
      if (s.saBurn && !radio) p.saCap = { t: "the ground can't reach it anymore", c: 'r', n: 60 };
      if (s.saBurn && s.saMode === 'sep' && s.saBeat === 3) {
        p.saCap = { t: 'the radio kept working: the ground knows what broke', c: 'g', n: 70 };
        p.saBeat = 4;
      }
    }
    if (!inP && wasP && s.saBurn && s.saMode === 'one') {
      p.saRun = false;
      p.saBeat = 2;
    }
    if (!s.saBurn && s.saPass >= 1 && a >= 338 && a < 343) {
      p.saBurn = true;
      p.saBurnT = 0;
      p.saCap = { t: 'a camera part burned in the heat', c: 'r', n: 30 };
    }
    if (s.saBurn && s.saMode === 'one' && burnT === 14)
      p.saCap = { t: 'one program: the crash took the radio down too', c: 'r', n: 50 };
    if (s.saBurn && s.saMode === 'sep' && burnT === 14) p.saCap = { t: 'only the camera app stopped', c: 'w', n: 40 };
    if (lg) p.saLog = log;
  }
  // operating system
  osH(j, k) {
    const v = Math.sin(j * 12.9898 + k * 78.233) * 43758.5453;
    return v - Math.floor(v);
  }
  osDelay(s, j, lin) {
    if (!lin) return 0;
    const job = s.osJob && j * 70 >= s.osJob0;
    return job ? (this.osH(j, 1) < 0.55 ? 18 + this.osH(j, 2) * 34 : this.osH(j, 2) * 6) : this.osH(j, 3) * 4;
  }
  osLate(s) {
    if (!s.osJob) return 0;
    const P = s.osT * 7;
    let n = 0;
    for (let j = Math.ceil(s.osJob0 / 70); j * 70 <= P; j++) if (this.osDelay(s, j, true) > 14) n++;
    return n;
  }
  // boards
  bdRes(k) {
    return (
      {
        laptop: { t: 'not built for radiation: it can crash', c: 'r', n: 50 },
        pi: { t: 'not built for radiation: it can crash', c: 'r', n: 50 },
        cube: { t: 'made to cope with some radiation', c: 'g', n: 50 },
        rad: { t: 'built to keep running in radiation', c: 'g', n: 50 },
      }[k] || null
    );
  }
  // layers
  tickLy(s, p) {
    if (s.lyA >= 0 && s.lyA < 70) {
      const a = s.lyA + 1;
      p.lyA = a;
      if (a === 62) {
        const d = Object.assign({}, s.lyDone, { [s.lyAt]: true });
        p.lyDone = d;
        p.lyCap = {
          t:
            s.lyAt === 'pi'
              ? 'the Pi runs Linux too: same layers'
              : s.lyAt === 'flight'
                ? 'only the bottom layers changed'
                : 'it runs',
          c: 'g',
          n: 50,
        };
        if (d.flight) p.lyBeat = 4;
      }
    }
  }
  // ground
  gGeo(t) {
    const R = Math.PI / 180,
      th = 180 + 3.75 * t,
      sat = [450 + 196 * Math.cos(th * R), 240 + 196 * Math.sin(th * R)];
    const nd = (d) => (((d % 360) + 540) % 360) - 180;
    const st = [250, 30].map((f0) => {
      const f = f0 + 0.25 * t;
      return { x: 450 + 92 * Math.cos(f * R), y: 240 + 92 * Math.sin(f * R), vis: Math.abs(nd(th - f)) < 28, d: nd(th - f) };
    });
    const TG = [
      [200, '#d4b48a'],
      [140, '#5fc9a3'],
      [80, '#7cb4f0'],
      [20, '#e7c4dc'],
      [320, '#d4b48a'],
      [260, '#5fc9a3'],
    ];
    const tg = TG.map((x) => {
      const f = x[0] + 0.25 * t;
      return { x: 450 + 92 * Math.cos(f * R), y: 240 + 92 * Math.sin(f * R), c: x[1], d: nd(th - f) };
    });
    return { sat, st, tg, th };
  }
  gSlowI(s) {
    const nB = (s.gBook[0] ? 1 : 0) + (s.gBook[1] ? 1 : 0),
      gs = s.gSeen || {};
    if (nB === 0) return 0;
    if (nB === 1 && gs.lost && !gs.both) return s.gBook[0] ? 1 : 0;
    return -1;
  }
  tickGround(s, p) {
    const si = this.gSlowI(s),
      g0 = this.gGeo(s.gT),
      slow = si >= 0 && g0.st[si].vis && !s.gBook[si];
    const dt = slow ? 0.125 : 0.5,
      k = dt / 0.5,
      t = s.gT + dt,
      g = this.gGeo(t),
      seen = Object.assign({}, s.gSeen);
    let ph = s.gPh.slice(),
      n = s.gN,
      buf = s.gBuf,
      cap = null,
      drop = s.gDrop > 0 ? s.gDrop - 1 : 0,
      snap = s.gSnap > 0 ? s.gSnap - 1 : 0;
    const fly = s.gFly
      .map((f) => Object.assign({}, f, { p: f.p + 0.1 * k }))
      .filter((f) => {
        if (f.p >= 1) {
          ph = ph.map((x) => (x.n === f.n ? Object.assign({}, x, { st: 'down' }) : x));
          return false;
        }
        return true;
      });
    if (t >= 5 && Math.floor((t - 5) / 10) > Math.floor((s.gT - 5) / 10)) {
      n += 1;
      snap = 4;
      if (ph.filter((x) => x.st === 'mem').length >= 6) {
        ph.push({ n, st: 'lost' });
        drop = 8;
        if (!seen.lost) {
          seen.lost = true;
          cap = { t: 'memory full: photo lost', c: 'r', n: 30, at: 'sat' };
        }
      } else {
        ph.push({ n, st: 'mem' });
        if (!seen.shot) {
          seen.shot = true;
          cap = { t: 'photo saved in memory', c: 's', n: 26, at: 'sat' };
        }
      }
    }
    let pass = -1;
    g.st.forEach((x, i) => {
      if (x.vis) pass = i;
    });
    if (pass >= 0 && s.gBook[pass]) {
      buf += 0.75 * dt;
      while (buf >= 1) {
        const i = ph.findIndex((x) => x.st === 'mem');
        if (i < 0) {
          buf = 1;
          break;
        }
        buf -= 1;
        ph[i] = Object.assign({}, ph[i], { st: 'fly' });
        fly.push({ n: ph[i].n, p: 0, i: pass });
      }
      if (!seen.paid && fly.length) {
        seen.paid = true;
        cap = { t: 'photos come down · $10 a minute', c: 's', n: 30, at: 'st', i: pass };
      }
    } else buf = 0;
    Object.assign(p, {
      gT: t,
      gPh: ph.slice(-48),
      gN: n,
      gFly: fly,
      gBuf: buf,
      gSeen: seen,
      gDrop: drop,
      gWasPass: pass,
      gSnap: snap,
    });
    if (cap) p.gCap = cap;
  }
  // cost
  tickCost(s, p) {
    const dt = 3,
      t = Math.min(1440, s.csT + dt),
      i = this.passAt(t),
      ov = this.ovl(s.csT, t),
      price = s.csBand === 'x' ? 22 : 10;
    let acc = s.csAcc + (dt * 2) / 96,
      taken = s.csTaken;
    while (acc >= 1) {
      acc -= 1;
      taken++;
    }
    let cost = s.csCost,
      buf = s.csBuf,
      down = s.csDown,
      up = s.csUp,
      any = false;
    ov.forEach(([k, o]) => {
      const bk = s.csBook[k] || {};
      if (!(bk.up || bk.dn)) return;
      any = true;
      cost += price * o;
      if (bk.up) up = true;
      if (bk.dn) {
        buf += this.rate(s.csBand) * o;
        while (buf >= 20 && taken - down > 0) {
          buf -= 20;
          down++;
        }
      }
    });
    if (!any) buf = 0;
    const bkNow = s.csBook[i] || {};
    Object.assign(p, {
      csT: t,
      csAcc: acc,
      csTaken: taken,
      csCost: cost,
      csBuf: buf,
      csDown: down,
      csUp: up,
      csLive: i >= 0 && (bkNow.up || bkNow.dn) ? i : -1,
    });
    if (t >= 1440) {
      const win = down >= 20 && up && cost <= s.csBud;
      p.csPlay = false;
      p.csEnd = true;
      p.csDayWin = win;
      p.csWin = s.csWin || win;
    }
  }
  // storage
  tickSto(s, p) {
    const dt = 2,
      t = s.sT + dt,
      cap = s.sMem / 4,
      q = s.sQ.slice(),
      acc = Object.assign({}, s.sAcc);
    let used = q.reduce((a, x) => a + x.n, 0),
      lostP = s.sLostP,
      lostT = s.sLostT,
      dropP = s.sDropP,
      dropT = s.sDropT,
      down = s.sDown;
    const add = (type, n) => {
      while (used + n > cap) {
        if (s.sPol === 'stop') {
          if (type === 'p') {
            lostP++;
            dropP = 6;
          } else if (type === 't') {
            lostT++;
            dropT = 6;
          }
          return;
        }
        let k = 0;
        if (s.sPol === 'tlm') {
          k = q.findIndex((x) => x.type === 'p');
          if (k < 0) {
            if (type === 'p') {
              lostP++;
              dropP = 6;
              return;
            }
            k = 0;
          }
        }
        const r = q.splice(k, 1)[0];
        used -= r.n;
        if (r.type === 'p') {
          lostP++;
          dropP = 6;
        } else if (r.type === 't') {
          lostT++;
          dropT = 6;
        }
      }
      q.push({ type, n, age: t });
      used += n;
    };
    acc.p += (dt * 4) / 96;
    acc.t += dt / 12;
    acc.e += dt / 48;
    while (acc.t >= 1) {
      acc.t -= 1;
      add('t', 1);
    }
    while (acc.e >= 1) {
      acc.e -= 1;
      add('e', 1);
    }
    while (acc.p >= 1) {
      acc.p -= 1;
      add('p', 5);
    }
    if (!s.sGd && this.passAt(t) >= 0) {
      let budget = 4 * dt;
      while (budget > 0 && q.length) {
        const h = q[0];
        if (h.n <= budget) {
          budget -= h.n;
          used -= h.n;
          q.shift();
          if (h.type === 'p') down++;
        } else {
          h.n -= budget;
          used -= budget;
          budget = 0;
        }
      }
    }
    const full = used >= cap - 1;
    Object.assign(p, {
      sT: t,
      sQ: q,
      sAcc: acc,
      sLostP: lostP,
      sLostT: lostT,
      sDropP: dropP,
      sDropT: dropT,
      sDown: down,
      sFull: s.sFull || full,
      sTlmFull: s.sTlmFull || (full && s.sPol === 'tlm'),
    });
  }
  hdr() {
    return {};
  }
  themeMap(o) {
    if (typeof o === 'string') {
      if (o.indexOf('#') < 0 && o.indexOf('rgb') < 0) return o;
      return o
        .replace(/#([0-9a-fA-F]{6})(?![0-9a-zA-Z_])/g, (m, h) => 'var(--c' + h.toLowerCase() + ')')
        .replace(
          /#([0-9a-fA-F]{3})(?![0-9a-zA-Z_])/g,
          (m, h) => 'var(--c' + (h[0] + h[0] + h[1] + h[1] + h[2] + h[2]).toLowerCase() + ')',
        )
        .replace(
          /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)/g,
          (m, r, g, b, a) => 'rgba(var(--r' + r + '_' + g + '_' + b + '),' + (a === undefined ? '1' : a) + ')',
        );
    }
    if (Array.isArray(o)) return o.map((x) => this.themeMap(x));
    if (o && typeof o === 'object') {
      const r = {};
      for (const k in o) r[k] = this.themeMap(o[k]);
      return r;
    }
    return o;
  }
  values() {
    return this.themeMap(this.scene());
  }
  scene() {
    const st = this.state,
      ch = st.ch,
      lv = st.lv,
      focus = st.focus;
    const SAND = '#d4b48a',
      SANDT = '#f3dcb8',
      SANDBG = '#2a241c',
      INK = '#1b150c';
    const GREEN = '#5fc9a3',
      GREENT = '#9fe3c9',
      GREENBG = '#16261f';
    const BLUE = '#7cb4f0',
      BLUET = '#a9cdf5',
      BLUEBG = '#16212e',
      RED = '#e5786d',
      REDBG = '#2a1a19';
    const LINE = '#262c34',
      LINE2 = '#343c47',
      CARD = '#1a1f25',
      TXT = '#eef0f2',
      MUTED = '#8e96a1',
      FAINT = '#5b636e';
    const CHIP = '#20252b',
      CHIPT = '#c9cfd6',
      PINKBG = '#241a22',
      PINKT = '#e7c4dc';
    const CHIPI = 'M6 6h12v12H6zM9.5 9.5h5v5h-5zM9 2.5V6M15 2.5V6M9 18v3.5M15 18v3.5';
    const HANDI =
      'M10 9.5V4a2 2 0 014 0v6l3.6.6a2.5 2.5 0 012.1 2.8L19 19a3 3 0 01-3 2.6h-4.3a3 3 0 01-2.4-1.2L5.6 17a1.8 1.8 0 012.7-2.4L10 16z';
    const ON = (a, b) => (a === b ? 'on' : '');
    const CO = (c) => (c ? 'fs-coach' : '');
    // ch0: satellite parts
    const PARTS = [
      {
        id: 'power',
        name: 'Power',
        role: 'sun → battery',
        icon: 'M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M12 7a5 5 0 110 10 5 5 0 010-10z',
        x: 174,
        y: 190,
      },
      {
        id: 'radio',
        name: 'Radio',
        role: 'talks to Earth',
        icon: 'M12 12v9M8.5 8.5a5 5 0 017 0M5.6 5.6a9 9 0 0112.8 0',
        x: 330,
        y: 84,
      },
      {
        id: 'adcs',
        name: 'Attitude',
        role: 'points the right way',
        icon: 'M12 3a9 9 0 110 18 9 9 0 010-18zM15 9l-2 5-4 1 2-5z',
        x: 362,
        y: 156,
      },
      {
        id: 'thermal',
        name: 'Thermal',
        role: 'not too hot or cold',
        icon: 'M10 13.5V5a2 2 0 014 0v8.5a4 4 0 11-4 0z',
        x: 300,
        y: 234,
      },
      {
        id: 'payload',
        name: 'Payload',
        role: 'the mission',
        icon: 'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 110 7 3.5 3.5 0 010-7z',
        x: 361,
        y: 276,
      },
      { id: 'obc', name: 'Computer', role: 'runs everything', icon: CHIPI, x: 330, y: 203 },
    ];
    const nFound = PARTS.filter((p) => st.found[p.id]).length,
      brain = nFound === 6;
    const nextPart = PARTS.find((p) => !st.found[p.id]);
    const pickPart = (id) => () => this.setState({ found: Object.assign({}, st.found, { [id]: true }), sel: id });
    const pc = (id) => (!st.found[id] ? '#4b525c' : st.sel === id || (brain && id === 'obc') ? SAND : '#9aa3ad');

    // ch1 radiation
    const pk = st.pk,
      beat = st.rdBeat,
      rdDone = Math.min(5, beat - 1);
    const P0 = [560, 380],
      P1 = [700, 120],
      P2 = [905, 205];
    let pp = pk ? Math.max(0, Math.min(1, pk.p)) : 0;
    if (pk && pk.dir === 'down') pp = 1 - pp;
    const bz = (a, b, c, u) => (1 - u) * (1 - u) * a + 2 * (1 - u) * u * b + u * u * c;
    const CAPC = { r: [REDBG, RED], g: [GREENBG, GREENT], w: [SANDBG, SANDT], s: [SANDBG, SANDT], b: [BLUEBG, BLUET] };
    const capv = (c, x, y) =>
      c && c.n > 0
        ? { cap: true, capT: c.t, capBg: CAPC[c.c][0], capFg: CAPC[c.c][1], capX: x, capY: y }
        : { cap: false, capT: '', capBg: CARD, capFg: TXT, capX: 0, capY: 0 };
    const pkNum = pk && pk.kind === 'ans' ? (pk.flipped ? pk.num ^ 64 : pk.num) : 0;
    const bin = (n) => n.toString(2).padStart(8, '0');
    const CH = { g: ['↑', SAND, SANDT], s: ['↓', BLUE, BLUET], w: ['!', SAND, SANDT], r: ['×', RED, RED] };
    const actT = {
      1: 'Request battery level',
      2: 'Request battery level',
      3: 'Start imaging: 50 photos',
      4: 'Request battery level',
      5: 'Postpone imaging until battery > 50%',
    }[beat];
    const ck2 = st.rdChk,
      ckOn = !!ck2 && ck2.n > 0,
      ckDig = ck2 ? String(ck2.v).split('') : [],
      ckSum = ckDig.reduce((x, d) => x + Number(d), 0);
    // ch3: partitions and layers
    const cr = st.crash,
      ct = st.crashT,
      tried = st.tried;
    const MODS = [
      ['Radio', false],
      ['Camera', false],
      ['Power', false],
      ['Your code', true],
    ];
    const mods = MODS.map((m) => {
      let state = 'run';
      if (cr) {
        if (cr === 'mono') state = 'stop';
        else if (m[1]) state = ct < 14 ? 'stop' : 'back';
      }
      return {
        t: m[0],
        mine: m[1],
        dot: state === 'stop' ? RED : GREEN,
        dotCls: state === 'run' ? 'fs-pulse' : state === 'back' ? 'fs-pop' : '',
        st: state === 'stop' ? 'stopped' : state === 'back' ? 'restarted' : 'running',
        sc: state === 'stop' ? RED : state === 'back' ? GREENT : MUTED,
        bg: state === 'stop' ? REDBG : CARD,
        bd: state === 'stop' ? '#5a3330' : st.pmode === 'apps' ? LINE2 : 'transparent',
        fg: state === 'stop' ? '#c9a09a' : TXT,
      };
    });
    const nextTry = !tried.mono
      ? st.pmode === 'mono'
        ? 'brk'
        : 'mono'
      : !tried.apps
        ? st.pmode === 'apps'
          ? 'brk'
          : 'apps'
        : !tried.none
          ? st.lmode === 'none'
            ? 'plat'
            : 'none'
          : !tried.lay
            ? st.lmode === 'lay'
              ? 'plat'
              : 'lay'
            : 'done';
    const n3 = ['mono', 'apps', 'none', 'lay'].filter((x) => tried[x]).length;
    const segv = (cur, key) => ({
      [key + 'Bg']: cur === key ? SAND : 'transparent',
      [key + 'Fg']: cur === key ? INK : CHIPT,
      [key + 'C']: nextTry === key ? 'fs-coach' : '',
    });
    const paRes = !cr
      ? ['pick the bug', MUTED, 'transparent', 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 8v5M12 16h.01']
      : cr === 'mono'
        ? ['everything stopped', RED, REDBG, 'M18 6L6 18M6 6l12 12']
        : ct < 14
          ? ['only one stopped', SANDT, SANDBG, 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 8v5M12 16h.01']
          : ['restarted, others never stopped', GREENT, GREENBG, 'M5 12l5 5L20 7'];
    const pa = Object.assign(
      {
        mono: st.pmode === 'mono',
        apps: st.pmode === 'apps',
        mods,
        boxBd: cr === 'mono' ? RED : LINE2,
        brkC: nextTry === 'brk' ? 'fs-coach' : '',
        brk: () => {
          if (st.crash) return;
          this.setState({ crash: st.pmode, crashT: 0, tried: Object.assign({}, tried, { [st.pmode]: true }) });
        },
        res: paRes[0],
        resFg: paRes[1],
        resBg: paRes[2],
        resIcon: paRes[3],
      },
      segv(st.pmode, 'mono'),
      segv(st.pmode, 'apps'),
    );
    pa.mono = st.pmode === 'mono';
    pa.apps = st.pmode === 'apps';
    const PLATS = [
      ['laptop', 'Laptop', 'Linux', 'M5 5h14v10H5zM2 19h20l-2-4H4z'],
      ['pi', 'Raspberry Pi', 'Linux', CHIPI],
      ['board', 'Flight board', 'RTEMS', 'M4 7h16v10H4zM8 7V4M16 7V4M8 17v3M16 17v3M8 11h8'],
    ];
    const lc = st.lchg,
      flash = lc && st.lT < 8;
    const lres = !lc
      ? ['change the board', MUTED, 'transparent', 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 8v5M12 16h.01']
      : lc === 'none'
        ? ['rewrite your app', RED, REDBG, 'M18 6L6 18M6 6l12 12']
        : ['app unchanged', GREENT, GREENBG, 'M5 12l5 5L20 7'];
    const lb = Object.assign(
      {
        layers: st.lmode === 'lay',
        code: lc === 'none' ? RED : lc === 'lay' ? GREEN : '#3a424c',
        appBd: lc === 'none' ? RED : lc === 'lay' ? GREEN : LINE2,
        tag: lc === 'none' ? 'rewrite' : 'no change',
        tagBg: lc === 'none' ? REDBG : GREENBG,
        tagFg: lc === 'none' ? RED : GREENT,
        tagO: lc ? 1 : 0,
        slab: flash ? SANDBG : CARD,
        slabBd: flash ? SAND : LINE,
        plats: PLATS.map((x) => ({
          t: x[1],
          os: x[2],
          icon: x[3],
          bd: st.plat === x[0] ? SAND : LINE,
          bg: st.plat === x[0] ? SANDBG : CARD,
          ic: st.plat === x[0] ? SAND : MUTED,
          coach:
            nextTry === 'plat' && st.plat !== x[0] && x[0] === (st.plat === 'laptop' ? 'pi' : 'laptop') ? 'fs-coach' : '',
          pick: () => {
            if (st.plat === x[0]) return;
            this.setState({ plat: x[0], lchg: st.lmode, lT: 0, tried: Object.assign({}, tried, { [st.lmode]: true }) });
          },
        })),
        res: lres[0],
        resFg: lres[1],
        resBg: lres[2],
        resIcon: lres[3],
      },
      segv(st.lmode, 'none'),
      segv(st.lmode, 'lay'),
    );

    // ch4: frameworks
    const fwOn = st.fwMode === 'fw';
    const BL = ['Scheduler', 'Messages', 'Commands', 'Telemetry', 'Events', 'Time', 'Tables', 'Health'];
    const FW = [
      {
        id: 'cfs',
        t: 'cFS',
        by: 'NASA Goddard',
        here: true,
        facts: [
          ['by', 'NASA Goddard'],
          ['in', 'C'],
          ['flew on', 'LRO · GPM · MMS'],
        ],
      },
      {
        id: 'fp',
        t: 'F Prime',
        by: 'NASA JPL',
        facts: [
          ['by', 'NASA JPL'],
          ['in', 'C++'],
          ['flew on', 'ASTERIA · Ingenuity'],
        ],
      },
      {
        id: 'kub',
        t: 'KubOS',
        by: 'Kubos',
        facts: [
          ['by', 'Kubos'],
          ['in', 'Rust · Python'],
          ['runs on', 'Kubos Linux'],
        ],
      },
      {
        id: 'rod',
        t: 'RODOS',
        by: 'DLR · Univ. Würzburg',
        facts: [
          ['by', 'DLR · Univ. Würzburg'],
          ['in', 'C++'],
          ['flew on', 'TET-1 · BIROS'],
        ],
      },
      {
        id: 'nmf',
        t: 'NanoSat MO Framework',
        by: 'ESA · TU Graz',
        facts: [
          ['by', 'ESA · TU Graz'],
          ['in', 'Java'],
          ['flew on', 'OPS-SAT'],
        ],
      },
    ];
    const nSeenFw = FW.filter((x) => st.fwSeen[x.id]).length,
      n4 = (st.fwToggled ? 1 : 0) + Math.min(2, nSeenFw);
    const nextFw = FW.find((x) => !st.fwSeen[x.id]);
    const fwCur = FW.find((x) => x.id === st.fw);
    const fwt = {
      scratchGo: () => this.setState({ fwMode: 'scratch' }),
      fwGo: () => this.setState({ fwMode: 'fw', fwToggled: true }),
      scratchBg: !fwOn ? SAND : 'transparent',
      scratchFg: !fwOn ? INK : CHIPT,
      scratchC: '',
      fwBg: fwOn ? SAND : 'transparent',
      fwFg: fwOn ? INK : CHIPT,
      fwC: !st.fwToggled ? 'fs-coach' : '',
    };

    // ch2 power
    const g2 = this.powGeo(st.pwT),
      pwU = [(g2.x - 590) / 175, (g2.y - 230) / 175],
      pwE = [590 + pwU[0] * 122, 230 + pwU[1] * 122],
      pwC = [
        [pwE[0] - pwU[1] * 26, pwE[1] + pwU[0] * 26],
        [pwE[0] + pwU[1] * 26, pwE[1] - pwU[0] * 26],
      ],
      pwB = [g2.x + (g2.x < 560 ? -66 : 62), Math.max(48, Math.min(400, g2.y))],
      pwDone = st.pwBeat >= 4 ? 3 : st.pwBeat - 1;
    const pwCamOn = st.pwCam && st.pwMode === 'normal' && !st.pwOff;
    const pcx = st.pwCap ? (st.pwCap.c === 'g' || st.pwCap.c === 'r' ? g2.x : 590) : 0,
      pcy = st.pwCap ? (g2.y < 230 ? g2.y + 70 : g2.y - 80) : 0;
    // ch3 ground
    const G = this.gGeo(st.gT),
      gs = st.gSeen,
      gDone = ['paid', 'lost', 'both', 'cancel'].filter((k) => gs[k]).length;
    const gB = (st.gBook[0] ? 1 : 0) + (st.gBook[1] ? 1 : 0),
      gStep =
        !st.gPlay && st.gT === 0
          ? 'start'
          : gB === 0
            ? 'book'
            : gB === 1 && gs.lost && !gs.both
              ? 'book2'
              : gB === 2
                ? 'cancel'
                : 'none';
    const gCoach = (i) =>
      (gStep === 'book' && i === 0) || (gStep === 'book2' && !st.gBook[i]) || (gStep === 'cancel' && i === 1);
    const gSI = this.gSlowI(st),
      gSlow = st.gPlay && gSI >= 0 && G.st[gSI].vis && !st.gBook[gSI];
    const gTipI = gStep === 'book' ? 0 : gStep === 'book2' ? (st.gBook[0] ? 1 : 0) : gStep === 'cancel' ? 1 : -1;
    const gTip = st.gPlay && gTipI >= 0 && (gStep === 'cancel' || Math.abs(G.st[gTipI].d) < 75);
    let gPass = -1;
    G.st.forEach((x, i) => {
      if (x.vis) gPass = i;
    });
    const sOut = [G.sat[0] - 450, G.sat[1] - 240],
      sLen = Math.hypot(sOut[0], sOut[1]) || 1,
      su = [sOut[0] / sLen, sOut[1] / sLen];
    let memAbs = [G.sat[0] + su[0] * 70, G.sat[1] + su[1] * 70 - 26];
    if (memAbs[1] < 8 || memAbs[1] > 392) memAbs = [G.sat[0] + (G.sat[0] < 450 ? -78 : 78), G.sat[1] - 26];
    memAbs = [Math.max(46, Math.min(700, memAbs[0])), Math.max(8, Math.min(392, memAbs[1]))];
    const memOff = [memAbs[0] - G.sat[0], memAbs[1] - G.sat[1]];
    const gcap = st.gCap;
    let gcx = 450,
      gcy = 240;
    if (gcap) {
      if (gcap.at === 'sat') {
        gcx = G.sat[0];
        gcy = G.sat[1] + (G.sat[1] < 240 ? 96 : -110);
      } else if (gcap.at === 'st') {
        const S = G.st[gcap.i];
        gcx = S.x;
        gcy = S.y + (S.y < 240 ? 54 : -64);
      } else {
        gcx = 960;
        gcy = 100;
      }
    }
    gcx = Math.max(160, Math.min(1000, gcx));
    gcy = Math.max(14, Math.min(410, gcy));
    const gN = [450 + 92 * Math.cos((G.th * Math.PI) / 180), 240 + 92 * Math.sin((G.th * Math.PI) / 180)],
      gu = [(gN[0] - G.sat[0]) / 104, (gN[1] - G.sat[1]) / 104];
    const gBase = st.gN > 24 ? Math.ceil((st.gN - 24) / 8) * 8 : 0,
      gPhM = {};
    st.gPh.forEach((x) => {
      gPhM[x.n] = x.st;
    });
    // ch4 separate apps
    const SAT = [
      ['Radio', 'M12 12v9M8.5 8.5a5 5 0 017 0M5.6 5.6a9 9 0 0112.8 0'],
      ['Camera', 'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 110 7 3.5 3.5 0 010-7z'],
      ['Power', 'M6 7h11v10H6zM17 10h2v4h-2M9 10v4M12 10v4'],
      ['Heaters', 'M10 13.5V5a2 2 0 014 0v8.5a4 4 0 11-4 0z'],
    ];
    const MS = this.misOf(st.mis);
    const saA = ((st.saPhi % 360) + 360) % 360,
      saRad = (saA * Math.PI) / 180,
      saS = [360 + 160 * Math.cos(saRad), 230 + 160 * Math.sin(saRad)],
      saTmp = this.saT(saA);
    const TCOL = ['#6aa8ff', '#7d9fe6', '#8a94c8', '#a99aa8', '#c49f88', '#d4a07a', '#ec8461', '#ff6a4d'],
      saC = TCOL[Math.max(0, Math.min(7, Math.floor(((saTmp + 150) / 270) * 8)))];
    const saDeadI = (i) => st.saBurn && (i === 1 || (st.saMode === 'one' && st.saBurnT >= [9, 0, 6, 3][i]));
    const saRadio = !saDeadI(0),
      saInP = Math.abs(saA - 180) < 22,
      saQ = (saA - 158) / 44,
      saHot = !st.saBurn && st.saPass >= 1 && (saA > 250 || saA < 20) && saTmp > 100;
    const saDone = st.saBeat >= 4 ? 3 : st.saBeat - 1;
    // ch5 layers
    const OSN = { laptop: 'Linux', pi: 'Linux', flight: 'RTEMS' },
      BDC = { laptop: 'any Linux', pi: 'any Linux', flight: 'flight board' },
      BDM = { laptop: 'computer', pi: 'computer', flight: 'flight board' };
    const lyK = st.lyAt,
      lyStep = st.lyA < 4 ? -1 : Math.min(6, Math.floor((st.lyA - 4) / 8)),
      lyRunning = st.lyA >= 0 && st.lyA < 62;
    const LYSTEPS = [
      [3, 'u', 'set up the ' + BDM[lyK]],
      [2, 'u', 'start tasks on ' + OSN[lyK]],
      [1, 'u', 'start the apps'],
      [0, 'u', MS.app + ' running'],
      [0, 'd', 'wake me every 10 s'],
      [1, 'd', 'timer for ' + MS.app],
      [2, 'd', OSN[lyK] + ' timer'],
    ];
    const lyDoneN = (st.lyBeat >= 2 ? 1 : 0) + (st.lyLay ? 1 : 0) + (st.lyDone.flight ? 1 : 0);
    const lyNext = st.lyBeat === 1 ? 'pi' : st.lyBeat === 3 && !lyRunning ? (!st.lyDone.flight ? 'flight' : 'none') : 'none';
    const capAt = (c, x, y) =>
      c && c.n > 0
        ? { cap: true, capT: c.t, capBg: CAPC[c.c][0], capFg: CAPC[c.c][1], capX: x, capY: y }
        : { cap: false, capT: '', capBg: CARD, capFg: TXT, capX: 0, capY: 0 };
    // ch7 frameworks
    const QI = {
      cmd: 'M12 12v9M8.5 8.5a5 5 0 017 0M5.6 5.6a9 9 0 0112.8 0',
      wx: 'M7 18h10a4 4 0 000-8 6 6 0 00-11.6 1.6A3.2 3.2 0 007 18z',
      sch: 'M17 2l4 4-4 4M3 11V9a3 3 0 013-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 01-3 3H3',
      tbl: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4',
      rv: 'M12 8a4 4 0 110 8 4 4 0 010-8zM12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1',
      tlm: 'M12 4v12M6 10l6 6 6-6M5 20h14',
      evt: 'M6 4h12v16H6zM9 8h6M9 12h6M9 16h3',
      ts: 'M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z',
      time: 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 7v5l3 2',
    };
    const QZ = [
      ['cmd', 'Hear commands from Earth', 'all'],
      ['wx', 'Photograph clouds', 0],
      ['sch', 'Do something every 10 seconds', 'all'],
      ['tbl', 'Change the battery rule from Earth', 'all'],
      ['rv', 'Drive the wheels', 1],
      ['tlm', 'Send status and photos down', 'all'],
      ['evt', 'Write down what went wrong', 'all'],
      ['ts', 'Point the mirror at a star', 2],
      ['time', 'Know the exact time', 'all'],
    ];
    const QN = {
      cmd: 'Hear commands',
      tlm: 'Send data down',
      sch: 'Every 10 s',
      time: 'Exact time',
      evt: 'Log problems',
      tbl: 'Change rules',
      wx: 'Cloud photos',
      rv: 'Drive wheels',
      ts: 'Point mirror',
    };
    const FWC = [
      [
        'Weather satellite',
        'M13 7L9 3 5 7l4 4M17 11l4 4-4 4-4-4M8 12l4 4 6-6-4-4zM16 8l3-3M9 21a6 6 0 00-6-6',
        140,
        ['cmd', 'uni', 'tlm', 'time', 'sch', 'tbl', 'evt'],
        'Cloud photos',
      ],
      [
        'Mars rover',
        'M3 16h18M7 16a2 2 0 11-4 0M21 16a2 2 0 11-4 0M14 16a2 2 0 11-4 0M5 12h14l-1 4H6zM9 12V8h6v4M12 8V4',
        470,
        ['tlm', 'cmd', 'uni', 'sch', 'evt', 'time', 'tbl'],
        'Drive wheels',
      ],
      [
        'Space telescope',
        'M4 14l11-6 2.5 4.5-11 6zM15 8l2-1 2.5 4.5-2 1M9 17l-2 4M11 16l2 5',
        800,
        ['sch', 'time', 'cmd', 'tlm', 'uni', 'tbl', 'evt'],
        'Point mirror',
      ],
    ];
    const FWN = QN,
      SHELF = ['cmd', 'tlm', 'sch', 'time', 'evt', 'tbl'];
    const fph = st.fwPhase,
      FMK = ['wx', 'rv', 'ts'];
    const FLW = {
      start: [
        [350, 128],
        [430, 128],
        [610, 128],
        [670, 180],
      ],
      tick: [
        [1000, 224],
        [930, 224],
      ],
      out: [
        [670, 270],
        [610, 318],
        [430, 318],
        [350, 318],
      ],
    };
    const flP = st.flPills.map((x) => Object.assign({}, x, this.along(FLW[x.w], x.p)));
    const flStopOk = st.flStart && st.flGot >= 2 && !st.flStop;
    const FWL = [
      ['cfs', 'cFS', 'NASA Goddard', 'bus', 'LRO · GPM · MMS', 'C'],
      ['fp', 'F Prime', 'NASA JPL', 'ports', 'ASTERIA · Ingenuity', 'C++'],
      ['kub', 'KubOS', 'Kubos', 'svc', '—', 'Rust · Python'],
      ['rod', 'RODOS', 'DLR · Univ. Würzburg', 'bus', 'TET-1 · BIROS', 'C++'],
      ['nmf', 'NanoSat MO', 'ESA · TU Graz', 'svc', 'OPS-SAT', 'Java'],
    ];
    const fsel = FWL.find((x) => x[0] === st.fwSel),
      fseen = Object.keys(st.fwSeen2).length;
    const fwN =
      (st.fwQ >= 9 ? 1 : 0) + (st.fwBeat >= 3 ? 1 : 0) + (st.flDone || st.fwBeat >= 4 ? 1 : 0) + (fseen >= 2 ? 1 : 0);
    const CFB = [
        ['ci', 'CI', 'cmd'],
        ['to', 'TO', 'tlm'],
        ['sch', 'SCH', 'sch'],
        ['time', 'TIME', 'time'],
        ['evs', 'EVS', 'evt'],
        ['tbl', 'TBL', 'tbl'],
      ],
      CFX = [100, 264, 428, 592, 756, 920];
    const CFD = {
      ci: ['CI', QN.cmd, QI.cmd, 'Brings commands from the ground to the right app.'],
      to: ['TO', QN.tlm, QI.tlm, 'Sends status and data from the apps down to the ground.'],
      sch: ['SCH', QN.sch, QI.sch, 'Wakes each app at the right moment.'],
      time: ['TIME', QN.time, QI.time, 'Keeps one clock for the whole spacecraft.'],
      evs: ['EVS', QN.evt, QI.evt, 'Writes down what each app reports, so the ground can read it later.'],
      tbl: ['TBL', QN.tbl, QI.tbl, 'Settings you can change from the ground, without sending new code.'],
      sb: [
        'SB',
        'Carries messages',
        'M3 12h18M7 8v8M12 8v8M17 8v8',
        'Carries every message between the apps. Each app only listens to what it needs.',
      ],
    };
    const CFO = ['ci', 'to', 'sch', 'time', 'evs', 'tbl', 'sb'],
      cfNext = st.cfT >= 64 && !st.cfZ ? CFO.find((k) => !st.cfSeen[k]) || null : null,
      cfAfter = st.cfZ ? CFO.find((k) => !st.cfSeen[k] && k !== st.cfZ) || null : null;
    const cfOpen = (k) => this.setState({ cfZ: k, cfZT: 0, cfSeen: Object.assign({}, st.cfSeen, { [k]: true }) });
    const OSP = st.osT * 7,
      OSJ = Math.floor(OSP / 70);
    const osLane = (lin) => {
      const grid = [],
        marks = [],
        cuts = [];
      for (let j = Math.max(0, OSJ - 11); j <= OSJ; j++) {
        const gx = 770 - (OSP - j * 70);
        if (gx < 4) continue;
        grid.push({ x: gx.toFixed(1) });
        const d = this.osDelay(st, j, lin),
          x = gx + d;
        marks.push({ gx: gx.toFixed(1), x: x.toFixed(1), c: d > 14 ? RED : GREEN, lateO: d > 14 ? 1 : 0 });
        if (st.osJob && j * 70 >= st.osJob0) cuts.push({ x: (x - 5).toFixed(1) });
      }
      const lastJ = OSJ,
        lastD = this.osDelay(st, lastJ, lin),
        age = OSP - lastJ * 70,
        wob = lin && lastD > 14 && age < 50;
      return { grid, marks, cuts, rot: wob ? 10 : 0, beam: wob ? RED : '#5fc9a3' };
    };
    const osLateN = this.osLate(st),
      osMisDone = Object.keys(st.osMis).length >= 3,
      osDoneN = (osLateN >= 6 ? 1 : 0) + (osMisDone ? 1 : 0) + (Object.keys(st.osSeen).length >= 2 ? 1 : 0);
    const STK = (hl) =>
      [
        ['App', MS.app],
        ['cFS', 'apps + cFE'],
        ['OSAL', 'OS layer'],
        ['PSP', 'board layer'],
        ['Board', 'hardware'],
      ].map((x, i) => ({
        t: x[0],
        s: x[1],
        bd: i === hl ? SAND : LINE,
        bg: i === hl ? SANDBG : CARD,
        fg: i === hl ? SANDT : CHIPT,
        sub: i === hl ? SANDT : FAINT,
      }));
    const OSM = [
      [
        'Weather satellite',
        FWC[0][1],
        'photo every 10 s',
        'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 110 7 3.5 3.5 0 010-7z',
        false,
      ],
      ['Mars rover', FWC[1][1], 'steer every 100 ms', 'M12 8a4 4 0 110 8 4 4 0 010-8z', true],
      [
        'Space telescope',
        FWC[2][1],
        'hold the mirror on a star',
        'M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z',
        true,
      ],
    ];
    const BDL = [
      [
        'laptop',
        'Laptop · native',
        '$0 · you have it',
        'x86 · Linux',
        'pc-linux · any Linux PC',
        ['x', 'x', 'v', 'v'],
        true,
      ],
      ['pi', 'Raspberry Pi 4B', 'under $100', 'ARM · Linux', 'pc-linux · same as laptop', ['v', 'x', 'v', 'v'], true],
      ['cube', 'CubeSat computer', '~$5k–8k', 'ARM9 · small RTOS', 'needs its own', ['v', '~', '~', 'x'], false],
      ['rad', 'Rad-hard computer', '~$200k', 'PowerPC · VxWorks', 'needs its own', ['v', 'v', 'x', 'x'], false],
      ['emu', 'Emulator · QEMU', '$0', 'virtual ARM · Linux', 'pc-linux · same as Pi', ['~', 'x', 'v', 'v'], true],
    ];
    const bdB = BDL.find((x) => x[0] === st.bdSel) || BDL[0],
      bdNext = BDL.find((x) => !st.bdSeen[x[0]]);
    const STYCAP = {
      bus: 'apps talk through one shared bus',
      ports: 'components are wired to each other',
      svc: 'apps ask services for what they need',
    };
    const tasks = [
      { t: 'Tap each part', n: nFound, of: 6 },
      { t: 'Radiation', n: rdDone, of: 5 },
      { t: 'Power', n: pwDone, of: 3 },
      { t: 'Ground', n: gDone, of: 4 },
      { t: 'Apps', n: saDone, of: 3 },
      { t: 'OS', n: osDoneN, of: 3 },
      null,
      { t: 'Frameworks', n: fwN, of: 4 },
      { t: 'Add each layer', n: lv, of: 4 },
      { t: 'Pick one', n: st.placed ? 1 : 0, of: 1 },
      { t: 'Steps', n: Object.keys(st.stVis).length, of: 9 },
      { t: 'cFS', n: Object.keys(st.cfSeen).length, of: 7 },
      { t: 'Boards', n: Object.keys(st.bdSeen).length, of: 5 },
    ];
    const done = tasks.map((x) => !x || x.n >= x.of);
    const TITLES = [
      'What is a satellite?',
      'Radiation flips bits',
      'Power runs out in the shadow',
      'Talking to the ground',
      'Why separate apps',
      'Why layers',
      'Why layers and separate apps',
      'Why use a framework',
      "The satellite's computer, on your desk",
      'Pick where it runs',
      'Your first steps',
    ];
    const ICONS = [
      'M13 7L9 3 5 7l4 4M17 11l4 4-4 4-4-4M8 12l4 4 6-6-4-4zM16 8l3-3M9 21a6 6 0 00-6-6',
      'M13 2L4 14h7l-1 8 9-12h-7z',
      'M6 7h11v10H6zM17 10h2v4h-2M9 10v4M12 10v4',
      'M12 12v9M8.5 8.5a5 5 0 017 0M5.6 5.6a9 9 0 0112.8 0',
      'M12 3v18M16 7.5c0-1.9-1.8-3-4-3s-4 1.1-4 3 1.8 2.8 4 3.2 4 1.3 4 3.3-1.8 3-4 3-4-1.1-4-3',
      'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
      'M12 3l9 5-9 5-9-5zM3 12.5l9 5 9-5',
      'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
      CHIPI,
      'M5 5h14v10H5zM2 19h20l-2-4H4z',
      'M5 21V4M5 4h11l-2 4 2 4H5',
    ];
    const NAMES = [
      'Satellite',
      'Radiation',
      'Power',
      'Ground',
      'Separate apps',
      'Layers',
      'Layers',
      'Frameworks',
      'cFS lab',
      'Targets',
      'Steps',
    ];
    NAMES.push('cFS');
    TITLES.push("We use NASA's cFS");
    NAMES.push('Boards');
    TITLES.push('Which computer runs it?');
    NAMES[5] = 'OS layer';
    TITLES[5] = 'Which operating system?';
    ICONS.push('M12 2l9 5v10l-9 5-9-5V7zM12 12l9-5M12 12v10M12 12L3 7');
    ICONS.push('M7 7h10v10H7zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4');
    NAMES[8] = 'On your desk';
    ICONS[4] = 'M3 5h7v14H3zM14 5h7v14h-7z';
    ICONS[5] = 'M4 5h16v14H4zM8 10l3 2-3 2M13 15h3';
    const GROUPS = [
      ['Satellite', [0]],
      ['Why space is hard', [1, 2, 3]],
      ['Software', [7, 4, 11, 5, 12]],
      ['Your lab', [8, 9, 10]],
    ];
    const ORDER = [0, 1, 2, 3, 7, 4, 11, 5, 12, 8, 9, 10],
      oi = ORDER.indexOf(ch);
    const RESET = {
      0: /^(found|sel)$/,
      1: /^(rd[A-Z]|pk$|hitT$)/,
      2: /^pw[A-Z]/,
      3: /^g[A-Z]/,
      4: /^sa[A-Z]/,
      5: /^(ly[A-Z]|os[A-Z])/,
      12: /^bd[A-Z]/,
      7: /^(fw[A-Z]|fl[A-Z])/,
      11: /^cf[A-Z]/,
      8: /^(lv|focus)$/,
    };
    const go = (i) => () => {
      const P = { ch: i, pwPlay: false, gPlay: false };
      if (done[ch]) P.fin = Object.assign({}, st.fin, { [ch]: true });
      const re = RESET[i];
      if (re)
        Object.keys(this._init).forEach((k) => {
          if (re.test(k)) P[k] = this._init[k];
        });
      if (i === 10) Object.assign(P, { k: 0, at: 0, auto: false, stVis: { 0: true } });
      this.setState(P);
    };
    const tk = tasks[ch];
    const prog =
      ch === 2
        ? Math.min(1, (st.pwBeat - 1) / 3 + (st.pwBeat === 1 && st.pwPlay ? Math.min(1, (st.pwT - st.pwT0) / 90) / 3 : 0))
        : ch === 3
          ? Math.min(1, gDone / 4 + (st.gPlay ? 0.04 : 0))
          : ch === 10
            ? st.k / 8
            : tk
              ? Math.min(1, tk.n / tk.of)
              : 0;
    // part 1: build the flight computer
    const F = (id) => () => this.setState({ focus: focus === id ? null : id });
    const CAPS = {
      ci: 'commands in',
      to: 'telemetry out',
      sch: 'wakes apps on time',
      sample: 'example to copy',
      cfe: 'bus · events · time',
      osal: 'any operating system',
      psp: 'any board',
    };
    const TIPS = {
      ci: 'Command Ingest',
      to: 'Telemetry Output',
      sch: 'Scheduler',
      sample: 'Sample app',
      cfe: 'core Flight Executive',
      osal: 'OS Abstraction Layer',
      psp: 'Platform Support Package',
    };
    const chip = (id, t, bg, fg) => ({
      t,
      tip: TIPS[id],
      pick: F(id),
      cur: 'pointer',
      bg: focus === id ? SANDBG : bg,
      fg: focus === id ? SANDT : fg,
      bd: focus === id ? SAND : 'transparent',
    });
    const inRow = (ids) => ids.indexOf(focus) >= 0;
    const READY = { tag: 'ready', tagBg: GREENBG, tagFg: GREENT };
    const R = [
      Object.assign(
        {
          need: 4,
          name: 'Your app',
          cap: 'your mission',
          bd: SAND,
          bg: 'rgba(212,180,138,0.06)',
          chips: [
            { t: 'test_app', tip: 'your code', pick: () => {}, cur: 'default', bg: SANDBG, fg: SANDT, bd: 'transparent' },
          ],
        },
        { tag: 'you build', tagBg: SAND, tagFg: INK },
      ),
      Object.assign(
        {
          need: 3,
          name: 'NASA apps',
          cap: inRow(['ci', 'to', 'sch', 'sample']) ? CAPS[focus] : 'talk to the ground',
          bd: LINE,
          bg: CARD,
          chips: [
            chip('ci', 'ci_lab', BLUEBG, BLUET),
            chip('to', 'to_lab', BLUEBG, BLUET),
            chip('sch', 'sch_lab', BLUEBG, BLUET),
            chip('sample', 'sample_app', BLUEBG, BLUET),
          ],
        },
        READY,
      ),
      Object.assign(
        {
          need: 2,
          name: 'cFS core',
          cap: inRow(['cfe', 'osal', 'psp']) ? CAPS[focus] : 'the framework',
          bd: LINE,
          bg: CARD,
          chips: [chip('cfe', 'cFE', PINKBG, PINKT), chip('osal', 'OSAL', CHIP, CHIPT), chip('psp', 'PSP', CHIP, CHIPT)],
        },
        READY,
      ),
      Object.assign({ need: 1, name: 'Linux', cap: 'runs programs', bd: LINE, bg: CARD, chips: [] }, READY),
      {
        need: 0,
        name: 'Raspberry Pi 4B',
        cap: 'the hardware',
        bd: '#2f6e58',
        bg: '#15271f',
        chips: [],
        tag: '',
        tagBg: LINE,
        tagFg: MUTED,
      },
    ];
    const install = () => this.setState({ lv: Math.min(4, lv + 1), focus: null });
    const nextNeed = lv + 1;
    const rows = R.map((r) =>
      Object.assign({}, r, {
        coach: lv + 1 === r.need ? 'fs-coach' : '',
        done: lv >= r.need,
        next: lv + 1 === r.need,
        locked: lv + 1 < r.need,
        pick: install,
        hasTag: !!r.tag,
        capFg:
          (inRow(['ci', 'to', 'sch', 'sample']) && r.need === 3) || (inRow(['cfe', 'osal', 'psp']) && r.need === 2)
            ? SANDT
            : MUTED,
      }),
    );
    const link = lv >= 3,
      mission = lv >= 4;
    const showTlm = link && focus !== 'ci' && focus !== 'sch';
    const showCmd = link && ['to', 'sample', 'sch'].indexOf(focus) < 0;
    const showData = mission && focus !== 'ci' && focus !== 'sch';
    const bars = [],
      pts = [];
    for (let i = 0; i < 16; i++) {
      const n = st.t - (15 - i);
      bars.push(n < 0 ? 2 : 5 + ((n * 7) % 13));
    }
    for (let i = 0; i < 29; i++) {
      const n = st.t - (28 - i);
      pts.push(i * 5 + ',' + (15 - 10 * Math.sin(n / 6)).toFixed(1));
    }
    const LIGHTS = [
      ['Runs programs', 'M4 5h16v14H4zM7 10l3 2-3 2M12 15h5'],
      ['Software bus', 'M3 12h18M6 12V7M12 12V7M18 12V7M9 12v5M15 12v5'],
      ['Ground link', 'M12 12v9M8.5 8.5a5 5 0 017 0M5.6 5.6a9 9 0 0112.8 0'],
      ['Your mission', 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 8a4 4 0 110 8 4 4 0 010-8z'],
    ];

    // part 2: where it runs
    const P = st.place;
    const places = [
      ['native', 'Native', 'your computer'],
      ['emu', 'Emulator', 'virtual Raspberry Pi'],
      ['board', 'Board', 'real Raspberry Pi'],
    ].map((x) => {
      const sel = P === x[0];
      return {
        name: x[1],
        sub: x[2],
        isNative: x[0] === 'native',
        isEmu: x[0] === 'emu',
        isBoard: x[0] === 'board',
        rec: x[0] === 'emu',
        pick: () => this.setPlace(x[0]),
        coach: !st.placed && x[0] === 'emu' ? 'fs-coach' : '',
        src: x[0] === 'native' ? 'from nasa/cFS' : 'added by Flight Studio',
        srcBg: x[0] === 'native' ? BLUEBG : SANDBG,
        srcFg: x[0] === 'native' ? BLUET : SANDT,
        bd: sel ? SAND : LINE,
        bw: sel ? '1.5px' : '1px',
        dot: sel ? SAND : 'transparent',
        sh: sel ? '0 18px 44px -24px rgba(212,180,138,0.5)' : 'none',
      };
    });
    const pi = P === 'board' ? 0 : P === 'emu' ? 1 : 2;
    const seg = (n) => [0, 1, 2].map((i) => (i < n ? GREEN : LINE));

    // part 3: first steps
    const GC = [
      { c: SAND, bg: SANDBG, tint: 'rgba(212,180,138,0.08)' },
      { c: GREEN, bg: GREENBG, tint: 'rgba(95,201,163,0.08)' },
      { c: BLUE, bg: BLUEBG, tint: 'rgba(124,180,240,0.08)' },
    ];
    const STEPS = [
      ['Target', 'where it runs', 'M12 3a9 9 0 110 18 9 9 0 010-18zM12 8a4 4 0 110 8 4 4 0 010-8z', 0],
      ['Boot', 'start cFS', 'M12 3.5V11M6.6 7a7.6 7.6 0 1010.8 0', 0],
      ['Event', 'say hello', 'M4 12l16-8-6 16-2-7z', 1],
      ['App', 'your program', 'M4 7l8-4 8 4v10l-8 4-8-4zM12 11v10M4 7l8 4 8-4', 1],
      ['Command', 'teach it', 'M8 7l-5 5 5 5M16 7l5 5-5 5', 1],
      ['Send', 'talk to it', 'M12 13a1 1 0 100-2 1 1 0 000 2zM8.5 8.5a5 5 0 000 7M15.5 8.5a5 5 0 010 7', 1],
      ['Sensor', 'test data', 'M2 12c2.5-6 5-6 7.5 0s5 6 7.5 0 3.5-4 5-2', 2],
      ['Test', 'check it', 'M5 12l5 5L20 7', 2],
      ['Board', 'real Pi', 'M6 6h12v12H6zM9.5 9.5h5v5h-5zM9 2.5V6M15 2.5V6M9 18v3.5M15 18v3.5', 2],
    ];
    const k = st.k,
      g = GC[STEPS[k][3]],
      stNext = st.auto ? -1 : STEPS.findIndex((x, i) => !st.stVis[i]);
    const HL = [['base'], ['base', 'core', 'nasa'], ['nasa'], ['app'], ['app'], ['app'], ['app'], ['app'], ['base']][k];
    const baseName =
      k === 8 ? 'Raspberry Pi 4B' : P === 'native' ? 'Your computer' : P === 'board' ? 'Raspberry Pi 4B' : 'Virtual Pi 4B';
    const dchip = (t, bg, fg, hl, cls) => ({
      t,
      bg: hl ? SANDBG : bg,
      fg: hl ? SANDT : fg,
      bd: hl ? SAND : 'transparent',
      cls: cls || '',
    });
    const DR = [
      {
        id: 'app',
        name: 'Your app',
        ghost: k < 3,
        chips:
          k < 3
            ? []
            : [dchip('test_app', SANDBG, SANDT, false, k === 3 ? 'fs-pop' : '')].concat(
                k >= 4 ? [dchip('+ SET_RATE', GREENBG, GREENT, false, k === 4 ? 'fs-pop' : '')] : [],
              ),
      },
      {
        id: 'nasa',
        name: 'NASA apps',
        chips: [
          dchip('ci_lab', BLUEBG, BLUET),
          dchip('to_lab', BLUEBG, BLUET),
          dchip('sch_lab', BLUEBG, BLUET),
          dchip('sample_app', BLUEBG, BLUET, k === 2),
        ],
      },
      {
        id: 'core',
        name: 'cFS core',
        chips: [dchip('cFE', PINKBG, PINKT), dchip('OSAL', CHIP, CHIPT), dchip('PSP', CHIP, CHIPT)],
      },
      { id: 'base', name: baseName, chips: [] },
    ];
    const DELAY = { base: '0s', core: '0.3s', nasa: '0.6s', app: '0s' };
    const drows = DR.map((r) => {
      const hl = HL.indexOf(r.id) >= 0;
      return {
        name: r.name,
        chips: r.chips,
        bd: hl ? g.c : LINE,
        bg: hl ? g.tint : CARD,
        ls: r.ghost ? 'dashed' : 'solid',
        op: r.ghost ? '0.5' : '1',
        delay: k === 1 ? DELAY[r.id] : '0s',
      };
    });
    const aOn = k === 5 || k === 7,
      nOn = k === 2,
      sOn = k === 6 || k === 7;

    const playObj = (playing, fn, coach) => ({
      play: fn,
      playC: CO(coach),
      playIcon: playing ? 'M7 5h3v14H7zM14 5h3v14h-3z' : 'M8 5l11 7-11 7z',
      playT: playing ? 'Pause' : 'Play',
    });
    return {
      h: this.hdr(),
      c11: ch === 11,
      c12: ch === 12,
      c0: ch === 0,
      c1: ch === 1,
      c2: ch === 2,
      c3: ch === 3,
      c4: ch === 4,
      c5: ch === 5,
      c6: ch === 6,
      c7: ch === 7,
      c8: ch === 8,
      c9: ch === 9,
      c10: ch === 10,
      title: TITLES[ch],
      hasTask: false,
      eyebrow: (() => {
        const gr = GROUPS.find((g) => g[1].indexOf(ch) >= 0);
        return gr[0] + (gr[1].length > 1 ? ' · ' + (gr[1].indexOf(ch) + 1) + ' / ' + gr[1].length : '');
      })(),
      task: tk
        ? {
            t: tk.t,
            n: tk.n + '/' + tk.of,
            icon: done[ch] ? 'M5 12l5 5L20 7' : HANDI,
            ic: done[ch] ? GREEN : SAND,
            fg: done[ch] ? GREENT : SANDT,
            bd: done[ch] ? '#2f6e58' : '#5c4d38',
            bg: done[ch] ? GREENBG : 'rgba(212,180,138,0.06)',
          }
        : { t: '', n: '', icon: '', ic: SAND, fg: SANDT, bd: LINE, bg: CARD },
      groups2: GROUPS.map((gr) => {
        const curG = gr[1].indexOf(ch) >= 0;
        return {
          t: gr[0],
          fg: curG ? SAND : MUTED,
          flex: gr[1].length > 1 ? String(gr[1].length) : '0 0 auto',
          items: gr[1].map((i, j) => {
            const cur = i === ch,
              dn = (done[i] || !!st.fin[i]) && i !== 10,
              prev = gr[1][j - 1],
              pPos = ORDER.indexOf(prev);
            const pct = Math.round(prog * 100);
            return {
              t: NAMES[i],
              icon: dn && !cur ? 'M5 12l5 5L20 7' : ICONS[i],
              notFirst: j > 0,
              fill: j === 0 ? 0 : prev === ch ? pct : pPos < oi ? 100 : 0,
              pick: go(i),
              ring: cur ? 'conic-gradient(#d4b48a ' + pct + '%, #343c47 0)' : dn ? GREEN : LINE2,
              bg: cur ? (pct >= 100 ? SAND : '#2a241c') : dn ? GREENBG : '#13171c',
              ic: cur ? (pct >= 100 ? INK : SAND) : dn ? GREEN : FAINT,
            };
          }),
        };
      }),
      // ch0
      spots: PARTS.map((x) => {
        const fd = !!st.found[x.id];
        return {
          name: x.name,
          x: x.x + 80,
          y: x.y + 20,
          found: fd,
          open: !fd,
          pick: pickPart(x.id),
          cls: nextPart && nextPart.id === x.id ? 'fs-coach' : '',
          bs: fd ? 'solid' : 'dashed',
          bd: fd ? GREEN : SAND,
          bg: fd ? GREEN : 'rgba(19,23,28,0.85)',
        };
      }),
      parts: PARTS.map((x) => {
        const fd = !!st.found[x.id],
          sel = st.sel === x.id;
        return {
          found: fd,
          locked: !fd,
          name: x.name,
          role: x.role,
          icon: x.icon,
          pick: () => this.setState({ sel: x.id }),
          brain: brain && x.id === 'obc',
          bd: sel || (brain && x.id === 'obc') ? SAND : LINE,
          bg: sel ? 'rgba(212,180,138,0.06)' : CARD,
          ibg: sel ? SANDBG : CHIP,
          ic: sel ? SAND : CHIPT,
        };
      }),
      s0v: {
        power: pc('power'),
        radio: pc('radio'),
        adcs: pc('adcs'),
        thermal: pc('thermal'),
        payload: pc('payload'),
        obc: pc('obc'),
        wires: brain ? 0.8 : 0,
      },
      // ch1 radiation
      rd: Object.assign(
        {
          do: () => this.radAct(),
          act: !pk && !st.rdDrain && beat <= 5 && !(beat === 4 && !st.rdShield) && !(beat === 2 && !st.rdFlare),
          actT: actT || '',
          wait: !!pk || st.rdDrain,
          chat: st.rdChat.map((m) => ({
            t: m.t,
            time: m.time || '',
            arrow: CH[m.who][0],
            ac: CH[m.who][1],
            fg: CH[m.who][2],
          })),
          chkA: ckOn && st.rdChkId % 2 === 1,
          chkB: ckOn && st.rdChkId % 2 === 0,
          chkV: ck2 ? ck2.v : 0,
          chkSum: ckDig.join(' + ') + ' = ' + ckSum,
          chkVal: ck2 ? ck2.chk : 0,
          chkRes: ck2 && ck2.ok ? '✓  ' + ckSum + ' = ' + ck2.chk : '✗  ' + ckSum + ' ≠ ' + (ck2 ? ck2.chk : 0),
          chkResBg: ck2 && ck2.ok ? GREENBG : REDBG,
          chkFg: ck2 && ck2.ok ? GREENT : RED,
          chkBd: ck2 && ck2.ok ? '#2f6e58' : '#5a3330',
          flare: () =>
            this.setState({
              rdFlare: true,
              rdCap: { t: 'more radiation reaches the satellite', c: 'r', x: 980, y: 300, n: 30 },
            }),
          flareShow: beat === 2 && !st.rdFlare,
          rayO: st.rdFlare && beat <= 4 ? 0.95 : 0,
          shield: () =>
            this.setState({
              rdShield: true,
              rdReveal: false,
              rdDead: false,
              rdTrue: 16,
              rdCap: { t: 'each message now carries the sum of its digits', c: 'g', x: 980, y: 300, n: 30 },
            }),
          showShield: beat === 4 && !st.rdShield && !st.rdDrain,
          sunO: beat >= 2 && beat <= 4 ? (st.rdFlare ? 1 : 0.5) : 0,
          shO: st.rdShield ? 1 : 0,
          shCls: st.rdShield ? 'fs-dash' : '',
          satO: st.rdDead ? 0.3 : 1,
          pathC: st.rdDead ? '#22272e' : '#343c47',
          bat: st.rdTrue,
          batW: Math.max(0, Math.min(100, st.rdTrue)),
          batC: st.rdTrue < 25 ? RED : st.rdTrue < 50 ? SAND : GREEN,
          batBd: st.rdDead ? RED : '#2f6e58',
          link: st.rdDead ? 'no answer' : 'in contact',
          linkBg: st.rdDead ? REDBG : GREENBG,
          linkFg: st.rdDead ? RED : GREENT,
          flashCls: st.rdFlash > 0 && st.rdFlash % 4 === 0 ? 'fs-ring' : '',
          reveal: st.rdReveal,
        },
        capv(st.rdCap, st.rdCap ? st.rdCap.x : 0, st.rdCap ? st.rdCap.y : 0),
      ),
      pk: {
        x: Math.round(bz(P0[0], P1[0], P2[0], pp)),
        y: Math.round(bz(P0[1], P1[1], P2[1], pp)),
        o: pk && pk.p >= 0 ? 1 : 0,
        t: pk ? (pk.kind === 'ans' ? 'Battery ' + pkNum + '%' : pk.t) : '',
        cls: pk && pk.flipped ? 'fs-pop' : '',
        bd: pk && pk.flipped ? RED : pk && pk.dir === 'down' ? BLUE : SAND,
        fg: pk && pk.flipped ? RED : pk && pk.dir === 'down' ? BLUET : SANDT,
        hasBits: !!pk && pk.kind === 'ans',
        hasChk: !!pk && pk.kind === 'ans' && st.rdShield,
        chk:
          pk && pk.kind === 'ans'
            ? String(pk.num)
                .split('')
                .reduce((x, d) => x + Number(d), 0)
            : 0,
        bits: bin(pkNum)
          .split('')
          .map((c, i) => ({ t: c, c: pk && pk.flipped && i === 1 ? RED : pk && pk.dir === 'down' ? BLUET : SANDT })),
        hitO: st.hitT > 0 ? 0.9 : 0,
      },
      // ch2 power
      pw: Object.assign(
        {
          x: g2.x.toFixed(1),
          y: g2.y.toFixed(1),
          bx: (pwB[0] - g2.x - 11).toFixed(1),
          by: (pwB[1] - g2.y - 40).toFixed(1),
          cx: (g2.x < 560 ? -40 : 20).toFixed(1),
          cy: (g2.y > 230 || g2.y < 120 ? 46 : -72).toFixed(1),
          tx: 1000,
          ty: 414,
          rayO: g2.shadow || st.pwOff ? 0 : 0.6,
          wing: st.pwOff ? '#22272e' : g2.shadow ? '#34506e' : '#f0d58a',
          satO: st.pwOff ? 0.3 : 1,
          bat: st.pwBat.toFixed(0),
          batC: st.pwBat < 20 ? RED : st.pwBat < 40 ? SAND : GREEN,
          batBd: st.pwBat < 20 ? RED : '#4b525c',
          lineO: st.pwSafeOn ? 1 : 0,
          safeBadge: st.pwMode === 'safe' && !st.pwOff,
          sby: g2.y < 120 ? 34 : -58,
          camShow: st.pwCam,
          flashCls: pwCamOn && st.pwT % 6 === 0 ? 'fs-pop' : '',
          photos: st.pwPhotos,
          camBg: pwCamOn ? SANDBG : CHIP,
          camBd: pwCamOn ? SAND : LINE2,
          camIc: pwCamOn ? SANDT : FAINT,
          camIcon: pwCamOn
            ? 'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 110 7 3.5 3.5 0 010-7z'
            : 'M4 8h3l2-3h6l2 3h3v11H4zM3 3l18 18',
          coneO: pwCamOn && st.pwT % 6 < 2 ? 0.35 : 0,
          c1x: pwC[0][0].toFixed(1),
          c1y: pwC[0][1].toFixed(1),
          c2x: pwC[1][0].toFixed(1),
          c2y: pwC[1][1].toFixed(1),
          segs: [0, 1, 2, 3].map((i) =>
            st.pwBat > i * 25 + 5 ? (st.pwBat < 20 ? RED : st.pwBat < 40 ? SAND : GREEN) : '#22272e',
          ),
          boltO: !g2.shadow && !st.pwOff && st.pwPlay ? 1 : 0,
          showStart: st.pwBeat === 1 && !st.pwPlay,
          showCam: st.pwBeat === 2 && !st.pwCam,
          showSafe: st.pwBeat === 3 && !st.pwSafeOn,
          start: () => this.setState({ pwPlay: true, pwT0: st.pwT }),
          cam: () => this.setState({ pwCam: true, pwBat: Math.min(st.pwBat, 35), pwCap: { t: 'camera on', c: 's', n: 14 } }),
          safe: () => this.setState({ pwSafeOn: true, pwCap: { t: 'rule: below 30%, stop the camera', c: 'g', n: 22 } }),
        },
        capv(st.pwCap, pcx, pcy),
      ),
      // ch3 ground
      gd: Object.assign(
        {
          sx: G.sat[0].toFixed(1),
          sy: G.sat[1].toFixed(1),
          rot: (0.25 * st.gT).toFixed(1),
          mx: memOff[0].toFixed(1),
          my: memOff[1].toFixed(1),
          mem: Array.from({ length: 6 }, (_, i) => {
            const m = st.gPh.filter((x) => x.st === 'mem').length;
            return {
              bg: i < m ? SAND : 'rgba(0,0,0,0)',
              bd: i < m ? SAND : m >= 6 ? '#5a3330' : LINE2,
              cls: i === m - 1 && st.gSnap > 0 ? 'fs-pop' : '',
            };
          }),
          memBd: st.gPh.filter((x) => x.st === 'mem').length >= 6 ? RED : LINE2,
          drop: st.gDrop > 0,
          bodyC: st.gSnap > 0 ? '#f3dcb8' : '#c9cfd6',
          snapO: st.gSnap > 0 ? 0.45 : 0,
          snapR: (6 + (4 - st.gSnap) * 3).toFixed(0),
          nx: gN[0].toFixed(1),
          ny: gN[1].toFixed(1),
          c1x: (gN[0] - gu[1] * 12).toFixed(1),
          c1y: (gN[1] + gu[0] * 12).toFixed(1),
          c2x: (gN[0] + gu[1] * 12).toFixed(1),
          c2y: (gN[1] - gu[0] * 12).toFixed(1),
          b0x: G.st[0].x.toFixed(1),
          b0y: G.st[0].y.toFixed(1),
          b1x: G.st[1].x.toFixed(1),
          b1y: G.st[1].y.toFixed(1),
          b0o: G.st[0].vis ? (st.gBook[0] ? 0.9 : 0.25) : 0,
          b1o: G.st[1].vis ? (st.gBook[1] ? 0.9 : 0.25) : 0,
          b0c: st.gBook[0] ? GREEN : '#4b525c',
          b1c: st.gBook[1] ? GREEN : '#4b525c',
          fly: st.gFly.map((f) => {
            const S = G.st[f.i];
            return { x: (G.sat[0] + (S.x - G.sat[0]) * f.p).toFixed(1), y: (G.sat[1] + (S.y - G.sat[1]) * f.p).toFixed(1) };
          }),
          st: G.st.map((x, i) => {
            const bk = !!st.gBook[i],
              live = x.vis && bk;
            return {
              x: x.x.toFixed(1),
              y: x.y.toFixed(1),
              pick: () => {
                const B = Object.assign({}, st.gBook);
                B[i] = !B[i];
                const nb = (B[0] ? 1 : 0) + (B[1] ? 1 : 0),
                  sn = Object.assign({}, st.gSeen);
                let cp = null;
                if (nb === 2 && !sn.both) {
                  sn.both = true;
                  cp = { t: 'no more losses, but over budget', c: 'r', n: 40, at: 'cost' };
                }
                if (nb === 1 && sn.both && !sn.cancel) {
                  sn.cancel = true;
                  cp = { t: 'some photos lost, inside the budget', c: 'g', n: 60, at: 'cost' };
                }
                this.setState(Object.assign({ gBook: B, gPlay: true, gSeen: sn }, cp ? { gCap: cp } : {}));
              },
              cls: gCoach(i) && st.gPlay ? 'fs-coach' : '',
              bs: bk ? 'solid' : 'dashed',
              bd: live ? GREEN : bk ? '#2f6e58' : SAND,
              bg: live ? GREENBG : bk ? '#13201b' : 'rgba(19,23,28,0.92)',
              ic: bk ? GREEN : SAND,
              tag: live ? '+$10/min' : bk ? 'booked' : '$10/min',
              tagBg: live ? SANDBG : bk ? GREENBG : CHIP,
              tagFg: live ? SANDT : bk ? GREENT : CHIPT,
            };
          }),
          tip: gTip,
          tipT:
            { book: 'tap to book this station', book2: 'book a second station', cancel: 'over budget · tap one to cancel' }[
              gStep
            ] || '',
          tipX: gTipI >= 0 ? G.st[gTipI].x.toFixed(1) : 0,
          tipY: gTipI >= 0 ? (G.st[gTipI].y + 52).toFixed(1) : 0,
          slow: gSlow,
          showStart: !st.gPlay && st.gT === 0,
          start: () => this.setState({ gPlay: true }),
          clock: this.clock(540 + Math.floor(st.gT)),
          cost: '$' + 160 * gB,
          costW: Math.min(100, (160 * gB) / 4),
          costC: 160 * gB > 200 ? RED : gB ? SAND : FAINT,
          stc: [0, 1]
            .filter((i) => st.gBook[i])
            .map((i) => ({ t: (i === 0 ? 'station A' : 'station B') + ' · $160', bg: CHIP, fg: CHIPT })),
          gal: Array.from({ length: 24 }, (_, i) => {
            const nn = gBase + i + 1,
              x = gPhM[nn],
              last = nn === st.gN;
            return {
              t: x === 'lost' ? '×' : nn <= st.gN ? String(nn) : '',
              bg: x === 'down' ? SAND : x === 'lost' ? REDBG : 'rgba(0,0,0,0)',
              bs: x === 'down' || x === 'lost' ? 'solid' : 'dashed',
              bd: x === 'down' ? SAND : x === 'lost' ? RED : x ? '#8a7152' : LINE,
              fg: x === 'down' ? '#1b150c' : x === 'lost' ? RED : x ? SANDT : FAINT,
              cls: (x === 'down' || x === 'lost') && last ? 'fs-pop' : '',
            };
          }),
          down: st.gPh.filter((x) => x.st === 'down').length,
          lost: st.gPh.filter((x) => x.st === 'lost').length,
          onb: st.gPh.filter((x) => x.st === 'mem' || x.st === 'fly').length,
          lostFg: st.gPh.some((x) => x.st === 'lost') ? RED : CHIPT,
        },
        capv(gcap, gcx, gcy),
      ),
      // ch11 cFS
      cf: Object.assign(
        {
          busO: st.cfT >= 4 ? 1 : 0,
          app: MS.app,
          appIcon: MS.icon,
          zoom: !!st.cfZ,
          tabs: FWC.map((c, ci) => {
            const on = (st.mis || 'wx') === FMK[ci];
            return {
              name: c[0],
              icon: c[1],
              bd: on ? SAND : LINE,
              bg: on ? SANDBG : CARD,
              ic: on ? SANDT : CHIPT,
              pick: () => this.setState({ mis: FMK[ci] }),
            };
          }),
          boxes: CFB.map((b, i) => ({
            t: b[1],
            x: CFX[i],
            o: st.cfT >= 22 + i * 7 ? 1 : 0.3,
            seen: !!st.cfSeen[b[0]],
            bd: st.cfSeen[b[0]] ? GREEN : '#2f6e58',
            cls: cfNext === b[0] ? 'fs-coach' : '',
            open: () => cfOpen(b[0]),
          })),
          sbOpen: () => cfOpen('sb'),
          sbCls: cfNext === 'sb' ? 'fs-coach' : '',
          sbSeen: !!st.cfSeen.sb,
          chips: CFB.map((b, i) => [b[2], CFX[i] + 11, 340, 'g'])
            .concat([[st.mis || 'wx', 474, 146, 's']])
            .map((x, i) => {
              const u0 = (st.cfT - 10 - i * 7) / 12,
                u = u0 <= 0 ? 0 : u0 >= 1 ? 1 : u0 * u0 * (3 - 2 * u0),
                x0 = 30,
                y0 = 112 + i * 32;
              return {
                t: QN[x[0]],
                icon: QI[x[0]],
                x: (x0 + (x[1] - x0) * u).toFixed(1),
                y: (y0 + (x[2] - y0) * u).toFixed(1),
                o: 1,
                bd: x[3] === 'g' ? '#2f6e58' : '#8a7152',
                bg: x[3] === 'g' ? '#162a22' : '#2a241c',
                fg: x[3] === 'g' ? GREENT : SANDT,
              };
            }),
          close: () => this.setState({ cfZ: null }),
        },
        capAt(st.cfCap, 460, 200),
      ),
      cz: Object.assign(
        {
          app: MS.app,
          outT: MS.out(3),
          icon: MS.icon,
          clock: (() => {
            const v = 14 * 3600 + 3 * 60 + 7 + Math.floor(st.cfZT / 10);
            return [Math.floor(v / 3600), Math.floor(v / 60) % 60, v % 60].map((x) => String(x).padStart(2, '0')).join(':');
          })(),
          log: [
            ['14:03:00', MS.app, 'started', GREENT],
            ['14:03:10', MS.app, MS.out(1), TXT],
            ['14:04:20', 'Heaters app', 'heater on', TXT],
            ['14:05:42', MS.app, MS.dev.toLowerCase() + ' too hot', SANDT],
          ]
            .slice(0, 1 + Math.floor((st.cfZT % 80) / 16))
            .map((x) => ({ time: x[0], app: x[1], t: x[2], fg: x[3] })),
          tbl: Math.floor(st.cfZT / 36) % 2 ? 40 : 30,
          tblT: '40%',
          nextCls: st.cfZT > 20 ? 'wc-btn fs-coach' : 'wc-btn',
          closeCls: !cfAfter && st.cfZT > 20 ? 'fs-coach' : '',
          hasNext: !!cfAfter,
          nextT: cfAfter ? (CFD[cfAfter] || ['', ''])[0] : '',
          next: () => cfAfter && cfOpen(cfAfter),
        },
        ...['ci', 'to', 'sch', 'time', 'evs', 'tbl', 'sb'].map((k) => ({ [k]: st.cfZ === k })),
        st.cfZ
          ? { name: CFD[st.cfZ][0], plain: CFD[st.cfZ][1], pIcon: CFD[st.cfZ][2], desc: CFD[st.cfZ][3] }
          : { name: '', plain: '', pIcon: '', desc: '' },
      ),
      // ch7 frameworks
      fw2: Object.assign(
        {
          viewQ: fph === 'quiz',
          viewA: st.fwBeat <= 2 && fph !== 'quiz',
          viewF: st.fwBeat === 3,
          viewB: st.fwBeat >= 4,
          dots: QZ.map((q, i) => ({ c: i < st.fwQ ? GREEN : i === st.fwQ ? SAND : '#2b313a' })),
          qA: st.fwQ < 9 && st.fwQ % 2 === 0,
          qB: st.fwQ < 9 && st.fwQ % 2 === 1,
          qDone: st.fwQ >= 9,
          qT: st.fwQ < 9 ? QZ[st.fwQ][1] : '',
          qIcon: st.fwQ < 9 ? QI[QZ[st.fwQ][0]] : '',
          qCls: st.fwWrong === 1 ? 'w-shake' : st.fwWrong === 2 ? 'w-shake2' : '',
          hint: !!st.fwHint && st.fwQ < 9,
          hintT: st.fwHint,
          allCoach: st.fwQ < 9 && (st.fwWrong ? QZ[st.fwQ][2] === 'all' : st.fwQ % 2 === 0) ? 'fs-coach' : '',
          oneCoach: st.fwQ < 9 && (st.fwWrong ? QZ[st.fwQ][2] !== 'all' : st.fwQ % 2 !== 0) ? 'fs-coach' : '',
          pickAll: () => {
            if (st.fwQ >= 9) return;
            const q = QZ[st.fwQ];
            if (q[2] === 'all')
              this.setState({
                fwAns: Object.assign({}, st.fwAns, { [q[0]]: 'all' }),
                fwQ: st.fwQ + 1,
                fwWrong: 0,
                fwHint: '',
              });
            else
              this.setState({
                fwWrong: st.fwWrong === 1 ? 2 : 1,
                fwHint: ['only the weather satellite does this', 'only the rover does this', 'only the telescope does this'][
                  q[2]
                ],
              });
          },
          pickOne: () => {
            if (st.fwQ >= 9) return;
            const q = QZ[st.fwQ];
            if (q[2] !== 'all')
              this.setState({
                fwAns: Object.assign({}, st.fwAns, { [q[0]]: 'one' }),
                fwQ: st.fwQ + 1,
                fwWrong: 0,
                fwHint: '',
              });
            else this.setState({ fwWrong: st.fwWrong === 1 ? 2 : 1, fwHint: 'the rover and the telescope need it too' });
          },
          mIcons: FWC.map((c) => ({ icon: c[1] })),
          allC: QZ.filter((q) => st.fwAns[q[0]] === 'all').map((q) => ({ t: QN[q[0]], icon: QI[q[0]] })),
          oneC: FWC.map((c, ci) => {
            const q = QZ.find((x) => x[2] === ci);
            return { name: c[0], icon: c[1], has: !!st.fwAns[q[0]], cT: QN[q[0]], cIcon: QI[q[0]] };
          }),
          cols: FWC.map((c) => ({ name: c[0], icon: c[1], x: c[2], o: 1 })),
          blocks: [].concat(
            ...FWC.map((c, ci) =>
              c[3].map((ty, k) => {
                const uni = ty === 'uni',
                  sh = fph === 'shelf',
                  si = SHELF.indexOf(ty),
                  lit = fph !== 'mixed';
                return {
                  t: uni ? (sh ? this.misOf(FMK[ci]).app : c[4]) : FWN[ty],
                  x: sh && !uni ? 130 + si * 156 : c[2],
                  y: sh ? (uni ? 84 : 392) : 84 + k * 40,
                  w: sh && !uni ? 140 : 240,
                  o: sh && !uni && ci > 0 ? 0 : 1,
                  z: sh && !uni && ci > 0 ? 1 : 2,
                  bg: !lit ? CARD : uni ? SANDBG : GREENBG,
                  bd: !lit ? LINE2 : uni ? SAND : '#2f6e58',
                  fg: !lit ? CHIPT : uni ? SANDT : GREENT,
                };
              }),
            ),
          ),
          uniq: FWC.map((c, ci) => ({ x: c[2], t: this.misOf(FMK[ci]).job, o: fph === 'shelf' ? 1 : 0 })),
          shelfO: fph === 'shelf' ? 1 : 0,
          shelfLblO: fph === 'shelf' ? 1 : 0,
          shelfBd: GREEN,
          picks:
            st.fwBeat === 2 && fph === 'shelf'
              ? FWC.map((c, ci) => ({
                  name: c[0],
                  x: c[2] - 10,
                  cls: st.fwT >= 30 && ci === 0 ? 'fs-coach' : '',
                  pick: () => this.setState({ mis: FMK[ci], fwBeat: 3, fwCap: null }),
                }))
              : [],
          find: () =>
            this.setState({
              fwPhase: 'lit',
              fwT: 0,
              fwCap: { t: 'the same pieces show up in every mission', c: 's', n: 26 },
            }),
          findShow: st.fwBeat === 1 && fph === 'mixed',
          cards: FWL.map((x) => ({
            t: x[1],
            by: x[2],
            here: x[0] === 'cfs',
            bd: st.fwSel === x[0] ? SAND : LINE,
            bg: st.fwSel === x[0] ? 'rgba(212,180,138,0.06)' : CARD,
            cls: CO((!st.fwSeen2.cfs && x[0] === 'cfs') || (st.fwSeen2.cfs && fseen < 2 && x[0] === 'fp')),
            pick: () => {
              const sn = Object.assign({}, st.fwSeen2, { [x[0]]: true });
              this.setState({
                fwSel: x[0],
                fwSeen2: sn,
                fwBeat: Object.keys(sn).length >= 2 ? 5 : 4,
                fwCap: { t: STYCAP[x[3]], c: 'g', n: 40 },
              });
            },
          })),
          sBus: !!fsel && fsel[3] === 'bus',
          sPorts: !!fsel && fsel[3] === 'ports',
          sSvc: !!fsel && fsel[3] === 'svc',
          sNone: !fsel,
          appT: MS.app,
          outT: MS.out(1),
          devT: MS.dev,
          verbT: MS.verb,
        },
        capAt(st.fwCap, 590, st.fwBeat >= 4 ? 100 : st.fwBeat === 3 ? 410 : st.fwPhase === 'shelf' ? 230 : 8),
      ),
      fl: {
        clock: this.mclock(st.flSec),
        app: MS.app,
        job: MS.job,
        icon: MS.icon,
        log: st.flLog.map((m) => ({
          t: m.t,
          time: m.time,
          arrow: { g: '✓', s: '↓', u: '↑' }[m.who],
          ac: { g: GREEN, s: BLUE, u: SAND }[m.who],
          fg: { g: GREENT, s: BLUET, u: SANDT }[m.who],
        })),
        start: () => {
          if (st.flStart) return;
          this.setState({
            flStart: true,
            flLog: st.flLog.concat([{ who: 'u', t: 'START', time: this.mclock(st.flSec) }]),
            flPills: st.flPills.concat([{ k: 'start', w: 'start', p: 0, v: 0.09, t: 'START' }]),
          });
        },
        stop: () => {
          if (!flStopOk) return;
          this.setState({
            flStop: true,
            flLog: st.flLog.concat([{ who: 'u', t: 'STOP', time: this.mclock(st.flSec) }]).slice(-8),
            flPills: st.flPills.concat([{ k: 'stop', w: 'start', p: 0, v: 0.09, t: 'STOP' }]),
          });
        },
        startCls: !st.flStart ? 'fs-coach' : '',
        startBd: !st.flStart ? '#8a7152' : LINE,
        startFg: !st.flStart ? SANDT : FAINT,
        stopCls: flStopOk ? 'fs-coach' : '',
        stopBd: flStopOk ? '#8a7152' : LINE,
        stopFg: flStopOk ? SANDT : FAINT,
        cmdBd: flP.some((x) => x.w === 'start' && x.seg === 1) ? TXT : '#2f6e58',
        tlmBd: flP.some((x) => x.w === 'out' && x.seg === 2) ? TXT : '#2f6e58',
        schBd: flP.some((x) => x.w === 'tick' && x.p < 0.5) ? TXT : '#2f6e58',
        stT: st.flOn
          ? 'running'
          : st.flStop && st.flStart && !st.flPills.some((x) => x.k === 'stop')
            ? 'stopped'
            : 'waiting',
        stBg: st.flOn ? GREENBG : CHIP,
        stFg: st.flOn ? GREENT : CHIPT,
        r1: st.flOn ? 'rgba(212,180,138,0.14)' : 'rgba(0,0,0,0)',
        r2: st.flStop && !st.flOn && !st.flPills.some((x) => x.k === 'stop') ? 'rgba(212,180,138,0.14)' : 'rgba(0,0,0,0)',
        snapBg: st.flSnap > 0 ? 'rgba(212,180,138,0.55)' : 'rgba(212,180,138,0.12)',
        pills: flP.map((x) => {
          const c = {
            start: [SAND, '#1b150c'],
            stop: [SAND, '#1b150c'],
            tick: [GREEN, '#0d1115'],
            out: [BLUE, '#0d1115'],
            ack: [GREEN, '#0d1115'],
          }[x.k];
          return { x: x.x.toFixed(1), y: x.y.toFixed(1), t: x.t, bg: c[0], fg: c[1] };
        }),
      },
      // ch4 separate apps
      sa: Object.assign(
        {
          sx: saS[0].toFixed(1),
          sy: saS[1].toFixed(1),
          tx: (Math.cos(saRad) * 50).toFixed(1),
          ty: (Math.sin(saRad) * 50).toFixed(1),
          tT: (saTmp > 0 ? '+' : saTmp < 0 ? '−' : '') + Math.abs(saTmp) + ' °C',
          tC: saC,
          bodyC: !saRadio ? '#4b525c' : '#c9cfd6',
          panelC: !saRadio ? '#3a4250' : '#7cb4f0',
          beacon: saRadio,
          burn: st.saBurn && st.saBurnT < 10,
          smoke: st.saBurn && st.saBurnT < 70,
          stx: 264,
          sty: 230,
          beamO: saInP && saRadio ? 0.9 : 0,
          ping: saInP && !saRadio,
          noAns: saInP && !saRadio,
          stBd: saInP ? (saRadio ? GREEN : RED) : '#8e96a1',
          pill: saInP && saRadio && saQ > 0.1 && saQ < 0.9,
          pillT: st.saBurn ? 'camera stopped · rest OK' : 'all OK',
          px: (saS[0] + (264 - saS[0]) * Math.max(0, Math.min(1, (saQ - 0.1) / 0.8))).toFixed(1),
          py: (saS[1] + (230 - saS[1]) * Math.max(0, Math.min(1, (saQ - 0.1) / 0.8))).toFixed(1),
          tiles: [
            ['Radio', 'M12 12v9M8.5 8.5a5 5 0 017 0M5.6 5.6a9 9 0 0112.8 0'],
            ['Camera', 'M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 110 7 3.5 3.5 0 010-7z'],
            ['Power', 'M6 7h11v10H6zM17 10h2v4h-2M9 10v4M12 10v4'],
            ['Heaters', 'M10 13.5V5a2 2 0 014 0v8.5a4 4 0 11-4 0z'],
          ].map((x, i) => {
            const dead = saDeadI(i),
              hot = i === 1 && saHot;
            return {
              name: x[0],
              icon: x[1],
              x: 796 + (i % 2) * 184,
              y: 62 + Math.floor(i / 2) * 104,
              cls: hot ? 'sa-hot' : i === 1 && st.saBurn && st.saBurnT < 6 ? 'w-shake' : '',
              bd: dead ? '#5a3330' : hot ? '#ec8461' : LINE2,
              bg: dead ? '#1a1416' : CARD,
              ibg: dead ? '#22272e' : hot ? 'rgba(236,132,97,0.2)' : CHIP,
              ic: dead ? (i === 1 ? RED : FAINT) : hot ? '#ec8461' : CHIPT,
              fg: dead ? FAINT : TXT,
              dot: dead ? RED : hot ? '#ec8461' : GREEN,
              dotCls: dead ? '' : 'fs-pulse',
            };
          }),
          log: st.saLog.map((m) => ({
            t: m.t,
            arrow: m.who === 'g' ? '✓' : '×',
            ac: m.who === 'g' ? GREEN : RED,
            fg: m.who === 'g' ? GREENT : RED,
          })),
          split: () =>
            this.setState({
              saMode: 'sep',
              saBeat: 3,
              saRun: true,
              saPhi: 40,
              saBurn: false,
              saBurnT: 0,
              saPass: 0,
              saLog: [],
              saCap: { t: 'each app runs on its own', c: 'g', n: 24 },
            }),
          splitShow: st.saBeat === 2,
          oneO: st.saMode === 'one' ? 1 : 0,
          oneC: !saRadio ? RED : '#4b525c',
          modeT: st.saMode === 'one' ? 'one program' : 'separate apps',
          modeBg: st.saMode === 'one' ? CHIP : GREENBG,
          modeFg: st.saMode === 'one' ? CHIPT : GREENT,
        },
        capAt(st.saCap, 150, 16),
      ),
      // ch5 layers
      os: Object.assign(
        {
          stack: STK(2),
          v1: st.osBeat === 1,
          v2: st.osBeat === 2,
          v3: st.osBeat >= 3,
          job: st.osJob,
          jobX: Math.max(0, 770 - (OSP - st.osJob0)).toFixed(1),
          jobW: (776 - Math.max(0, 770 - (OSP - st.osJob0))).toFixed(1),
          lanes: [true, false].map((lin, i) =>
            Object.assign(
              {
                name: lin ? 'Linux' : 'RTEMS',
                sub: lin ? 'general purpose' : 'real-time',
                y: 24 + i * 176,
                late: lin ? osLateN : 0,
                lateBg: lin && osLateN ? REDBG : GREENBG,
                lateFg: lin && osLateN ? RED : GREENT,
              },
              osLane(lin),
            ),
          ),
          heavy: () => this.setState({ osJob: true, osJob0: OSP + 70 }),
          heavyShow: st.osBeat === 1 && !st.osJob,
          toMis: () => this.setState({ osBeat: 2, osCap: null }),
          toMisShow: st.osBeat === 1 && osLateN >= 6,
          mis: OSM.map((m, i) => {
            const shown = !!st.osMis[i],
              rt = m[4];
            return {
              name: m[0],
              icon: m[1],
              job: m[2],
              jIcon: m[3],
              x: 30 + i * 306,
              shown,
              hidden: !shown,
              os: rt ? 'RTEMS · real-time' : 'Linux is fine',
              osBg: rt ? BLUEBG : GREENBG,
              osFg: rt ? BLUET : GREENT,
              ticks: [0, 1, 2, 3, 4].map((k) => ({
                x: (30 + k * 40 + (!rt && (k === 1 || k === 3) ? 12 : 0)).toFixed(0),
                c: !rt && (k === 1 || k === 3) ? SAND : GREEN,
              })),
              bd: shown ? (rt ? BLUE : GREEN) : LINE,
              cls: !shown && Object.keys(st.osMis).length === i ? 'fs-coach' : '',
              pick: () => this.setState({ osMis: Object.assign({}, st.osMis, { [i]: true }) }),
            };
          }),
          toOsal: () => this.setState({ osBeat: 3, osSeen: { linux: true } }),
          toOsalShow: st.osBeat === 2 && osMisDone,
          layers: [
            [MS.app, SANDBG, SANDT, '#8a7152', true],
            ['cFS', GREENBG, GREENT, '#2f6e58', true],
            ['OSAL · translates to ' + { linux: 'Linux', rtems: 'RTEMS', vx: 'VxWorks' }[st.osOs], CHIP, TXT, LINE2, false],
          ].map((x) => ({ t: x[0], bg: x[1], fg: x[2], bd: x[3], same: x[4] && st.osOs !== 'linux' })),
          osName: { linux: 'Linux', rtems: 'RTEMS', vx: 'VxWorks' }[st.osOs],
          osCls: st.osSw % 2 ? 'os-a' : 'os-b',
          osPick: [
            ['linux', 'Linux', 'laptop · Pi'],
            ['rtems', 'RTEMS', 'flight boards'],
            ['vx', 'VxWorks', 'flight boards'],
          ].map((o) => ({
            t: o[1],
            s: o[2],
            bd: st.osOs === o[0] ? BLUE : LINE,
            bg: st.osOs === o[0] ? BLUEBG : CARD,
            cls: !st.osSeen[o[0]] && Object.keys(st.osSeen).length < 2 && o[0] === 'rtems' ? 'fs-coach' : '',
            pick: () =>
              this.setState({
                osOs: o[0],
                osSw: st.osSw + 1,
                osSeen: Object.assign({}, st.osSeen, { [o[0]]: true }),
                osCap: o[0] === 'linux' ? null : { t: 'only the OS changed, your app stayed the same', c: 'g', n: 50 },
              }),
          })),
        },
        capAt(st.osCap, 560, st.osBeat === 3 ? 400 : 190),
      ),
      bd: Object.assign(
        {
          stack: STK(3),
          cards: BDL.map((x) => ({
            t: x[1],
            price: x[2],
            pc: x[0] === 'rad' ? RED : x[0] === 'cube' ? SANDT : CHIPT,
            seen: !!st.bdSeen[x[0]],
            bd: st.bdSel === x[0] ? SAND : LINE,
            bg: st.bdSel === x[0] ? SANDBG : CARD,
            cls: bdNext && bdNext[0] === x[0] && !(st.bdSel === 'pi' && st.bdTest === 0) ? 'fs-coach' : '',
            pick: () =>
              this.setState({
                bdSel: x[0],
                bdSeen: Object.assign({}, st.bdSeen, { [x[0]]: true }),
                bdTest: 0,
                bdCap:
                  x[0] === 'emu'
                    ? { t: 'a virtual Raspberry Pi on your laptop, for $0', c: 'g', n: 60 }
                    : x[0] === 'rad'
                      ? { t: 'often impossible to get for a student project', c: 'r', n: 50 }
                      : null,
              }),
          })),
          is_laptop: st.bdSel === 'laptop',
          is_pi: st.bdSel === 'pi',
          is_cube: st.bdSel === 'cube',
          is_rad: st.bdSel === 'rad',
          is_emu: st.bdSel === 'emu',
          boardCls: st.bdTest >= 18 && (st.bdSel === 'pi' || st.bdSel === 'laptop') && st.bdTest < 24 ? 'w-shake' : '',
          rays: st.bdTest > 0 && st.bdTest < 20,
          crash: st.bdTest >= 18 && (st.bdSel === 'pi' || st.bdSel === 'laptop'),
          ok: st.bdTest >= 18 && (st.bdSel === 'cube' || st.bdSel === 'rad'),
          testShow: st.bdSel !== 'emu',
          testCls: st.bdTest === 0 && st.bdSel === 'pi' ? 'fs-coach' : '',
          test: () => this.setState({ bdTest: 1, bdCap: null }),
          props: [
            ['Real pins and parts', 'M7 7h10v10H7zM9 3v4M15 3v4M9 17v4M15 17v4'],
            ['Survives radiation', 'M13 2L4 14h7l-1 8 9-12h-7z'],
            ['Easy to get', 'M6 6h15l-2 9H8zM6 6L5 3H2M9 20a1 1 0 100-2 1 1 0 000 2zM18 20a1 1 0 100-2 1 1 0 000 2z'],
            ['Fast to try code', 'M8 5v14l11-7z'],
          ].map((pr, i) => {
            const v = bdB[5][i];
            return {
              t: pr[0],
              icon: pr[1],
              v: v === 'v' ? '✓' : v === 'x' ? '✗' : '~',
              bg: v === 'v' ? GREENBG : v === 'x' ? REDBG : SANDBG,
              fg: v === 'v' ? GREENT : v === 'x' ? RED : SANDT,
            };
          }),
          layers: [MS.app, 'cFS', 'OSAL'].map((t) => ({ t })),
          pspT: bdB[4],
          pspBd: bdB[6] ? BLUE : SAND,
          pspBg: bdB[6] ? BLUEBG : SANDBG,
          pspFg: bdB[6] ? BLUET : SANDT,
          pspCls: st.bdSel && Object.keys(st.bdSeen).length % 2 ? 'os-a' : 'os-b',
          cpu: bdB[3],
          bars: [
            ['Raspberry Pi', 'under $100', 100],
            ['CubeSat computer', '~$8k', 8000],
            ['Rad-hard computer', '~$200k', 200000],
            ['Laptop or emulator', '$0', 0],
          ].map((b, i) => ({
            t: b[0],
            p: b[1],
            w: st.bdT > 3 ? (b[2] / 2000).toFixed(2) : 0,
            c: i === 2 ? RED : i === 1 ? SAND : GREEN,
            fg: CHIPT,
          })),
        },
        capAt(st.bdCap, 580, 324),
      ),
      ly: Object.assign(
        {
          pcs: [
            ['laptop', 'Laptop', 'M5 5h14v10H5zM2 19h20l-2-4H4z'],
            ['pi', 'Raspberry Pi', CHIPI],
            ['flight', 'Flight computer', 'M4 7h16v10H4zM8 7V4M16 7V4M8 17v3M16 17v3M8 11h8'],
          ].map((x, i) => {
            const cur = st.lyAt === x[0];
            return {
              name: x[1],
              icon: x[2],
              os: OSN[x[0]],
              y: 40 + i * 132,
              ok: st.lyLay && !!st.lyDone[x[0]],
              cls: CO(lyNext === x[0]),
              bd: cur ? (st.lyBad ? RED : SAND) : LINE,
              bg: cur ? 'rgba(212,180,138,0.05)' : CARD,
              pick: () => {
                if (!st.lyLay) {
                  if (x[0] === 'laptop') {
                    this.setState({ lyAt: 'laptop', lyBad: false, lyCap: null });
                    return;
                  }
                  this.setState({
                    lyAt: x[0],
                    lyBad: true,
                    lyBeat: Math.max(st.lyBeat, 2),
                    lyCap: { t: 'your code only knew the laptop', c: 'r', n: 40 },
                  });
                  return;
                }
                if (lyRunning && x[0] === st.lyAt) return;
                this.setState({ lyAt: x[0], lyA: 0, lyCap: null });
              },
            };
          }),
          rows: [
            [MS.app, MS.job, MS.icon, 'your code', SANDBG, SANDT],
            [
              'Framework',
              'messages, timers, logs',
              'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
              'shared',
              GREENBG,
              GREENT,
            ],
            ['OS layer', 'talks to the operating system', 'M4 5h16v14H4zM8 10l3 2-3 2M13 15h3', OSN[lyK], BLUEBG, BLUET],
            ['Board layer', 'talks to this exact board', CHIPI, BDC[lyK], BLUEBG, BLUET],
          ].map((x, i) => {
            const y = st.lyLay ? 30 + i * 66 : i === 0 ? 236 : 30 + i * 66,
              o = st.lyLay || i === 0 ? 1 : 0;
            let msg = null;
            for (let j = 0; j <= lyStep; j++) if (LYSTEPS[j][0] === i) msg = LYSTEPS[j];
            const act = lyRunning && lyStep >= 0 && LYSTEPS[lyStep][0] === i,
              bad = !st.lyLay && i === 0 && st.lyBad,
              pre = !st.lyLay && i === 0;
            const kind = bad ? 'r' : pre ? 'n' : msg ? msg[1] : 'n',
              MC = {
                r: [REDBG, RED, '#5a3330'],
                n: [CHIP, CHIPT, LINE2],
                u: [BLUEBG, BLUET, '#2e4d6b'],
                d: [SANDBG, SANDT, '#8a7152'],
              }[kind];
            const same = st.lyLay && i <= 1 && st.lyA >= 62 && lyK !== 'laptop';
            return {
              name: x[0],
              role: x[1],
              icon: x[2],
              chip: same ? 'no change' : x[3],
              chipBg: same ? GREENBG : x[4],
              chipFg: same ? GREENT : x[5],
              y,
              o,
              z: o ? 2 : 1,
              fg: i === 0 ? SANDT : TXT,
              cls: bad ? 'w-shake' : '',
              bd: bad ? RED : act ? TXT : i >= 2 && st.lyA >= 0 && st.lyA < 14 ? SAND : i === 0 ? '#8a7152' : LINE2,
              bg: i === 0 ? 'rgba(212,180,138,0.05)' : CARD,
              same: false,
              msgShow: o === 1 && (pre || !!msg),
              msg: bad ? 'laptop clock not found' : pre ? 'read the laptop clock' : msg ? msg[2] : '',
              arrow: bad ? '×' : pre ? '↓' : msg && msg[1] === 'u' ? '↑' : '↓',
              msgBg: MC[0],
              msgFg: MC[1],
              msgBd: MC[2],
              my: y + 12,
              ly: y + 28,
            };
          }),
          hwIcon: {
            laptop: 'M5 5h14v10H5zM2 19h20l-2-4H4z',
            pi: CHIPI,
            flight: 'M4 7h16v10H4zM8 7V4M16 7V4M8 17v3M16 17v3M8 11h8',
          }[lyK],
          hwName: { laptop: 'Laptop', pi: 'Raspberry Pi 4B', flight: 'Flight computer' }[lyK],
          hwBd: st.lyBad ? RED : st.lyLay && st.lyA >= 62 ? GREEN : LINE2,
          phase: lyRunning && lyStep >= 0,
          phaseT: lyStep >= 4 ? 'every 10 s ↓' : 'start-up ↑',
          phaseC: lyStep >= 4 ? SAND : BLUE,
          add: () => this.setState({ lyLay: true, lyBad: false, lyBeat: 3, lyA: 0, lyCap: null }),
          addShow: st.lyBeat === 2 && !st.lyLay,
        },
        capAt(st.lyCap, 826, 296),
      ),
      // ch3
      pa: Object.assign(pa, {
        mono: st.pmode === 'mono',
        apps: st.pmode === 'apps',
        monoGo: () => this.setState({ pmode: 'mono', crash: null, crashT: 0 }),
        appsGo: () => this.setState({ pmode: 'apps', crash: null, crashT: 0 }),
      }),
      lb: Object.assign(lb, {
        noneGo: () => this.setState({ lmode: 'none', lchg: null }),
        layGo: () => this.setState({ lmode: 'lay', lchg: null }),
      }),
      // ch4
      fwt,
      fwb: {
        blocks: BL.map((t, i) => ({
          t,
          bs: fwOn ? 'solid' : 'dashed',
          bd: fwOn ? '#2f6e58' : '#8a7152',
          bg: fwOn ? GREENBG : 'transparent',
          fg: fwOn ? GREENT : SAND,
          d: (i * 0.05).toFixed(2) + 's',
        })),
        brO: fwOn ? 1 : 0,
        work: fwOn ? 14 : 100,
        flown: fwOn ? 100 : 4,
      },
      fws: FW.map((x) => {
        const sel = st.fw === x.id;
        return {
          t: x.t,
          by: x.by,
          here: !!x.here,
          seen: !!st.fwSeen[x.id] && !x.here,
          pick: () => this.setState({ fw: x.id, fwSeen: Object.assign({}, st.fwSeen, { [x.id]: true }) }),
          coach: st.fwToggled && n4 < 3 && nextFw && nextFw.id === x.id ? 'fs-coach' : '',
          bd: sel ? SAND : LINE,
          bg: sel ? 'rgba(212,180,138,0.06)' : CARD,
        };
      }),
      fwd: {
        none: !fwCur,
        some: !!fwCur,
        t: fwCur ? fwCur.t : '',
        facts: fwCur ? fwCur.facts.map((x) => ({ k: x[0], v: x[1] })) : [],
        cfs: st.fw === 'cfs',
        fp: st.fw === 'fp',
        kub: st.fw === 'kub',
        rod: st.fw === 'rod',
        nmf: st.fw === 'nmf',
      },
      // ch5-7
      sc: {
        cable: link ? '#7d8590' : '#3a424c',
        led: lv >= 1 ? GREEN : '#3a424c',
        ledCls: focus === 'sch' ? 'fs-blink' : lv >= 2 ? 'fs-pulse' : '',
        ringCls: focus === 'sch' ? 'fs-ring' : '',
        wire: mission ? GREEN : '#4b525c',
        dash: mission ? '0' : '4 4',
        sens: mission ? GREEN : '#4b525c',
        tlm: showTlm ? 1 : 0,
        cmd: showCmd ? 1 : 0,
        data: showData ? 1 : 0,
        q: mission ? 0 : 1,
        ok: mission,
      },
      scr: {
        off: !link,
        on: link,
        dot: link ? GREEN : '#3a424c',
        bars,
        pts: pts.join(' '),
        tlmOp: showTlm ? 1 : 0.25,
        cmdOp: showCmd ? 1 : 0.15,
        dataOp: showData ? 1 : 0,
      },
      lights: LIGHTS.map((x, i) => {
        const on = lv > i;
        return {
          t: x[0],
          icon: x[1],
          cls: on ? 'fs-pop' : '',
          bd: on ? GREEN : LINE,
          bg: on ? GREENBG : 'transparent',
          ic: on ? GREEN : FAINT,
          fg: on ? TXT : MUTED,
        };
      }),
      rows,
      canReset: lv > 0,
      reset: () => this.setState({ lv: 0, focus: null, t: 0 }),
      places,
      bNative: P === 'native',
      bEmu: P === 'emu',
      bBoard: P === 'board',
      same: [
        { name: 'Your app', bd: SAND, chips: [{ t: 'test_app', bg: SANDBG, fg: SANDT }] },
        {
          name: 'NASA apps',
          bd: LINE,
          chips: [
            { t: 'ci_lab', bg: BLUEBG, fg: BLUET },
            { t: 'to_lab', bg: BLUEBG, fg: BLUET },
            { t: 'sch_lab', bg: BLUEBG, fg: BLUET },
            { t: 'sample_app', bg: BLUEBG, fg: BLUET },
          ],
        },
        {
          name: 'cFS core',
          bd: LINE,
          chips: [
            { t: 'cFE', bg: PINKBG, fg: PINKT },
            { t: 'OSAL', bg: CHIP, fg: CHIPT },
            { t: 'PSP', bg: CHIP, fg: CHIPT },
          ],
        },
      ],
      meters: [
        { t: 'Quick to try', segs: seg([3, 2, 1][pi === 2 ? 0 : pi === 1 ? 1 : 2]) },
        { t: 'Like the real Pi', segs: seg([1, 2, 3][pi === 2 ? 0 : pi === 1 ? 1 : 2]) },
      ],
      pi: P === 'board' ? { t: 'yes', bg: SANDBG, fg: SANDT } : { t: 'no', bg: CHIP, fg: CHIPT },
      groups: [
        { t: 'set up', c: SAND },
        { t: 'build', c: GREEN },
        { t: 'test', c: BLUE },
      ],
      nodes: STEPS.map((x, i) => {
        const gc = GC[x[3]],
          cur = i === k,
          past = i < k;
        return {
          label: x[0],
          sub: x[1],
          icon: x[2],
          pick: () => this.setState({ k: i, auto: false, at: 0, stVis: Object.assign({}, st.stVis, { [i]: true }) }),
          cls: cur ? 'fs-pop' : i === stNext ? 'fs-coach' : '',
          bd: cur || past ? gc.c : LINE2,
          bg: cur ? gc.c : past ? gc.bg : 'transparent',
          ic: cur ? INK : past ? gc.c : FAINT,
          fg: cur ? TXT : past ? CHIPT : MUTED,
        };
      }),
      lineW: 'calc((100% - 92px) * ' + (k / 8).toFixed(3) + ')',
      playIcon: st.auto ? 'M7 5h3v14H7zM14 5h3v14h-3z' : 'M8 5l11 7-11 7z',
      playAria: st.auto ? 'Pause' : 'Play',
      togglePlay: () => this.setState(st.k >= 8 && !st.auto ? { k: 0, auto: true, at: 0 } : { auto: !st.auto, at: 0 }),
      drows,
      dg: {
        gBd: aOn || nOn || k === 7 ? g.c : LINE,
        ok: k === 7,
        aC: aOn ? g.c : LINE,
        aCls: aOn ? 'fs-dash' : '',
        aOp: aOn ? 1 : 0,
        nC: nOn ? g.c : LINE,
        nCls: nOn ? 'fs-dash' : '',
        nOp: nOn ? 1 : 0,
        sC: sOn ? GREEN : LINE,
        sCls: sOn ? 'fs-dash' : '',
        sOp: sOn ? 1 : 0,
        senBd: k >= 6 && k <= 7 ? GREEN : LINE,
        senIc: k >= 6 ? GREEN : FAINT,
      },
      // nav
      canBack: oi > 0,
      back: go(ORDER[Math.max(0, oi - 1)]),
      next: go(ORDER[Math.min(ORDER.length - 1, oi + 1)]),
      notLast: oi < ORDER.length - 1,
      isLast: ch === 10,
      nextCls: done[ch] ? 'ready fs-coach' : '',
      nextBg: '',
      nextFg: '',
      nextBd: '',
    };
  }
}
