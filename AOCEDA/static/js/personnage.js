/*! Personnage animé de l'assistant AOCEDA.
 *  FICHIER GÉNÉRÉ par etudes/coucou/construire_personnage.js : ne pas le modifier à la main (modifier les sources).
 *  Moteur d'animation : Coucou, github.com/Louis-CFM/coucou (windows/src/mochi/engine.ts, core/anim.ts), sous licence
 *  MIT reproduite ci-dessous. Le personnage « Mochi », son nom, son apparence et ses sons (tous droits réservés) ne sont
 *  pas repris : personnage, chorégraphies, pastilles et scène AOCEDA.
 *
 *  MIT License
 *
 *  Copyright (c) 2026 Louis Raillé
 *
 *  Permission is hereby granted, free of charge, to any person obtaining a copy
 *  of this software and associated documentation files (the "Software"), to deal
 *  in the Software without restriction, including without limitation the rights
 *  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 *  copies of the Software, and to permit persons to whom the Software is
 *  furnished to do so, subject to the following conditions:
 *
 *  The above copyright notice and this permission notice shall be included in all
 *  copies or substantial portions of the Software.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 *  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 *  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 *  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 *  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 *  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 *  SOFTWARE.
 */
(() => {
"use strict";
const Ease = {
    out: (t)=>1 - Math.pow(1 - t, 3),
    inOut: (t)=>t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
    back: (t)=>{
        const c1 = 1.7;
        const c3 = c1 + 1;
        return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
    },
    lin: (t)=>t,
    easeIn: (t)=>t * t * t
};
const lerp = (a, b, t)=>a + (b - a) * t;
const clamp = (v, lo, hi)=>Math.max(lo, Math.min(hi, v));
const seg = (t, a, b)=>clamp((t - a) / (b - a), 0, 1);
function cubicBezier(x1, y1, x2, y2) {
    const cx = (t)=>(1 - t) ** 2 * 3 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3;
    const cy = (t)=>(1 - t) ** 2 * 3 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3;
    return (x)=>{
        let lo = 0;
        let hi = 1;
        let t = x;
        for(let i = 0; i < 12; i++){
            const v = cx(t);
            if (v < x) lo = t;
            else hi = t;
            t = (lo + hi) / 2;
        }
        return cy(t);
    };
}
const closeCurve = cubicBezier(0.45, 0, 0.2, 1);
class Spring {
    value;
    target;
    velocity = 0;
    omega;
    zeta;
    constructor(value, response = 0.5, damping = 0.72){
        this.value = value;
        this.target = value;
        this.omega = 2 * Math.PI / response;
        this.zeta = damping;
    }
    configure(response, damping) {
        this.omega = 2 * Math.PI / response;
        this.zeta = damping;
    }
    set(value) {
        this.value = value;
        this.target = value;
        this.velocity = 0;
    }
    get settled() {
        return Math.abs(this.target - this.value) < 0.01 && Math.abs(this.velocity) < 0.05;
    }
    step(dt) {
        const steps = Math.max(1, Math.ceil(dt / (1 / 240)));
        const h = dt / steps;
        for(let i = 0; i < steps; i++){
            const acc = this.omega * this.omega * (this.target - this.value) - 2 * this.zeta * this.omega * this.velocity;
            this.velocity += acc * h;
            this.value += this.velocity * h;
        }
    }
}
class Tracked {
    spring;
    curveFrom = 0;
    curveTo = 0;
    curveStart = 0;
    curveDur = 0;
    mode = "idle";
    constructor(value){
        this.spring = new Spring(value);
    }
    get value() {
        return this.spring.value;
    }
    get animating() {
        return this.mode !== "idle";
    }
    jump(v) {
        this.spring.set(v);
        this.mode = "idle";
    }
    springTo(v, response = 0.5, damping = 0.72) {
        this.spring.configure(response, damping);
        this.spring.target = v;
        this.mode = "spring";
    }
    curveTowards(v, durationMs = 340, now = performance.now()) {
        this.curveFrom = this.spring.value;
        this.curveTo = v;
        this.curveStart = now;
        this.curveDur = durationMs;
        this.spring.target = v;
        this.spring.velocity = 0;
        this.mode = "curve";
    }
    step(dt, now = performance.now()) {
        if (this.mode === "spring") {
            this.spring.step(dt);
            if (this.spring.settled) {
                this.spring.value = this.spring.target;
                this.spring.velocity = 0;
                this.mode = "idle";
            }
        } else if (this.mode === "curve") {
            const p = clamp((now - this.curveStart) / this.curveDur, 0, 1);
            this.spring.value = lerp(this.curveFrom, this.curveTo, closeCurve(p));
            if (p >= 1) {
                this.spring.velocity = 0;
                this.mode = "idle";
            }
        }
    }
}

const Sound = { play() {} };                       // sons de Mochi : tous droits réservés -> jamais joués


const EYE_W = 0.25;
const EYE_H = 0.27;
const EYE_SP = 0.37;
const EYE_P = -0.12;
let BASE_TOP = [
    0.929,
    0.929,
    0.937
];
let BASE_BOTTOM = [
    0.769,
    0.773,
    0.792
];
let INK = "rgb(26,20,18)";
const MINI_INK = "rgb(16,19,26)";
const C = {
    idle: [
        0.902,
        0.914,
        0.933
    ],
    working: [
        0.231,
        0.62,
        1
    ],
    thinking: [
        0.545,
        0.361,
        0.965
    ],
    searching: [
        0.388,
        0.396,
        0.949
    ],
    approval: [
        0.961,
        0.647,
        0.141
    ],
    question: [
        0.133,
        0.827,
        0.933
    ],
    error: [
        0.957,
        0.314,
        0.369
    ],
    finished: [
        0.204,
        0.831,
        0.6
    ],
    ratelimit: [
        0.984,
        0.573,
        0.235
    ],
    sleeping: [
        0.58,
        0.635,
        0.722
    ],
    dizzy: [
        0.957,
        0.447,
        0.714
    ]
};
const base = {
    bounces: false,
    scans: false,
    breathes: false,
    zz: false,
    sweat: false,
    look: null,
    tilt: 0
};
const BOT_STATES = {
    idle: {
        ...base,
        color: C.idle,
        tint: 0,
        eye: "pill",
        badge: null
    },
    working: {
        ...base,
        color: C.working,
        tint: 0.72,
        eye: "pill",
        badge: {
            kind: "dots",
            color: C.working
        }
    },
    thinking: {
        ...base,
        color: C.thinking,
        tint: 0.72,
        eye: "pill",
        badge: {
            kind: "dots",
            color: C.thinking
        },
        look: [
            0.55,
            0.55
        ]
    },
    searching: {
        ...base,
        color: C.searching,
        tint: 0.72,
        eye: "pill",
        badge: {
            kind: "dots",
            color: C.searching
        },
        scans: true
    },
    approval: {
        ...base,
        color: C.approval,
        tint: 0.78,
        eye: "wide",
        badge: {
            kind: "bang",
            color: C.approval
        },
        bounces: true
    },
    question: {
        ...base,
        color: C.question,
        tint: 0.75,
        eye: "pill",
        badge: {
            kind: "question",
            color: C.question
        },
        tilt: 0.17
    },
    error: {
        ...base,
        color: C.error,
        tint: 0.78,
        eye: "flat",
        badge: {
            kind: "dot",
            color: C.error
        }
    },
    finished: {
        ...base,
        color: C.finished,
        tint: 0.35,
        eye: "happy",
        badge: {
            kind: "dot",
            color: C.finished
        }
    },
    ratelimit: {
        ...base,
        color: C.ratelimit,
        tint: 0.72,
        eye: "tired",
        badge: {
            kind: "dot",
            color: C.ratelimit
        },
        sweat: true
    },
    sleeping: {
        ...base,
        color: C.sleeping,
        tint: 0.32,
        eye: "closed",
        badge: null,
        breathes: true,
        zz: true
    },
    dizzy: {
        ...base,
        color: C.dizzy,
        tint: 0.7,
        eye: "spiral",
        badge: null
    }
};
const STATE_SOUND = {
    working: "work",
    thinking: "think",
    searching: "search",
    approval: "approval",
    question: "question",
    error: "error",
    finished: "finish",
    ratelimit: "rate",
    sleeping: "sleep",
    dizzy: "dizzy"
};
const EMOTE_EYE = {
    love: "heart",
    surprised: "dot",
    proud: "star",
    wink: "wink",
    yawn: "tired",
    happy: "happy",
    annoyed: "line"
};
const now = ()=>performance.now() / 1000;
function hexToRGB(hex) {
    const h = hex.replace("#", "");
    const v = parseInt(h, 16);
    return [
        (v >> 16 & 255) / 255,
        (v >> 8 & 255) / 255,
        (v & 255) / 255
    ];
}
const rgba = (c, a = 1)=>`rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${a})`;
const mix3 = (a, b, t)=>[
        lerp(a[0], b[0], t),
        lerp(a[1], b[1], t),
        lerp(a[2], b[2], t)
    ];
function roundRectPath(x, X, Y, W, H, R) {
    const r = Math.max(0, Math.min(R, W / 2, H / 2));
    x.beginPath();
    x.moveTo(X + r, Y);
    x.arcTo(X + W, Y, X + W, Y + H, r);
    x.arcTo(X + W, Y + H, X, Y + H, r);
    x.arcTo(X, Y + H, X, Y, r);
    x.arcTo(X, Y, X + W, Y, r);
    x.closePath();
}
function heartPath(x, s) {
    x.beginPath();
    x.moveTo(0, s * 0.38);
    x.bezierCurveTo(-s * 1.05, -s * 0.15, -s * 0.5, -s * 0.95, 0, -s * 0.38);
    x.bezierCurveTo(s * 0.5, -s * 0.95, s * 1.05, -s * 0.15, 0, s * 0.38);
    x.closePath();
}
function starPath(x, ro, ri) {
    x.beginPath();
    for(let i = 0; i < 10; i++){
        const r = i % 2 ? ri : ro;
        const a = -Math.PI / 2 + i * Math.PI / 5;
        x.lineTo(Math.cos(a) * r, Math.sin(a) * r);
    }
    x.closePath();
}
const FONT = `system-ui, "Segoe UI Variable Text", "Segoe UI", sans-serif`;
class BotEngine {
    isMini = false;
    bodyColor = null;
    yaw = 0;
    pitch = 0;
    roll = 0;
    tilt = 0;
    open = 1;
    sx = 1;
    sy = 1;
    oy = 0;
    ox = 0;
    tint = 0;
    morph = 0;
    hands = 0;
    blush = 0;
    es = 1;
    badgeS = 0;
    tgYaw = 0;
    tgPitch = 0;
    tgTilt = 0;
    tgSy = 1;
    tgSx = 1;
    tgEs = 1;
    particleOverhang = 0;
    slotH = 0;
    slotHTarget = 0;
    slotHVel = 0;
    isChewing = false;
    col = C.idle;
    colT = C.idle;
    state = "idle";
    cfg = BOT_STATES.idle;
    eyeOverride = null;
    eyeOverrideUntil = 0;
    permanentEye = null;
    permanentEmote = null;
    miniNextBehavior = 0;
    badge = null;
    badgeKey = "none";
    badgeToken = 0;
    tweens = new Map();
    locks = new Set();
    particles = [];
    lookX = 0;
    lookY = 0;
    lastTime = now();
    t0 = now() - Math.random() * 5;
    nextBlink = now() + 1.5 + Math.random() * 2;
    waveUntil = 0;
    waveStart = 0;
    greetToken = 0;
    lastAmbient = 0;
    slapTimes = [];
    miniLookTarget = {
        x: 0,
        y: 0
    };
    miniLookNextTime = 0;
    onDizzy = null;
    setState(next, force = false) {
        if (this.state === next && !force) return;
        const prev = this.state;
        this.state = next;
        this.cfg = BOT_STATES[next];
        this.colT = this.cfg.color;
        if (!this.locks.has("tint")) this.tint = this.cfg.tint;
        if (!this.locks.has("tilt")) this.tgTilt = this.cfg.tilt;
        this.setBadge(this.cfg.badge);
        switch(next){
            case "finished":
                this.doRoll(950, 1);
                setTimeout(()=>this.emit("spark", 5), 500);
                break;
            case "error":
                this.anim("ox", [
                    [
                        0.08,
                        50,
                        Ease.out
                    ],
                    [
                        -0.08,
                        70,
                        Ease.inOut
                    ],
                    [
                        0.05,
                        70,
                        Ease.inOut
                    ],
                    [
                        0,
                        90,
                        Ease.out
                    ]
                ]);
                break;
            case "approval":
                this.anim("oy", [
                    [
                        -0.2,
                        150,
                        Ease.out
                    ],
                    [
                        0,
                        300,
                        Ease.back
                    ]
                ]);
                break;
            case "dizzy":
                this.doRoll(1300, 2);
                break;
            case "question":
                this.blink();
                break;
            case "ratelimit":
                this.emit("sweat", 1);
                break;
            default:
                if (prev !== "idle" || next !== "idle") this.blink();
        }
    }
    setBadge(b) {
        const key = b ? `${b.kind}-${b.color.join(",")}` : "none";
        if (key === this.badgeKey) return;
        this.badgeKey = key;
        const tok = ++this.badgeToken;
        this.anim("badgeS", [
            [
                0,
                90,
                Ease.inOut
            ]
        ]);
        setTimeout(()=>{
            if (tok !== this.badgeToken) return;
            this.badge = b;
            if (b) this.anim("badgeS", [
                [
                    1,
                    280,
                    Ease.back
                ]
            ]);
        }, 100);
    }
    blink() {
        if (this.locks.has("open")) return;
        this.anim("open", [
            [
                0.06,
                70,
                Ease.inOut
            ],
            [
                1,
                130,
                Ease.out
            ]
        ]);
    }
    squash() {
        this.anim("sy", [
            [
                0.78,
                70,
                Ease.out
            ],
            [
                1.1,
                130,
                Ease.out
            ],
            [
                1,
                170,
                Ease.inOut
            ]
        ]);
        this.anim("sx", [
            [
                1.16,
                70,
                Ease.out
            ],
            [
                0.95,
                130,
                Ease.out
            ],
            [
                1,
                170,
                Ease.inOut
            ]
        ]);
    }
    gulp() {
        this.slotHTarget = 0.42;
        setTimeout(()=>{
            this.slotHTarget = 0;
            this.isChewing = true;
            setTimeout(()=>{
                this.isChewing = false;
            }, 800);
        }, 460);
        this.anim("sy", [
            [
                0.78,
                80,
                Ease.out
            ],
            [
                1.18,
                130,
                Ease.out
            ],
            [
                1,
                220,
                Ease.back
            ]
        ]);
        this.anim("sx", [
            [
                1.28,
                80,
                Ease.out
            ],
            [
                0.92,
                130,
                Ease.out
            ],
            [
                1,
                220,
                Ease.back
            ]
        ]);
        this.blink();
    }
    slap() {
        this.interruptGreet();
        if (this.state === "dizzy") return;
        const t = now();
        this.slapTimes = this.slapTimes.filter((s)=>t - s < 1.7);
        this.slapTimes.push(t);
        Sound.play("slap");
        this.squash();
        if (this.slapTimes.length >= 3) {
            this.slapTimes = [];
            this.onDizzy?.();
        } else {
            this.eyeOverride = "line";
            this.eyeOverrideUntil = t + 0.8;
            setTimeout(()=>Sound.play("annoyed"), 60);
        }
    }
    doRoll(durationMs, turns) {
        this.roll = 0;
        this.anim("roll", [
            [
                Math.PI * 2 * turns,
                durationMs,
                Ease.inOut
            ]
        ], ()=>{
            this.roll = 0;
        });
    }
    greet() {
        const t = now();
        const tok = ++this.greetToken;
        this.waveStart = t + 0.45;
        this.waveUntil = t + 1.55;
        this.eyeOverride = "happy";
        this.eyeOverrideUntil = t + 2.0;
        this.anim("oy", [
            [
                -0.06,
                220,
                Ease.out
            ],
            [
                0.0,
                220,
                Ease.back
            ]
        ]);
        setTimeout(()=>{
            if (this.greetToken !== tok) return;
            this.anim("hands", [
                [
                    1,
                    280,
                    Ease.out
                ]
            ]);
            this.anim("sy", [
                [
                    0.95,
                    100,
                    Ease.out
                ],
                [
                    1.0,
                    260,
                    Ease.back
                ]
            ]);
            this.anim("sx", [
                [
                    1.04,
                    100,
                    Ease.out
                ],
                [
                    1.0,
                    260,
                    Ease.back
                ]
            ]);
            Sound.play("greet");
        }, 250);
        setTimeout(()=>{
            if (this.greetToken === tok) this.blink();
        }, 550);
        setTimeout(()=>{
            if (this.greetToken === tok) this.blink();
        }, 1500);
        setTimeout(()=>{
            if (this.greetToken !== tok) return;
            this.waveUntil = 0;
            this.anim("hands", [
                [
                    0,
                    200,
                    Ease.inOut
                ]
            ]);
        }, 1550);
        setTimeout(()=>{
            if (this.greetToken !== tok) return;
            this.eyeOverride = "happy";
            this.eyeOverrideUntil = now() + 0.3;
        }, 1750);
    }
    interruptGreet() {
        if (this.hands <= 0.01 && now() >= this.waveUntil) return;
        this.greetToken++;
        this.waveUntil = 0;
        this.waveStart = 0;
        this.anim("hands", [
            [
                0,
                150,
                Ease.inOut
            ]
        ]);
    }
    setPermanentEmote(emote) {
        this.permanentEmote = emote;
        if (emote === "wink") {
            this.miniNextBehavior = now() + 0.8 + Math.random() * 1.7;
            return;
        }
        this.permanentEye = emote ? EMOTE_EYE[emote] : null;
        if (this.permanentEye) {
            this.eyeOverride = this.permanentEye;
            this.eyeOverrideUntil = Number.POSITIVE_INFINITY;
        } else if (this.eyeOverrideUntil === Number.POSITIVE_INFINITY) {
            this.eyeOverride = null;
            this.eyeOverrideUntil = 0;
        }
        this.miniNextBehavior = now() + 0.8 + Math.random() * 1.7;
    }
    triggerEmote(emote, duration = 1.8) {
        const t = now();
        this.eyeOverride = EMOTE_EYE[emote];
        this.eyeOverrideUntil = t + duration;
        switch(emote){
            case "love":
                this.anim("blush", [
                    [
                        1,
                        300,
                        Ease.out
                    ],
                    [
                        1,
                        (duration - 0.6) * 1000,
                        Ease.lin
                    ],
                    [
                        0,
                        300,
                        Ease.inOut
                    ]
                ]);
                this.emit("heart", 4);
                this.anim("oy", [
                    [
                        -0.1,
                        160,
                        Ease.out
                    ],
                    [
                        0,
                        300,
                        Ease.back
                    ]
                ]);
                break;
            case "surprised":
                this.anim("oy", [
                    [
                        -0.3,
                        140,
                        Ease.out
                    ],
                    [
                        0,
                        380,
                        Ease.back
                    ]
                ]);
                this.anim("es", [
                    [
                        1.25,
                        120,
                        Ease.out
                    ],
                    [
                        1,
                        500,
                        Ease.inOut
                    ]
                ]);
                break;
            case "proud":
                this.emit("star", 5);
                this.anim("tilt", [
                    [
                        -0.14,
                        220,
                        Ease.out
                    ],
                    [
                        -0.14,
                        (duration - 0.5) * 1000,
                        Ease.lin
                    ],
                    [
                        0,
                        280,
                        Ease.inOut
                    ]
                ]);
                this.anim("blush", [
                    [
                        0.7,
                        250,
                        Ease.out
                    ],
                    [
                        0.7,
                        (duration - 0.5) * 1000,
                        Ease.lin
                    ],
                    [
                        0,
                        300,
                        Ease.inOut
                    ]
                ]);
                break;
            case "wink":
                this.anim("tilt", [
                    [
                        0.12,
                        160,
                        Ease.out
                    ],
                    [
                        0.12,
                        (duration - 0.4) * 1000,
                        Ease.lin
                    ],
                    [
                        0,
                        240,
                        Ease.inOut
                    ]
                ]);
                break;
            case "yawn":
                this.anim("sy", [
                    [
                        1.12,
                        500,
                        Ease.inOut
                    ],
                    [
                        1,
                        500,
                        Ease.inOut
                    ]
                ]);
                this.anim("sx", [
                    [
                        0.94,
                        500,
                        Ease.inOut
                    ],
                    [
                        1,
                        500,
                        Ease.inOut
                    ]
                ]);
                setTimeout(()=>{
                    this.eyeOverride = "closed";
                    this.emit("z", 2);
                }, 700);
                break;
            case "happy":
                this.anim("blush", [
                    [
                        0.6,
                        200,
                        Ease.out
                    ],
                    [
                        0,
                        600,
                        Ease.inOut
                    ]
                ]);
                break;
            case "annoyed":
                this.eyeOverride = "line";
                this.eyeOverrideUntil = t + 0.8;
                setTimeout(()=>Sound.play("annoyed"), 60);
                break;
        }
    }
    emit(type, count) {
        for(let i = 0; i < count; i++){
            const isZ = type === "z";
            this.particles.push({
                type,
                x: (Math.random() - 0.5) * 0.9 + (isZ ? 0.55 : 0),
                y: -0.7 - Math.random() * 0.2,
                vx: (Math.random() - 0.5) * 0.35 + (isZ ? 0.18 : 0),
                vy: -(0.45 + Math.random() * 0.35),
                age: -i * 0.14,
                life: 1.3 + Math.random() * 0.5,
                rot: Math.random() * Math.PI * 2,
                size: 0.15 + Math.random() * 0.08
            });
        }
    }
    animateMorph(target, durationMs) {
        const dur = durationMs ?? (target > 0.5 ? 550 : 650);
        this.anim("morph", [
            [
                target,
                dur,
                Ease.inOut
            ]
        ]);
    }
    resetMorph() {
        this.tweens.delete("morph");
        this.locks.delete("morph");
        this.morph = 0;
    }
    get busy() {
        return this.tweens.size > 0 || this.particles.length > 0 || this.cfg.bounces || this.cfg.scans || this.cfg.breathes || this.cfg.zz || this.cfg.sweat || this.isMini || Math.abs(this.tgYaw - this.yaw) > 0.002 || Math.abs(this.tgPitch - this.pitch) > 0.002 || Math.abs(this.tgTilt - this.tilt) > 0.002 || Math.abs(this.tgSy - this.sy) > 0.002 || Math.abs(this.tgSx - this.sx) > 0.002 || Math.abs(this.tgEs - this.es) > 0.002 || this.slotH > 0.001 || Math.abs(this.slotHVel) > 0.001 || Math.abs(this.col[0] - this.colT[0]) > 0.003 || Math.abs(this.col[1] - this.colT[1]) > 0.003 || Math.abs(this.col[2] - this.colT[2]) > 0.003;
    }
    anim(prop, keys, onComplete) {
        this.tweens.set(prop, {
            prop,
            keys,
            index: 0,
            from: this[prop],
            startMs: performance.now(),
            onComplete
        });
        this.locks.add(prop);
    }
    update(dt) {
        const n = now();
        const nowMs = performance.now();
        for (const tw of [
            ...this.tweens.values()
        ]){
            const k = tw.keys[tw.index];
            const p = Math.min(1, Math.max(0, (nowMs - tw.startMs) / k[1]));
            this[tw.prop] = tw.from + (k[0] - tw.from) * k[2](p);
            if (p >= 1) {
                tw.from = k[0];
                tw.index += 1;
                tw.startMs = nowMs;
                if (tw.index >= tw.keys.length) {
                    this.tweens.delete(tw.prop);
                    this.locks.delete(tw.prop);
                    tw.onComplete?.();
                }
            }
        }
        const t = n - this.t0;
        let ty = this.lookX * 0.62;
        let tp = this.lookY * 0.5;
        if (this.cfg.look) {
            ty = ty * 0.35 + this.cfg.look[0] * 0.55;
            tp = tp * 0.3 + this.cfg.look[1] * 0.5;
        }
        if (this.cfg.scans) {
            ty = Math.sin(t * 2.6) * 0.6;
            tp = -0.06;
        }
        if (this.state === "sleeping") {
            ty = 0;
            tp = -0.14;
        }
        if (this.state === "dizzy") {
            ty = Math.sin(t * 9) * 0.25;
        }
        if (this.isMini && !this.cfg.look && !this.cfg.scans && this.state !== "sleeping" && this.state !== "dizzy") {
            if (n > this.miniLookNextTime) {
                this.miniLookTarget = {
                    x: -0.88 + Math.random() * 1.76,
                    y: -0.55 + Math.random() * 1.0
                };
                this.miniLookNextTime = n + 0.5 + Math.random() * 1.5;
            }
            ty = this.miniLookTarget.x * 0.62;
            tp = this.miniLookTarget.y * 0.5;
        }
        this.tgYaw = ty;
        this.tgPitch = tp;
        this.tgTilt = this.cfg.tilt;
        if (n > this.waveStart && n < this.waveUntil) {
            const wt = n - this.waveStart;
            this.tgTilt = -0.06 + Math.sin(2 * Math.PI * 1.2 * wt) * 0.07;
        }
        const bounce = this.cfg.bounces ? -Math.abs(Math.sin(t * 5.2)) * 0.07 : 0;
        const kGen = 1 - Math.pow(0.0008, dt);
        if (!this.locks.has("oy")) this.oy += (bounce - this.oy) * kGen;
        if (this.cfg.breathes) {
            const amp = this.isMini ? 0.07 : 0.035;
            this.tgSy = 1 + Math.sin(t * 1.8) * amp;
            this.tgSx = 1 - Math.sin(t * 1.8) * amp * 0.57;
        } else if (this.isMini) {
            this.tgSy = 1 + Math.sin(t * 2.2) * 0.04;
            this.tgSx = 1 - Math.sin(t * 2.2) * 0.02;
        } else {
            this.tgSy = 1;
            this.tgSx = 1;
        }
        if (this.isMini && n > this.miniNextBehavior) this.doMiniBehaviorLoop();
        const kLook = 1 - Math.pow(0.0025, dt);
        if (!this.locks.has("yaw")) this.yaw += (this.tgYaw - this.yaw) * kLook;
        if (!this.locks.has("pitch")) this.pitch += (this.tgPitch - this.pitch) * kLook;
        if (!this.locks.has("tilt")) this.tilt += (this.tgTilt - this.tilt) * kGen;
        if (!this.locks.has("sy")) this.sy += (this.tgSy - this.sy) * kGen;
        if (!this.locks.has("sx")) this.sx += (this.tgSx - this.sx) * kGen;
        if (!this.locks.has("es")) this.es += (this.tgEs - this.es) * kGen;
        this.col = mix3(this.col, this.colT, 1 - Math.pow(0.002, dt));
        if (n > this.nextBlink) {
            if (this.state !== "sleeping" && this.state !== "dizzy") {
                this.blink();
                if (Math.random() < 0.22) setTimeout(()=>this.blink(), 230);
            }
            this.nextBlink = n + 2.2 + Math.random() * 3.2;
        }
        if (this.eyeOverride && n > this.eyeOverrideUntil) {
            this.eyeOverride = this.permanentEye;
            if (this.permanentEye) this.eyeOverrideUntil = Number.POSITIVE_INFINITY;
        }
        if (n - this.lastAmbient > 1.3) {
            this.lastAmbient = n;
            if (this.cfg.zz) this.emit("z", 1);
            if (!this.isMini && this.cfg.sweat && Math.random() < 0.5) this.emit("sweat", 1);
        }
        for (const p of this.particles)p.age += dt;
        this.particles = this.particles.filter((p)=>p.age < p.life);
        const omega = 2 * Math.PI / 0.25;
        const zeta = 0.6;
        const acc = omega * omega * (this.slotHTarget - this.slotH) - 2 * zeta * omega * this.slotHVel;
        this.slotHVel += acc * dt;
        this.slotH = Math.max(0, this.slotH + this.slotHVel * dt);
        this.lastTime = n;
    }
    doMiniBehaviorLoop() {
        const n = now();
        switch(this.permanentEmote){
            case "happy":
                if (this.locks.has("oy")) {
                    this.miniNextBehavior = n + 0.4;
                    return;
                }
                this.anim("oy", [
                    [
                        -0.3,
                        120,
                        Ease.out
                    ],
                    [
                        0.03,
                        200,
                        Ease.inOut
                    ],
                    [
                        0,
                        160,
                        Ease.back
                    ]
                ]);
                this.anim("sy", [
                    [
                        0.82,
                        80,
                        Ease.out
                    ],
                    [
                        1.18,
                        130,
                        Ease.out
                    ],
                    [
                        0.88,
                        160,
                        Ease.inOut
                    ],
                    [
                        1,
                        200,
                        Ease.back
                    ]
                ]);
                this.anim("sx", [
                    [
                        1.15,
                        80,
                        Ease.out
                    ],
                    [
                        0.88,
                        130,
                        Ease.out
                    ],
                    [
                        1.06,
                        160,
                        Ease.inOut
                    ],
                    [
                        1,
                        200,
                        Ease.back
                    ]
                ]);
                this.miniNextBehavior = n + 2.2 + Math.random() * 1.2;
                break;
            case "annoyed":
                if (this.locks.has("yaw")) {
                    this.miniNextBehavior = n + 0.5;
                    return;
                }
                this.anim("yaw", [
                    [
                        -0.65,
                        50,
                        Ease.out
                    ],
                    [
                        0.65,
                        90,
                        Ease.inOut
                    ],
                    [
                        -0.5,
                        80,
                        Ease.inOut
                    ],
                    [
                        0.4,
                        75,
                        Ease.inOut
                    ],
                    [
                        -0.2,
                        70,
                        Ease.inOut
                    ],
                    [
                        0,
                        140,
                        Ease.out
                    ]
                ]);
                this.miniNextBehavior = n + 3.0 + Math.random() * 2.5;
                break;
            case "wink":
                this.eyeOverride = "wink";
                this.eyeOverrideUntil = n + 0.55;
                this.anim("tilt", [
                    [
                        0.13,
                        100,
                        Ease.out
                    ],
                    [
                        0.13,
                        320,
                        Ease.lin
                    ],
                    [
                        0,
                        200,
                        Ease.inOut
                    ]
                ]);
                this.miniNextBehavior = n + 2.2 + Math.random() * 2.0;
                break;
            case "love":
                this.emit("heart", 2);
                this.anim("tilt", [
                    [
                        -0.1,
                        180,
                        Ease.out
                    ],
                    [
                        0.1,
                        340,
                        Ease.inOut
                    ],
                    [
                        0,
                        220,
                        Ease.inOut
                    ]
                ]);
                this.miniNextBehavior = n + 2.6 + Math.random() * 1.5;
                break;
            default:
                this.miniNextBehavior = n + 3.0 + Math.random() * 2.0;
        }
    }
    draw(x, W, H) {
        const R = W * 0.3;
        const rx = R * 1.14;
        const ry = R * 0.88;
        const cx = W / 2 + this.ox * R;
        const cy = H / 2 + this.particleOverhang / 2 + this.oy * R + R * 0.06;
        this.drawHandsBehind(x, R, rx, ry, cx, cy);
        x.save();
        x.translate(cx, cy);
        if (this.tilt !== 0) x.rotate(this.tilt);
        x.scale(this.sx, this.sy);
        const body = this.bodyPath(rx, ry, R);
        this.drawBody(x, body, R, rx, ry);
        const blushVal = Math.max(this.blush, this.tint * 0.5) * (1 - this.morph);
        if (blushVal > 0.01) {
            x.save();
            x.clip(body);
            const yOffset = Math.sin(this.yaw) * rx * 0.8;
            x.fillStyle = `rgba(255,120,150,${0.5 * blushVal})`;
            for (const sd of [
                -1,
                1
            ]){
                x.beginPath();
                x.ellipse(sd * rx * 0.55 + yOffset, ry * 0.2, R * 0.17, R * 0.1, 0, 0, Math.PI * 2);
                x.fill();
            }
            x.restore();
        }
        this.drawEyes(x, body, R, rx, ry);
        if (this.morph > 0.05) this.drawMouth(x, body, R);
        x.restore();
        if (this.badge && this.badgeS > 0.01 && this.morph < 0.25) {
            this.drawBadge(x, this.badge, R, cx, cy);
        }
        this.drawParticles(x, R, cx, cy);
    }
    bodyPath(rx, ry, R) {
        const n = 72;
        const expN = 2.0 / 2.7;
        const tw = R * 1.0;
        const th = R * 0.94;
        const tr = R * 0.42;
        const p = new Path2D();
        const m = this.morph;
        for(let i = 0; i <= n; i++){
            const a = i / n * Math.PI * 2;
            const ca = Math.cos(a);
            const sa = Math.sin(a);
            const px0 = rx * (ca >= 0 ? Math.pow(ca, expN) : -Math.pow(-ca, expN));
            const py0 = ry * (sa >= 0 ? Math.pow(sa, expN) : -Math.pow(-sa, expN));
            let px = px0;
            let py = py0;
            if (m >= 0.005) {
                const rr = rrPoint(ca, sa, tw, th, tr);
                px = lerp(px0, rr.x, m);
                py = lerp(py0, rr.y, m);
            }
            if (i === 0) p.moveTo(px, py);
            else p.lineTo(px, py);
        }
        p.closePath();
        return p;
    }
    drawBody(x, body, R, rx, ry) {
        if (this.bodyColor) {
            x.fillStyle = rgba(this.bodyColor, 1);
            x.fill(body);
            return;
        }
        const g = x.createLinearGradient(rx * 0.7, -ry * 0.85, -rx * 0.8, ry * 0.9);
        g.addColorStop(0, rgba(BASE_TOP));
        g.addColorStop(1, rgba(BASE_BOTTOM));
        x.fillStyle = g;
        x.fill(body);
        const effectiveTint = this.tint * (1 - this.morph);
        if (effectiveTint > 0.01) {
            const tg = x.createLinearGradient(0, ry, 0, -ry);
            tg.addColorStop(0, rgba(this.col, 0.72 * effectiveTint));
            tg.addColorStop(1, rgba(this.col, 0));
            x.fillStyle = tg;
            x.fill(body);
        }
        const sh = x.createRadialGradient(0, 0, R * 0.15, 0, 0, R * 1.25);
        sh.addColorStop(0, "rgba(0,0,0,0)");
        sh.addColorStop(0.6, "rgba(0,0,0,0)");
        sh.addColorStop(1, "rgba(0,0,0,0.2)");
        x.fillStyle = sh;
        x.fill(body);
        const hl = x.createRadialGradient(rx * 0.34, -ry * 0.46, 0, rx * 0.34, -ry * 0.46, R * 0.42);
        hl.addColorStop(0, "rgba(255,255,255,0.55)");
        hl.addColorStop(1, "rgba(255,255,255,0)");
        x.fillStyle = hl;
        x.fill(body);
    }
    drawEyes(x, body, R, rx, ry) {
        let shape = this.eyeOverride ?? this.cfg.eye;
        if (this.morph > 0.5) {
            if (this.isChewing) shape = "happy";
            else if (this.slotHTarget > 0.05 || this.slotH > 0.1) shape = "cup";
        }
        x.save();
        x.clip(body);
        const ink = this.isMini ? MINI_INK : INK;
        x.fillStyle = ink;
        x.strokeStyle = ink;
        for (const sd of [
            -1,
            1
        ]){
            const eyeYaw = sd * EYE_SP + this.yaw;
            let eyePitch = EYE_P + this.pitch + this.roll;
            eyePitch = ((eyePitch + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
            const cp = Math.cos(eyePitch);
            if (Math.cos(eyeYaw) * cp <= 0.04) continue;
            const ex = Math.sin(eyeYaw) * cp * rx;
            const ey = -Math.sin(eyePitch) * ry + (this.morph > 0 ? ry * 0.14 * this.morph : 0);
            const fx = lerp(Math.max(0.18, Math.cos(eyeYaw)), 1, this.morph * 0.7);
            const fy = lerp(Math.max(0.18, cp), 1, this.morph * 0.7);
            const eyeMult = this.isMini ? 1.9 : 1.0;
            const ew = R * EYE_W * this.es * eyeMult;
            const eh = R * EYE_H * this.es * eyeMult;
            x.save();
            x.translate(ex, ey);
            x.scale(fx, fy);
            this.drawEyeShape(x, shape, ew, eh, sd, ink);
            x.restore();
        }
        x.restore();
    }
    drawEyeShape(x, shape, w, h, sd, ink) {
        const t = now();
        switch(shape){
            case "wide":
                this.drawEyeShape(x, "pill", w * 1.16, h * 1.12, sd, ink);
                break;
            case "pill":
                {
                    const hh = Math.max(h * this.open, w * 0.3);
                    roundRectPath(x, -w / 2, -hh / 2, w, hh, Math.min(w / 2, hh / 2));
                    x.fill();
                    break;
                }
            case "dot":
                x.beginPath();
                x.arc(0, 0, w * 0.45, 0, Math.PI * 2);
                x.fill();
                break;
            case "line":
                x.rotate(-sd * 0.2);
                roundRectPath(x, -w * 0.78, -w * 0.21, w * 1.56, w * 0.42, w * 0.21);
                x.fill();
                break;
            case "flat":
                roundRectPath(x, -w * 0.72, -w * 0.2, w * 1.44, w * 0.4, w * 0.2);
                x.fill();
                break;
            case "happy":
                x.lineWidth = w * 0.5;
                x.lineCap = "round";
                x.beginPath();
                x.arc(0, h * 0.18, w * 0.82, Math.PI * 1.12, Math.PI * 1.88);
                x.stroke();
                break;
            case "closed":
                x.lineWidth = w * 0.36;
                x.lineCap = "round";
                x.beginPath();
                x.arc(0, -h * 0.08, w * 0.78, Math.PI * 0.15, Math.PI * 0.85);
                x.stroke();
                break;
            case "spiral":
                {
                    x.lineWidth = w * 0.22;
                    x.lineCap = "round";
                    x.beginPath();
                    for(let a = 0; a < 4.4 * Math.PI; a += 0.2){
                        const r = w * 0.06 + a * w * 0.058;
                        const aa = a + t * 9 * sd;
                        const px = Math.cos(aa) * r;
                        const py = Math.sin(aa) * r;
                        if (a === 0) x.moveTo(px, py);
                        else x.lineTo(px, py);
                    }
                    x.stroke();
                    break;
                }
            case "heart":
                x.fillStyle = "#FF4D6D";
                heartPath(x, w * 1.2);
                x.fill();
                x.fillStyle = ink;
                break;
            case "star":
                x.fillStyle = "#F7B32B";
                x.rotate(t * 1.5 * sd);
                starPath(x, w * 1.05, w * 0.46);
                x.fill();
                x.fillStyle = ink;
                break;
            case "tired":
                roundRectPath(x, -w / 2, -h * 0.02, w, h * 0.38, w / 2);
                x.fill();
                roundRectPath(x, -w * 0.62, -h * 0.1, w * 1.24, w * 0.22, w * 0.11);
                x.fill();
                break;
            case "wink":
                if (sd < 0) {
                    const hh = Math.max(h * this.open, w * 0.3);
                    roundRectPath(x, -w / 2, -hh / 2, w, hh, Math.min(w / 2, hh / 2));
                    x.fill();
                } else {
                    x.lineWidth = w * 0.5;
                    x.lineCap = "round";
                    x.beginPath();
                    x.arc(0, h * 0.18, w * 0.82, Math.PI * 1.12, Math.PI * 1.88);
                    x.stroke();
                }
                break;
            case "cup":
                {
                    const hh = Math.max(h * this.open, w * 0.3);
                    const cr = Math.min(w / 2, hh / 2);
                    x.beginPath();
                    x.moveTo(-w / 2, -hh / 2);
                    x.lineTo(w / 2, -hh / 2);
                    x.lineTo(w / 2, hh / 2 - cr);
                    x.quadraticCurveTo(w / 2, hh / 2, w / 2 - cr, hh / 2);
                    x.lineTo(-w / 2 + cr, hh / 2);
                    x.quadraticCurveTo(-w / 2, hh / 2, -w / 2, hh / 2 - cr);
                    x.closePath();
                    x.fill();
                    break;
                }
        }
    }
    drawMouth(x, body, R) {
        const m = this.morph;
        const hW = R * 1.8 * m;
        const hH = this.slotH * R * m;
        const hX = -hW / 2;
        const boxTop = -R * (0.88 + 0.06 * m);
        const hY = boxTop + R * 0.08 * m;
        x.save();
        x.clip(body);
        x.strokeStyle = `rgba(255,255,255,${0.55 * m})`;
        x.lineWidth = 1;
        x.lineCap = "round";
        x.beginPath();
        x.moveTo(-R * 0.9 * m, boxTop + 1);
        x.lineTo(R * 0.9 * m, boxTop + 1);
        x.stroke();
        if (hH > 0.8) {
            const hR = Math.min(hW / 2, hH / 2);
            const g = x.createLinearGradient(0, hY, 0, hY + hH);
            g.addColorStop(0, "rgb(7,8,10)");
            g.addColorStop(1, "rgb(16,19,26)");
            roundRectPath(x, hX, hY, hW, hH, hR);
            x.fillStyle = g;
            x.fill();
            if (hH > 4) {
                const lipR = Math.min(hR, (hW - 2) / 2);
                x.strokeStyle = `rgba(255,255,255,${0.28 * m})`;
                x.beginPath();
                x.moveTo(hX + lipR, hY + hH - 0.5);
                x.lineTo(hX + hW - lipR, hY + hH - 0.5);
                x.stroke();
            }
        }
        x.restore();
    }
    drawHandsBehind(x, R, rx, ry, cx, cy) {
        if (this.hands <= 0.01 || this.isMini) return;
        if (R <= 14) return;
        const n = now();
        const bodyH = 2 * ry;
        const hew = 0.3 * ry * this.hands;
        const heh = 0.26 * ry * this.hands;
        const hwB = rx * this.sx;
        const hhB = ry * this.sy;
        const isWaving = n >= this.waveStart && this.waveStart > 0 && n < this.waveUntil;
        for (const sd of [
            -1,
            1
        ]){
            let localX;
            let localY;
            let handRot = 0;
            if (sd > 0 && isWaving) {
                const wt = n - this.waveStart;
                const rise = Math.min(1, wt / 0.18);
                const riseEased = 1 - Math.pow(1 - rise, 3);
                const restX = hwB * 1.08;
                const restY = hhB * 0.7;
                const oscX = Math.cos(13 * wt) * 0.06 * bodyH;
                const oscY = -Math.sin(13 * wt) * 0.14 * bodyH;
                const waveX = hwB * 1.1 + oscX;
                const waveY = -hhB * 0.15 + oscY;
                localX = restX + (waveX - restX) * riseEased;
                localY = restY + (waveY - restY) * riseEased;
                handRot = (-0.5 + Math.sin(13 * wt) * 0.35) * riseEased;
            } else if (sd < 0 && isWaving) {
                const wt = n - this.waveStart;
                localX = -hwB * 1.08;
                localY = hhB * 0.7 + Math.sin(6 * wt) * 0.04 * bodyH;
            } else {
                localX = sd * hwB * 1.08;
                localY = hhB * 0.7;
            }
            const cosT = Math.cos(this.tilt);
            const sinT = Math.sin(this.tilt);
            const worldX = cx + cosT * localX - sinT * localY;
            const worldY = cy + sinT * localX + cosT * localY;
            x.save();
            x.translate(worldX, worldY);
            if (handRot !== 0) x.rotate(handRot);
            const g = x.createLinearGradient(hew * 0.7, -heh * 0.85, -hew * 0.8, heh * 0.9);
            if (this.bodyColor) {
                g.addColorStop(0, rgba(mix3(this.bodyColor, [
                    1,
                    1,
                    1
                ], 0.35)));
                g.addColorStop(1, rgba(this.bodyColor));
            } else {
                g.addColorStop(0, rgba(BASE_TOP));
                g.addColorStop(1, rgba(BASE_BOTTOM));
            }
            x.beginPath();
            x.ellipse(0, 0, hew, heh, 0, 0, Math.PI * 2);
            x.fillStyle = g;
            x.fill();
            x.strokeStyle = "rgba(0,0,0,0.08)";
            x.lineWidth = 1;
            x.stroke();
            x.restore();
        }
    }
    drawBadge(x, badge, R, cx, cy) {
        const bs = this.badgeS * (this.isMini ? 1.25 : 1);
        const bx = cx - R * 0.72 * this.sx;
        const by = cy - R * 0.72 * this.sy;
        const t = now();
        x.save();
        x.translate(bx, by);
        x.scale(bs, bs);
        const col = rgba(badge.color);
        if (badge.kind === "dots") {
            if (this.isMini) {
                const phase = t * 2.4 % 1;
                const dotR = R * 0.22 * (1 + 0.25 * Math.sin(phase * Math.PI * 2));
                x.fillStyle = "#000";
                x.beginPath();
                x.arc(0, 0, R * 0.2, 0, Math.PI * 2);
                x.fill();
                x.fillStyle = col;
                x.beginPath();
                x.arc(0, 0, dotR, 0, Math.PI * 2);
                x.fill();
            } else {
                const pw = R * 0.72;
                const ph = R * 0.36;
                roundRectPath(x, -pw / 2, -ph / 2, pw, ph, ph / 2);
                x.fillStyle = col;
                x.fill();
                for(let i = 0; i < 3; i++){
                    const phase = ((t * 2.4 - i * 0.22) % 1 + 1) % 1;
                    const dotR = R * 0.055 * (1 + 0.4 * Math.max(0, Math.sin(phase * Math.PI * 2)));
                    x.fillStyle = "#fff";
                    x.beginPath();
                    x.arc((i - 1) * R * 0.18, 0, dotR, 0, Math.PI * 2);
                    x.fill();
                }
            }
        } else if (badge.kind === "bang" || badge.kind === "question") {
            x.fillStyle = "#000";
            x.beginPath();
            x.arc(0, 0, R * 0.3, 0, Math.PI * 2);
            x.fill();
            x.fillStyle = col;
            x.beginPath();
            x.arc(0, 0, R * 0.23, 0, Math.PI * 2);
            x.fill();
            if (!this.isMini) {
                x.fillStyle = "#fff";
                x.font = `900 ${R * 0.32}px ${FONT}`;
                x.textAlign = "center";
                x.textBaseline = "middle";
                x.fillText(badge.kind === "bang" ? "!" : "?", 0, R * 0.02);
            }
        } else {
            x.fillStyle = "#000";
            x.beginPath();
            x.arc(0, 0, R * 0.2, 0, Math.PI * 2);
            x.fill();
            x.fillStyle = col;
            x.beginPath();
            x.arc(0, 0, R * 0.135, 0, Math.PI * 2);
            x.fill();
        }
        x.restore();
    }
    drawParticles(x, R, cx, cy) {
        for (const p of this.particles){
            if (p.age <= 0) continue;
            const k = p.age / p.life;
            const a = k < 0.2 ? k / 0.2 : 1 - (k - 0.2) / 0.8;
            const px = cx + (p.x + p.vx * p.age) * R * 1.3;
            const py = cy + (p.y + p.vy * p.age) * R * 1.3;
            const sz = R * p.size * (1 + k * 0.4);
            x.save();
            x.translate(px, py);
            x.globalAlpha = Math.min(1, Math.max(0, a));
            switch(p.type){
                case "heart":
                    x.rotate(Math.sin(p.age * 6) * 0.3);
                    x.fillStyle = "#FF4D6D";
                    heartPath(x, sz);
                    x.fill();
                    break;
                case "star":
                    x.rotate(p.rot + p.age * 2);
                    x.fillStyle = "#F7B32B";
                    starPath(x, sz, sz * 0.45);
                    x.fill();
                    break;
                case "spark":
                    x.rotate(p.rot);
                    x.fillStyle = "#fff";
                    starPath(x, sz * 0.8, sz * 0.18);
                    x.fill();
                    break;
                case "sweat":
                    x.fillStyle = "#7CC7FF";
                    x.beginPath();
                    x.moveTo(0, -sz);
                    x.quadraticCurveTo(sz * 0.8, sz * 0.2, 0, sz * 0.6);
                    x.quadraticCurveTo(-sz * 0.8, sz * 0.2, 0, -sz);
                    x.fill();
                    break;
                case "z":
                    x.fillStyle = "rgb(209,219,235)";
                    x.font = `700 ${sz * 1.9}px ${FONT}`;
                    x.textAlign = "center";
                    x.textBaseline = "middle";
                    x.fillText("z", 0, 0);
                    break;
            }
            x.restore();
        }
    }
}
function rrPoint(ca, sa, W, H, cr) {
    const eps = 1e-6;
    const kx = ca >= 0 ? 1 : -1;
    const ky = sa >= 0 ? 1 : -1;
    const cx = kx * (W - cr);
    const cy = ky * (H - cr);
    const dot = ca * cx + sa * cy;
    const disc = dot * dot - (cx * cx + cy * cy - cr * cr);
    if (disc >= 0) {
        const t = dot + Math.sqrt(disc);
        if (t > eps) {
            const px = ca * t;
            const py = sa * t;
            if (Math.abs(px) >= W - cr - eps && Math.abs(py) >= H - cr - eps) return {
                x: px,
                y: py
            };
        }
    }
    if (Math.abs(sa) > eps) {
        const t = ky * H / sa;
        if (t > eps) {
            const px = ca * t;
            if (Math.abs(px) <= W - cr + eps) return {
                x: px,
                y: ky * H
            };
        }
    }
    if (Math.abs(ca) > eps) {
        const t = kx * W / ca;
        if (t > eps) {
            const py = sa * t;
            if (Math.abs(py) <= H - cr + eps) return {
                x: kx * W,
                y: py
            };
        }
    }
    return {
        x: kx * W,
        y: ky * H
    };
}

function changerCouleurs(haut, bas, encre) { BASE_TOP = haut; BASE_BOTTOM = bas; INK = encre; }
// ════════════════════════════════════════════════════════════════════════════════════════════════════════
// Personnage AOCEDA (v3, chorégraphiée) : extension du moteur d'animation de Coucou (code MIT © 2026 Louis Raillé).
// Ni le nom, ni l'apparence telle quelle, ni les sons de Mochi (tous droits réservés) ne sont repris.
//
// Méthode reprise des références du designer de Coucou (design/animations/greeting-v2.html, upload-sequence.html) :
// chaque action est une CHORÉGRAPHIE, une fonction du temps découpée en phases (préparation, action, résolution),
// avec des écrasements qui gardent le volume, des mains qui sortent de SOUS le corps (boule au repos, capsule
// pour le geste), des clignements qui ponctuent, et un retour au calme.
// Règles chiffrées (fiches « motion-design » de LottieFiles, MIT, principes Disney) : anticipation 100-200 ms à
// 10-20 % du geste, écrasement ~1,2 × 0,8, éléments enfants en retard de 50-150 ms (ici les oreilles, sur ressort),
// dépassement 10-20 % (joie), 0 % (erreur), tremblement d'erreur 2-3 cycles décroissants en 300-400 ms, tristesse
// lente (600 ms et plus), respiration d'ambiance 0,98-1,02 sur ~3 s, sortie plus courte que l'entrée.
//
// Une seule pastille à la fois (anneau noir, disque coloré, glyphe blanc). Pas de teinte sur le corps doré : l'état
// se lit au halo. Une action du chatbot = perso.jouer("nom", options) ; liste : ACTIONS_AOCEDA.
// ════════════════════════════════════════════════════════════════════════════════════════════════════════

const AO = { or: "#ffc20e", orFort: "#f2b300", encre: "#16212e", vert: "#1f9d55", rouge: "#e5484d", bleu: "#3b9eff",
             violet: "#8b5cf6", orange: "#f59e0b", gris: "#8e96a3", cyan: "#22b8d4", nuit: "#5b6b8c" };

/** Courbes d'animation : celles de Coucou (Ease) et quelques-unes en plus. */
const Ez = {
  ...Ease,
  sine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
  outQuad: (t) => 1 - (1 - t) * (1 - t),
  backDoux: (t) => { const c1 = 1.1, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
};
/** 0 -> 1 -> 0 entre a et b (demi-sinus : part et arrive avec de la vitesse, pour les petits gestes). */
const cloche = (t, a, b) => (t <= a || t >= b ? 0 : Math.sin(Math.PI * (t - a) / (b - a)));
/** 0 -> 1 -> 0 entre a et b, départ et arrivée en douceur (sinus²) : pour les GRANDS mouvements. */
const bosse = (t, a, b) => (t <= a || t >= b ? 0 : Math.pow(Math.sin(Math.PI * (t - a) / (b - a)), 2));
/** Images clés [[t, valeur, courbe?], ...] ; la courbe s'applique au segment qui MÈNE à la clé (comme kf de Coucou). */
function kf(t, cles, courbe = Ease.inOut) {
  if (t <= cles[0][0]) return cles[0][1];
  for (let i = 1; i < cles.length; i++) {
    if (t <= cles[i][0]) return lerp(cles[i - 1][1], cles[i][1], (cles[i][2] || courbe)(seg(t, cles[i - 1][0], cles[i][0])));
  }
  return cles[cles.length - 1][1];
}
/** Entrée puis sortie : 0 avant a, monte jusqu'à 1 en `entree` s, redescend à partir de b en `sortie` s. */
function tenue(t, a, b, entree = 0.25, sortie = 0.25, courbe = Ez.inOut) {
  if (t <= a || t >= b + sortie) return 0;
  if (t < a + entree) return courbe(seg(t, a, a + entree));
  if (t < b) return 1;
  return 1 - courbe(seg(t, b, b + sortie));
}

/** Pose de repos. Les chorégraphies écrivent des écarts à cette pose ; tout ce qui est numérique se fond. */
const REPOS = Object.freeze({
  dx: 0, dy: 0, sx: 1, sy: 1, inc: 0, hoche: 0, tourne: 0, roule: 0, echelle: 1, alpha: 1,
  es: 1, ouv: 1, rougit: 0,
  oG: 0, oD: 0, oL: 1,                                   // oreilles : inclinaison (+ = tombante), longueur
  regW: 0, regX: 0, regY: 0,                             // regard imposé (sens de l'écran, y vers le BAS) et son poids
  bouche: 0, rond: 0,                                    // bouche hors parole (bâillement, « oh ») ; 1 = ronde
  halo: 0, hR: 1, hG: 0.76, hB: 0.05,                    // halo d'état autour du corps et sa couleur
  gesteParole: 0,                                        // 1 = les mains accompagnent les syllabes accentuées
  mgK: 0, mgX: -1.2, mgY: 0.6, mgA: 0, mgL: 0,           // main gauche : sortie 0..1, position (rx, ry), angle, 0 boule..1 capsule
  mdK: 0, mdX: 1.2, mdY: 0.6, mdA: 0, mdL: 0,            // main droite
});
const CHAMPS = Object.keys(REPOS);

// ── outils de chorégraphie (écrivent dans la pose p) ─────────────────────────────────────────────────────
function teinte(p, hex, force) { const c = hexToRGB(hex); p.hR = c[0]; p.hG = c[1]; p.hB = c[2]; p.halo = force; }
function regarder(p, x, y, w = 1) { p.regW = w; p.regX = x; p.regY = y; }
function main(p, cote, k, x, y, a = 0, L = 0) {
  const c = cote < 0 ? "mg" : "md"; p[c + "K"] = k; p[c + "X"] = x; p[c + "Y"] = y; p[c + "A"] = a; p[c + "L"] = L;
}
/** Bord du corps (en rx) à la hauteur y (en ry) : le corps est une superellipse d'exposant 2,7 (moteur Coucou). */
function bordX(y) { return Math.pow(1 - Math.pow(Math.min(0.999, Math.abs(y)), 2.7), 1 / 2.7); }
/** Main au repos, posée contre le bas du corps, un bon tiers caché derrière lui (comme le coucou d'origine). */
function mainRepos(p, cote, k) { main(p, cote, k, cote * (bordX(0.62) + 0.09), 0.62, 0, 0); }
/** Saut complet : tassement d'anticipation, détente étirée, vol en parabole, impact écrasé, retour avec rebond. */
function sauter(p, t, t0, h, vol = 0.34, f = 1) {
  const t1 = t0 + 0.11, t2 = t1 + vol, t3 = t2 + 0.08, t4 = t3 + 0.2;
  if (t < t0 || t >= t4) return;
  let dy = 0, sy = 1;
  if (t < t1) { const k = Ez.sine(seg(t, t0, t1)); sy = 1 - 0.13 * f * k; dy = 0.035 * f * k; }
  else if (t < t2) {
    const u = seg(t, t1, t2), d = t - t1;                // détente : au moins 70 ms, sinon l'étirement « claque »
    const etire = d < 0.07 ? lerp(-0.13, 0.12, Ez.sine(d / 0.07)) : 0.12 * (1 - Ez.inOut(seg(d, 0.07, 0.07 + vol * 0.35)));
    sy = 1 + f * (etire + 0.05 * Ez.easeIn(seg(u, 0.7, 1)));
    // poussée : le corps accélère pendant 70 ms (une parabole seule partirait à pleine vitesse dès la 1re image)
    const pousse = Ez.sine(Math.min(1, d / 0.07));
    dy = lerp(0.035 * f, 0, pousse) - h * 4 * u * (1 - u) * pousse;
  } else if (t < t3) { const k = Ez.sine(seg(t, t2, t3)); sy = lerp(1 + 0.05 * f, 1 - 0.16 * f, k); dy = 0.035 * f * k; }
  else { const k = seg(t, t3, t4); sy = lerp(1 - 0.16 * f, 1, Ez.back(k)); dy = 0.035 * f * (1 - Ez.out(k)); }
  p.dy += dy; p.sy *= sy; p.sx *= 1 + (1 - sy) * 0.8;
}
/** Un hochement « oui » : petite montée d'anticipation, la tête baisse, remonte en dépassant à peine, se pose. */
function hocher(p, t, t0, a = 0.22, d = 0.46) {
  const u = t - t0; if (u < 0 || u >= d) return;
  const v = kf(u, [[0, 0], [d * 0.14, a * 0.18, Ez.out], [d * 0.42, -a, Ez.inOut], [d * 0.72, a * 0.1, Ez.inOut], [d, 0, Ez.inOut]]);
  p.hoche += v; p.dy -= v * 0.06; p.sy *= 1 + v * 0.08;
}
/** Oscillation qui s'amortit (tremblement, « non ») : `cycles` allers-retours en `d` secondes, sans dépassement final. */
function secouer(p, t, t0, champ, ampl, cycles, d) {
  const u = (t - t0) / d; if (u < 0 || u >= 1) return;
  const attaque = Ez.inOut(Math.min(1, (t - t0) / 0.08));   // 80 ms pour prendre l'amplitude (pas de saut à la 1re image)
  p[champ] += ampl * attaque * Math.pow(1 - u, 1.5) * Math.sin(2 * Math.PI * cycles * u);
}
/** Main en capsule dirigée vers `a` (angle écran, y vers le bas) : son bout intérieur est accroché juste DANS le bord
 *  du corps (l'épaule monte avec la cible), le reste dépasse vers la cible. tape > 0 : la main s'allonge (« ici »).
 *  L : 1 = capsule longue (montrer), 0,6 = plus courte (gestes de parole). */
function pointerVers(p, cote, a, k, tape = 0, L = 1) {
  const am = Math.atan2(Math.sin(a), Math.abs(Math.cos(a)));          // angle ramené du côté droit
  const ux = Math.cos(am), uy = Math.sin(am);
  const ay = clamp(uy * 0.35, -0.4, 0.45), ax = 0.86 * bordX(ay);    // épaule assez basse : un bras levé ne frôle pas l'oreille
  const lx = lerp(0.2316, 0.3088, L) * (1 + 0.25 * tape), ly = lerp(0.3, 0.4, L) * (1 + 0.25 * tape);   // demi-longueur
  main(p, cote, k, cote * (ax + ux * lx), ay + uy * ly, cote > 0 ? am : -am, L);
}
/** Salut de la main (repris du coucou de référence : capsule à -35° qui s'agite à 2,5 Hz, autre main posée). */
function saluer(p, t, t0, t1) {
  const kG = t < t1 ? Ez.back(seg(t, t0 - 0.16, t0 - 0.02)) : 1 - Ez.easeIn(seg(t, t1, t1 + 0.19));
  const kD = t < t1 ? Ez.back(seg(t, t0 - 0.12, t0 + 0.02)) : 1 - Ez.easeIn(seg(t, t1 + 0.03, t1 + 0.22));
  if (kG <= 0 && kD <= 0) return;
  // l'agitation et le balancement s'éteignent en douceur pendant que les mains rentrent (pas de coupure)
  const w = Math.max(0, t - t0), wa = w * 2 * Math.PI * 2.5;
  const agite = t < t0 ? 0 : 1 - Ez.inOut(seg(t, t1 - 0.1, t1 + 0.12));
  main(p, -1, kG, -(bordX(0.62) + 0.09), 0.62 + Math.sin(w * 6) * 0.04 * agite, 0, 0);
  main(p, 1, kD, 1.16 + Math.cos(wa) * 0.03 * agite, 0.2 + Math.sin(wa + 0.8) * 0.08 * agite, -0.61 + Math.sin(wa) * 0.21 * agite, 1);
  const fade = t < t0 ? 0 : 1 - Ez.inOut(seg(t, t1 - 0.13, t1 + 0.22));   // le corps se balance un peu avec le salut
  p.dx += Math.sin(w * 2 * Math.PI * 0.9) * 0.1 * fade; p.inc += Math.sin(w * 2 * Math.PI * 0.9 + 0.6) * 0.05 * fade;
}

/** Coucou commun (salut, appel connecté) : yeux plissés, petit élan, main qui s'agite, yeux contents, clignement. */
function coucou(p, t, s, perso) {
  if (t > 0.02 && t < 0.4) p.yeux = "happy";
  p.dy -= 0.04 * cloche(t, 0, 0.28);
  saluer(p, t, 0.22, 1.2);
  if (t > 1.25 && t < 1.5) p.yeux = "closed";
  regarder(p, 0, 0);
  s.ev(1.62, perso.blink);
}

function simulerParole(n) {                         // enveloppe de syllabes (parole sans son réel)
  const syllabe = Math.abs(Math.sin(n * 10.7)) * (0.55 + 0.45 * Math.sin(n * 2.3 + 1.2));
  return Math.max(0, Math.min(1, syllabe * (Math.sin(n * 0.95) > -0.8 ? 1 : 0.08)));
}

function rondRect(x, X, Y, W, H, R) { roundRectPath(x, X, Y, W, H, R); }   // chemin à coins ronds (outil du moteur)
/** Combiné téléphonique : icône « call » des Material Icons (Google, licence Apache 2.0), repère 24 × 24. */
const TRACE_TEL = new Path2D("M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z");

/** Glyphes blancs des pastilles, dessinés en vectoriel dans un disque de rayon s (centré en 0, 0).
 *  val : avancement 0..1 pour les glyphes animés (interrupteur, courbe, batterie, lignes). */
function dessinerGlyphe(x, nom, s, couleurDisque, val, t) {
  x.save();
  x.fillStyle = "#fff"; x.strokeStyle = "#fff"; x.lineCap = "round"; x.lineJoin = "round"; x.lineWidth = s * 0.16;
  const P = (v) => v * s;
  switch (nom) {
    case "points":                                   // trois points qui ondulent (comme Coucou)
      for (let i = 0; i < 3; i++) {
        const ph = (((t * 2.4 - i * 0.22) % 1) + 1) % 1;
        x.beginPath(); x.arc(P((i - 1) * 0.38), 0, P(0.11) * (1 + 0.45 * Math.max(0, Math.sin(ph * Math.PI * 2))), 0, Math.PI * 2); x.fill();
      }
      break;
    case "idee": {                                   // ampoule, qui s'allume d'un coup
      const brille = 1 + 0.12 * Math.max(0, Math.sin(Math.min(1, t / 0.35) * Math.PI));
      x.scale(brille, brille);
      x.beginPath(); x.arc(0, P(-0.12), P(0.36), Math.PI * 0.8, Math.PI * 2.2);
      x.quadraticCurveTo(P(0.16), P(0.18), P(0.15), P(0.3)); x.lineTo(P(-0.15), P(0.3));
      x.quadraticCurveTo(P(-0.16), P(0.18), Math.cos(Math.PI * 0.8) * P(0.36), P(-0.12) + Math.sin(Math.PI * 0.8) * P(0.36));
      x.closePath(); x.fill();
      x.lineWidth = P(0.11); x.beginPath(); x.moveTo(P(-0.13), P(0.46)); x.lineTo(P(0.13), P(0.46)); x.stroke();
      break; }
    case "loupe":
      x.lineWidth = P(0.15); x.beginPath(); x.arc(P(-0.08), P(-0.08), P(0.28), 0, Math.PI * 2); x.stroke();
      x.lineWidth = P(0.19); x.beginPath(); x.moveTo(P(0.14), P(0.14)); x.lineTo(P(0.4), P(0.4)); x.stroke();
      break;
    case "crayon": {                                 // crayon qui gribouille
      x.rotate(Math.PI / 4 + Math.sin(t * 14) * 0.08);
      rondRect(x, P(-0.12), P(-0.5), P(0.24), P(0.7), P(0.05)); x.fill();
      x.beginPath(); x.moveTo(P(-0.12), P(0.26)); x.lineTo(P(0.12), P(0.26)); x.lineTo(0, P(0.48)); x.closePath(); x.fill();
      x.fillStyle = couleurDisque; x.fillRect(P(-0.13), P(-0.3), P(0.26), P(0.05));
      break; }
    case "eclair":
      x.beginPath(); x.moveTo(P(0.1), P(-0.52)); x.lineTo(P(-0.28), P(0.07)); x.lineTo(P(-0.02), P(0.07));
      x.lineTo(P(-0.11), P(0.52)); x.lineTo(P(0.28), P(-0.09)); x.lineTo(P(0.02), P(-0.09)); x.closePath(); x.fill();
      break;
    case "sablier": {                                // le sable passe, puis le sablier se retourne
      const cycle = t % 2.4, k = Math.min(1, cycle / 2.0);
      x.rotate(Math.floor(t / 2.4) * Math.PI + Ez.backDoux(Math.max(0, (cycle - 2.0) / 0.4)) * Math.PI);
      x.lineWidth = P(0.12);
      x.beginPath(); x.moveTo(P(-0.3), P(-0.46)); x.lineTo(P(0.3), P(-0.46)); x.moveTo(P(-0.3), P(0.46)); x.lineTo(P(0.3), P(0.46)); x.stroke();
      x.lineWidth = P(0.08);
      x.beginPath(); x.moveTo(P(-0.22), P(-0.39)); x.lineTo(P(0.22), P(-0.39)); x.lineTo(P(0.03), 0); x.lineTo(P(0.22), P(0.39));
      x.lineTo(P(-0.22), P(0.39)); x.lineTo(P(-0.03), 0); x.closePath(); x.stroke();
      const haut = 1 - k;
      if (haut > 0.02) { x.beginPath(); x.moveTo(P(-0.22 * haut), P(-0.39 * haut)); x.lineTo(P(0.22 * haut), P(-0.39 * haut)); x.lineTo(0, 0); x.closePath(); x.fill(); }
      if (k > 0.02) { x.beginPath(); x.moveTo(P(-0.22), P(0.39)); x.lineTo(P(0.22), P(0.39)); x.lineTo(P(0.22 * (1 - k)), P(0.39 * (1 - k))); x.lineTo(P(-0.22 * (1 - k)), P(0.39 * (1 - k))); x.closePath(); x.fill(); }
      if (k > 0.02 && k < 0.98) { x.lineWidth = P(0.05); x.beginPath(); x.moveTo(0, 0); x.lineTo(0, P(0.39 * (1 - k))); x.stroke(); }
      break; }
    case "batterie": {                               // la batterie se vide (val = niveau), le dernier cran clignote
      const niv = clamp(val, 0.1, 1);
      x.lineWidth = P(0.11);
      rondRect(x, P(-0.42), P(-0.24), P(0.76), P(0.48), P(0.1)); x.stroke();
      rondRect(x, P(0.38), P(-0.1), P(0.09), P(0.2), P(0.03)); x.fill();
      if (niv > 0.15 || Math.sin(t * 9) > 0) { rondRect(x, P(-0.31), P(-0.13), P(0.54) * niv, P(0.26), P(0.04)); x.fill(); }
      break; }
    case "wifi_coupe":                               // Internet coupé : ondes Wi-Fi, barrées
      x.lineWidth = P(0.125);
      for (const r of [0.2, 0.36, 0.52]) { x.beginPath(); x.arc(0, P(0.26), P(r), -Math.PI * 0.76, -Math.PI * 0.24); x.stroke(); }
      x.beginPath(); x.arc(0, P(0.26), P(0.075), 0, Math.PI * 2); x.fill();
      x.strokeStyle = couleurDisque; x.lineWidth = P(0.24);
      x.beginPath(); x.moveTo(P(-0.38), P(-0.38)); x.lineTo(P(0.38), P(0.38)); x.stroke();
      x.strokeStyle = "#fff"; x.lineWidth = P(0.11); x.stroke();
      break;
    case "tel": {                                     // combiné (tracé « call » des Material Icons, Apache 2.0), qui sonne
      const salve = (t % 1.2) < 0.5 ? 1 : 0, k = s * 0.05;
      x.rotate(Math.sin(t * 40) * 0.14 * salve);
      x.scale(k, k); x.translate(-12, -12);
      x.fill(TRACE_TEL);
      break; }
    case "soleil":
      x.rotate(t * 0.6);
      x.beginPath(); x.arc(0, 0, P(0.2), 0, Math.PI * 2); x.fill();
      x.lineWidth = P(0.11);
      for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4; x.beginPath(); x.moveTo(Math.cos(a) * P(0.33), Math.sin(a) * P(0.33)); x.lineTo(Math.cos(a) * P(0.45), Math.sin(a) * P(0.45)); x.stroke(); }
      break;
    case "lune": {                                    // croissant (sans percer la pastille)
      const r = P(0.4), c = r * 0.45, r2 = Math.hypot(c, r);
      x.rotate(-0.35);
      x.beginPath(); x.arc(0, 0, r, -Math.PI / 2, Math.PI / 2, true);
      x.arc(c, 0, r2, Math.atan2(r, -c), Math.atan2(-r, -c) + Math.PI * 2, false); x.closePath(); x.fill();
      break; }
    case "relais":                                    // deux flèches qui tournent
      x.rotate(t * 2.4); x.lineWidth = P(0.13);
      for (const d of [0, Math.PI]) {
        x.beginPath(); x.arc(0, 0, P(0.32), d + 0.35, d + 2.55); x.stroke();
        const a = d + 2.55; x.save(); x.translate(Math.cos(a) * P(0.32), Math.sin(a) * P(0.32)); x.rotate(a + Math.PI / 2);
        x.beginPath(); x.moveTo(P(0.15), 0); x.lineTo(P(-0.06), P(-0.13)); x.lineTo(P(-0.06), P(0.13)); x.closePath(); x.fill(); x.restore();
      }
      break;
    case "courbe": {                                  // tendance qui monte, tracée progressivement (val)
      const pts = [[-0.42, 0.3], [-0.14, 0.04], [0.04, 0.16], [0.34, -0.16]];
      const lon = [0]; for (let i = 1; i < pts.length; i++) lon.push(lon[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
      const fin = lon[lon.length - 1] * clamp(val, 0, 1);
      x.lineWidth = P(0.13); x.beginPath(); x.moveTo(P(pts[0][0]), P(pts[0][1]));
      let bout = pts[0];
      for (let i = 1; i < pts.length; i++) {
        if (lon[i] <= fin) { x.lineTo(P(pts[i][0]), P(pts[i][1])); bout = pts[i]; continue; }
        const k = (fin - lon[i - 1]) / (lon[i] - lon[i - 1]);
        bout = [lerp(pts[i - 1][0], pts[i][0], k), lerp(pts[i - 1][1], pts[i][1], k)]; x.lineTo(P(bout[0]), P(bout[1])); break;
      }
      x.stroke();
      if (val >= 0.98) { x.beginPath(); x.moveTo(P(0.46), P(-0.28)); x.lineTo(P(0.17), P(-0.25)); x.lineTo(P(0.39), P(-0.04)); x.closePath(); x.fill(); }
      else { x.beginPath(); x.arc(P(bout[0]), P(bout[1]), P(0.1), 0, Math.PI * 2); x.fill(); }
      break; }
    case "micro":
      rondRect(x, P(-0.14), P(-0.48), P(0.28), P(0.54), P(0.14)); x.fill();
      x.lineWidth = P(0.1); x.beginPath(); x.arc(0, P(-0.08), P(0.29), 0.15, Math.PI - 0.15); x.stroke();
      x.beginPath(); x.moveTo(0, P(0.21)); x.lineTo(0, P(0.42)); x.stroke();
      break;
    case "oeil": {                                    // œil qui cligne de temps en temps
      const cl = (t % 3) > 2.85 ? 0.15 : 1;
      x.scale(1, cl);
      x.beginPath(); x.moveTo(P(-0.46), 0); x.quadraticCurveTo(0, P(-0.46), P(0.46), 0); x.quadraticCurveTo(0, P(0.46), P(-0.46), 0); x.fill();
      x.fillStyle = couleurDisque; x.beginPath(); x.arc(0, 0, P(0.16), 0, Math.PI * 2); x.fill();
      break; }
    case "interrupteur": {                            // val : 1 = allumé (bouton à droite), 0 = éteint
      x.lineWidth = P(0.1);
      rondRect(x, P(-0.42), P(-0.22), P(0.84), P(0.44), P(0.22)); x.stroke();
      x.beginPath(); x.arc(lerp(P(-0.2), P(0.2), clamp(val, 0, 1)), 0, P(0.14), 0, Math.PI * 2); x.fill();
      break; }
    case "plus":
      x.lineWidth = P(0.17); x.beginPath(); x.moveTo(P(-0.3), 0); x.lineTo(P(0.3), 0); x.moveTo(0, P(-0.3)); x.lineTo(0, P(0.3)); x.stroke();
      break;
    case "croix":
      x.lineWidth = P(0.17); x.beginPath(); x.moveTo(P(-0.24), P(-0.24)); x.lineTo(P(0.24), P(0.24)); x.moveTo(P(0.24), P(-0.24)); x.lineTo(P(-0.24), P(0.24)); x.stroke();
      break;
    case "coche": {                                   // coche qui se trace (val)
      const k = clamp(val, 0, 1);
      x.lineWidth = P(0.17); x.beginPath(); x.moveTo(P(-0.28), P(0.02));
      if (k < 0.4) x.lineTo(P(lerp(-0.28, -0.08, k / 0.4)), P(lerp(0.02, 0.22, k / 0.4)));
      else { x.lineTo(P(-0.08), P(0.22)); x.lineTo(P(lerp(-0.08, 0.3, (k - 0.4) / 0.6)), P(lerp(0.22, -0.2, (k - 0.4) / 0.6))); }
      x.stroke();
      break; }
    case "lignes": {                                  // trois lignes de texte qui s'écrivent l'une après l'autre (val)
      x.lineWidth = P(0.12);
      const L = [0.64, 0.64, 0.4];
      for (let i = 0; i < 3; i++) {
        const k = clamp(val * 3 - i, 0, 1); if (k <= 0) continue;
        const y0 = P(-0.24 + i * 0.24), x0 = P(-0.32);
        x.beginPath(); x.moveTo(x0, y0); x.lineTo(x0 + P(L[i]) * k, y0); x.stroke();
      }
      break; }
    case "globe":                                     // langue : globe dont le méridien tourne
      x.lineWidth = P(0.1);
      x.beginPath(); x.arc(0, 0, P(0.4), 0, Math.PI * 2); x.stroke();
      x.beginPath(); x.ellipse(0, 0, Math.max(P(0.02), P(0.4) * Math.abs(Math.cos(t * 2.2))), P(0.4), 0, 0, Math.PI * 2); x.stroke();
      x.beginPath(); x.moveTo(P(-0.4), 0); x.lineTo(P(0.4), 0); x.stroke();
      break;
    case "question":
      x.font = `900 ${P(1.3)}px ${FONT}`; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText("?", 0, P(0.07));
      break;
    case "franc":                                     // « F » du franc CFA
      x.font = `800 ${P(0.95)}px ${FONT}`; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText("F", 0, P(0.06));
      break;
  }
  x.restore();
}

class PersonnageAoceda extends BotEngine {
  constructor() {
    super();
    this.oreilles = true;
    this.teinteCorps = false;                              // palette AOCEDA : halo au lieu de teinter le corps doré
    this.oG = 0; this.oD = 0; this.oL = 1;                 // oreilles dessinées (pose + ressort)
    this.ore = { g: { a: 0, v: 0 }, d: { a: 0, v: 0 }, l: { a: 1, v: 0 } };
    this.mvt = { y: 0, vy: 0, ay: 0, ti: 0, vti: 0, ati: 0, ya: 0, vya: 0, aya: 0, pret: false };
    this.pose = { ...REPOS, yeux: null };
    this.ecart = null; this.tEcart = 0;                    // reste de la pose précédente, qui s'efface (aucune coupure)
    this.seq = null;                                       // chorégraphie en cours
    this.bouche = 0; this.parole = null; this.paroleFin = 0;
    this.batt = { t: -9, force: 0, cote: 1, arme: true, g: -9, d: -9, sortieG: 0, sortieD: 0 };
    this.souris = { x: 0, y: 0, t: -9 }; this.flane = { x: 0, y: 0, prochain: 0 };
    this.pastille = null; this.pastilleS = 0;
    this.parts2 = []; this.attentes = [];
    this.prochainTic = now() + 3;
  }

  // ── chorégraphies ──────────────────────────────────────────────────────────────────────────────────────
  /** Joue une action du chatbot (voir ACTIONS_AOCEDA). La pose en cours se fond dans la nouvelle. */
  jouer(nom, o = {}) {
    const action = ACTIONS_AOCEDA[nom];
    if (!action) return false;
    if (this.state !== "idle") this.setState("idle");   // état du moteur d'origine (boutons « Coucou »)
    if (this.hands > 0.01) this.interruptGreet();
    this.setPermanentEmote(null);
    this.parole = null; this.paroleFin = 0;
    if (!action.gardePastille) this.cacherPastille();
    const duree = typeof action.duree === "function" ? action.duree(o) : action.duree ?? Infinity;
    this.lancer(nom, action.f, duree, action.apparition ? { ...o, sansFondu: true } : o);
    if (action.debut) action.debut.call(this, o);
    return true;
  }
  /** Revient au repos en douceur. */
  repos() { this.parole = null; this.paroleFin = 0; this.cacherPastille(); this.lancer("repos", () => {}, 0, {}); }
  lancer(nom, f, duree, o) {
    const n = now(), s = { nom, f, duree, o, t0: n, t: 0, faits: new Set(), dernier: {}, i: 0, nettoyer: !!this.eyeOverride };
    s.ev = (at, fn) => { const c = s.i++; if (!s.faits.has(c) && s.t >= at) { s.faits.add(c); fn.call(this); } };
    s.tous = (periode, decalage, fn) => {                // événement périodique (boucles sans fin)
      const c = s.i++, k = Math.floor((s.t - decalage) / periode);
      if (k >= 0 && k > (s.dernier[c] ?? -1)) { s.dernier[c] = k; fn.call(this, k); }
    };
    // la nouvelle chorégraphie part de sa pose à t = 0 ; l'écart avec la pose actuelle GARDE SA VITESSE et s'amortit
    // (inertialisation) : un geste coupé en plein élan se termine naturellement au lieu de se figer
    // (sauf une apparition : elle part de rien, par définition)
    if (o.sansFondu) this.ecart = null;
    else {
      const p0 = { ...REPOS, yeux: null }, essai = { ...s, ev() {}, tous() {} }, base = this.poseBase || this.pose;
      f.call(this, 0, p0, essai, o);
      this.ecart = this.ecartDepuis(base, p0, this.poseBasePrec, this.dtPose || 1 / 60);
    }
    if (s.nettoyer) this.blink();                         // l'expression d'avant change sous un clignement
    this.seq = s;
  }
  /** Remise à zéro immédiate (banc d'essai). */
  reinitialiser() {
    this.seq = null; this.ecart = null; this.pose = { ...REPOS, yeux: null }; this.poseBase = { ...REPOS };
    this.pastille = null; this.pastilleS = 0; this.parts2 = []; this.particles = []; this.attentes = [];
    this.parole = null; this.paroleFin = 0; this.bouche = 0;
    this.batt = { t: -9, force: 0, cote: 1, arme: true, g: -9, d: -9, sortieG: 0, sortieD: 0 };
    this.ore = { g: { a: 0, v: 0 }, d: { a: 0, v: 0 }, l: { a: 1, v: 0 } }; this.mvt.pret = false;
    this.poseBasePrec = null;
    for (const p of [...this.tweens.keys()]) { this.tweens.delete(p); this.locks.delete(p); }
    this.eyeOverride = null; this.eyeOverrideUntil = 0; this.permanentEye = null;
    this.ox = 0; this.oy = 0; this.sx = 1; this.sy = 1; this.tilt = 0; this.roll = 0; this.open = 1; this.blush = 0;
    this.hands = 0; this.waveUntil = 0;
    this.setState("idle", true); this.setBadge(null);
  }
  /** Parole : niveau() = 0..1 (vraie voix) ou parole simulée pendant `secondes`. */
  dire(secondes) { if (!this.parole) this.paroleFin = now() + secondes; }
  /** Appel différé sur l'horloge du personnage (suit le ralenti et le banc d'essai, contrairement à setTimeout). */
  plusTard(secondes, fn) { this.attentes.push({ t: now() + secondes, fn }); }
  finParole() { this.parole = null; this.paroleFin = 0; }
  regarderSouris(x, y) { this.souris = { x, y, t: now() }; }

  // ── pastille AOCEDA (une seule à la fois, apparition « pop » comme les badges de Coucou) ──────────────
  montrerPastille(glyphe, couleur, val = 1) {
    super.setBadge(null);
    const nouvelle = { glyphe, couleur, val, debut: now() };
    if (this.pastille && this.pastilleS > 0.05) {          // l'ancienne rentre, puis la nouvelle sort
      this.anim("pastilleS", [[0, 110, Ease.easeIn]], () => {
        nouvelle.debut = now(); this.pastille = nouvelle; this.anim("pastilleS", [[1, 300, Ease.back]]);
      });
    } else { this.pastille = nouvelle; this.pastilleS = 0; this.anim("pastilleS", [[1, 300, Ease.back]]); }
  }
  cacherPastille() {
    if (!this.pastille) return;
    const p = this.pastille;
    this.anim("pastilleS", [[Math.max(this.pastilleS, 1.06), 70, Ease.out], [0, 150, Ease.easeIn]], () => { if (this.pastille === p) this.pastille = null; });
  }
  pulserPastille() { if (this.pastille) this.anim("pastilleS", [[1.2, 90, Ease.out], [1, 240, Ease.back]]); }
  /** Appui sur la pastille : elle s'enfonce puis rebondit, comme un vrai bouton. */
  presserPastille() { if (this.pastille) this.anim("pastilleS", [[0.84, 70, Ease.out], [1.08, 160, Ease.out], [1, 140, Ease.inOut]]); }
  setBadge(b) { if (!this.pastille) super.setBadge(b); }   // la pastille AOCEDA a la priorité

  // ── particules (positions en R depuis le centre du corps, y vers le bas) ─────────────────────────────
  emettre(type, o = {}) {
    this.parts2.push({ type, age: -(o.retard ?? 0), vie: o.vie ?? 1.2, x: o.x ?? 0, y: o.y ?? -1, vx: o.vx ?? 0, vy: o.vy ?? -0.4,
      g: o.g ?? 0, rot: o.rot ?? Math.random() * 6.28, vr: o.vr ?? (Math.random() - 0.5) * 6, taille: o.taille ?? 0.1,
      couleur: o.couleur ?? AO.or, cote: o.cote ?? 1 });
  }
  /** Bout d'une oreille, en R depuis le centre du corps (pour la vapeur de la colère). */
  boutOreille(sd) {
    const rot = sd * (0.14 + (sd < 0 ? this.oG : this.oD)), L = 0.92 * this.oL;
    return { x: sd * 0.37 * 1.14 + Math.sin(rot) * L, y: -0.6 * 0.88 - Math.cos(rot) * L };
  }
  /** Œil (sd = -1 gauche, 1 droit), en R depuis le centre du corps (pour la larme). */
  posOeil(sd) {
    const p = this.pose, yaw = sd * EYE_SP + this.yaw + p.tourne, pit = EYE_P + this.pitch + p.hoche;
    return { x: Math.sin(yaw) * Math.cos(pit) * 1.14 * this.sx * p.sx, y: -Math.sin(pit) * 0.88 * this.sy * p.sy };
  }

  // ── mise à jour ────────────────────────────────────────────────────────────────────────────────────────
  update(dt) {
    const n = now();
    this.calculerPose(n);
    const p = this.pose, libre = this.regardLibre(n);
    // le moteur compte lookY vers le HAUT ; regard imposé borné pour garder les deux yeux sur le visage
    this.lookX = lerp(libre.x, clamp(p.regX, -0.72, 0.72), p.regW);
    this.lookY = -lerp(libre.y, clamp(p.regY, -0.65, 0.65), p.regW);
    if (p.yeux) { this.eyeOverride = p.yeux; this.eyeOverrideUntil = n + 0.06; }
    super.update(dt);
    if (dt > 1e-4) { this.mettreAJourParole(n, dt); this.mettreAJourOreilles(n, dt); }
    for (const q of this.parts2) q.age += dt;
    this.parts2 = this.parts2.filter((q) => q.age < q.vie);
    if (this.attentes.length) {
      const pretes = this.attentes.filter((a) => n >= a.t);
      this.attentes = this.attentes.filter((a) => n < a.t);
      for (const a of pretes) a.fn.call(this);
    }
  }

  /** Écart (position + vitesse) entre la pose affichée et la pose de départ de la suite, par canal. */
  ecartDepuis(base, cible, prec, dt) {
    const e = {};
    for (const c of CHAMPS) e[c] = { r: base[c] - cible[c], w: prec ? clamp((base[c] - prec[c]) / dt, -40, 40) : 0 };
    return e;
  }

  calculerPose(n) {
    const dt = clamp(n - (this.nPose ?? n), 0, 0.05); this.nPose = n;
    const p = { ...REPOS, yeux: null };
    const s = this.seq;
    if (s) {
      s.t = n - s.t0; s.i = 0;
      if (s.nettoyer && s.t >= 0.07) { this.eyeOverride = this.permanentEye; s.nettoyer = false; }
      s.f.call(this, s.t, p, s, s.o);
    }
    if (this.ecart) {                                     // reste de la pose précédente : ressort critique (≈ 0,3 s)
      const om = 2 * Math.PI / 0.36, pas = Math.max(1, Math.ceil(dt / (1 / 240))), h = dt / pas;
      let actif = false;
      for (const c of CHAMPS) {
        const e = this.ecart[c];
        for (let i = 0; i < pas; i++) { e.w += (-om * om * e.r - 2 * om * e.w) * h; e.r += e.w * h; }
        p[c] += e.r;
        if (Math.abs(e.r) > 1e-4 || Math.abs(e.w) > 1e-3) actif = true;
      }
      if (!actif) this.ecart = null;
    }
    if (s && s.t >= s.duree) {                            // fin : la pose COMPLÈTE actuelle rejoint le repos en douceur
      this.seq = null; this.ecart = this.ecartDepuis(p, REPOS, this.poseBase, dt || 1 / 60);
    }
    this.poseBasePrec = this.poseBase; this.dtPose = dt || 1 / 60;
    this.poseBase = { ...p };                             // sans respiration ni parole (ajoutées à chaque image)
    // respiration d'ambiance (0,99-1,01 sur 3,4 s), sauf quand une chorégraphie gère déjà le souffle
    if (!s || !s.f.souffle) { const b = Math.sin(n * 2 * Math.PI / 3.4); p.sy *= 1 + 0.011 * b; p.sx *= 1 - 0.006 * b; }
    this.appliquerParole(p, n);
    this.pose = p;
  }

  /** Regard libre : la souris si elle a bougé il y a peu, sinon il « flâne » (fixations, souvent vers vous). */
  regardLibre(n) {
    if (n - this.souris.t < 2.5) return this.souris;
    const f = this.flane;
    if (n > f.prochain) {
      const r = Math.random();
      if (r < 0.4) { f.x = 0; f.y = 0; } else { f.x = (Math.random() - 0.5) * 0.7; f.y = (Math.random() - 0.5) * 0.4; }
      f.prochain = n + 1.4 + Math.random() * 2.6;
    }
    return f;
  }

  /** Bouche sur le niveau de la voix, et battements sur les syllabes accentuées (la tête hoche un peu AVANT). */
  mettreAJourParole(n, dt) {
    let niveau = 0;
    if (this.parole) niveau = this.parole();
    else if (n < this.paroleFin) niveau = simulerParole(n);
    // ouvre en ~40 ms, referme en ~90 ms : la bouche se ferme bien entre deux syllabes (sinon elle reste entrouverte)
    const k = 1 - Math.exp(-dt / (niveau > this.bouche ? 0.04 : 0.09));
    this.bouche += (niveau - this.bouche) * k;
    const b = this.batt;
    if (niveau < 0.25) b.arme = true;
    else if (b.arme && niveau >= 0.42 && n - b.t > 0.24) {
      b.arme = false; b.t = n; b.force = Math.min(1, 0.55 + niveau * 0.6); b.cote = -b.cote;
      if (b.cote > 0) b.d = n; else b.g = n;
    }
    // sortie des mains lissée : une main déjà sortie le reste (pas de clignotement d'un battement à l'autre)
    for (const [cle, dernier] of [["sortieG", b.g], ["sortieD", b.d]]) {
      const cible = n - dernier < 1.1 ? 1 : 0;
      b[cle] += (cible - b[cle]) * (1 - Math.exp(-dt / (cible > b[cle] ? 0.06 : 0.12)));
    }
  }
  appliquerParole(p, n) {
    const b = this.batt, u = n - b.t;
    if (u >= 0 && u < 0.42) {                             // attaque 80 ms, retour 260 ms
      const v = (u < 0.08 ? Ez.out(u / 0.08) : 1 - Ez.inOut(seg(u, 0.08, 0.34))) * b.force;
      p.hoche -= 0.07 * v; p.dy += 0.01 * v; p.inc += 0.022 * b.cote * v;
    }
    if (p.gesteParole > 0.01) {                           // mains : sortent au 1er battement, se relèvent à chaque
      for (const cote of [-1, 1]) {                       // battement, retombent le long du corps, rentrent après 1,1 s
        const v = n - (cote > 0 ? b.d : b.g), sortie = cote > 0 ? b.sortieD : b.sortieG;
        if (sortie < 0.01) continue;
        const lev = v < 0 || v > 0.5 ? 0 : v < 0.1 ? Ez.out(v / 0.1) : 1 - Ez.inOut(seg(v, 0.1, 0.46));
        const c = cote < 0 ? "mg" : "md", k = p.gesteParole * sortie;
        if (k > p[c + "K"]) pointerVers(p, cote, lerp(0.7, -0.2, lev * b.force), k, 0, 0.45);
      }
    }
  }

  /** Oreilles sur ressort : elles suivent la pose, avec du retard et un rebond quand le corps bouge. */
  mettreAJourOreilles(n, dt) {
    const p = this.pose, m = this.mvt;
    const y = this.oy + p.dy, ti = this.tilt + p.inc, ya = this.yaw + p.tourne;
    if (!m.pret) { Object.assign(m, { y, vy: 0, ay: 0, ti, vti: 0, ati: 0, ya, vya: 0, aya: 0, pret: true }); }
    const lisse = 1 - Math.exp(-dt / 0.03);
    const vy = (y - m.y) / dt, vti = (ti - m.ti) / dt, vya = (ya - m.ya) / dt;
    m.ay += ((vy - m.vy) / dt - m.ay) * lisse; m.ati += ((vti - m.vti) / dt - m.ati) * lisse; m.aya += ((vya - m.vya) / dt - m.aya) * lisse;
    Object.assign(m, { y, vy, ti, vti, ya, vya });
    if (this.oreilles && n > this.prochainTic && this.state !== "sleeping" && (!this.seq || this.seq.duree === Infinity)) {
      (Math.random() < 0.5 ? this.ore.g : this.ore.d).v += (Math.random() < 0.5 ? -1 : 1) * 3.2;   // frémissement
      this.prochainTic = n + 3.5 + Math.random() * 4;
    }
    const om = 2 * Math.PI / 0.34, z = 0.34, pas = Math.max(1, Math.ceil(dt / (1 / 240))), h = dt / pas;
    for (const [sd, o, cible] of [[-1, this.ore.g, p.oG], [1, this.ore.d, p.oD]]) {
      const force = clamp(-m.ay * 0.018 - sd * m.ati * 0.0035 - sd * m.aya * 0.0015, -0.45, 0.5);
      for (let i = 0; i < pas; i++) { o.v += (om * om * (cible + force - o.a) - 2 * z * om * o.v) * h; o.a += o.v * h; }
      if (o.a < -0.24) { o.a = -0.24; o.v = Math.max(0, o.v); }   // vers l'intérieur : elles ne se croisent jamais
      if (o.a > 1.25) { o.a = 1.25; o.v = Math.min(0, o.v); }
    }
    const l = this.ore.l, oml = 2 * Math.PI / 0.3;
    for (let i = 0; i < pas; i++) { l.v += (oml * oml * (p.oL - l.a) - 2 * 0.45 * oml * l.v) * h; l.a += l.v * h; }
    this.oG = this.ore.g.a; this.oD = this.ore.d.a; this.oL = l.a;
  }

  // ── dessin ─────────────────────────────────────────────────────────────────────────────────────────────
  geo(W, H) {
    const R = W * 0.3, rx = R * 1.14, ry = R * 0.88;
    return { R, rx, ry, cx: W / 2 + this.ox * R, cy: H / 2 + this.particleOverhang / 2 + this.oy * R + R * 0.06 };
  }
  corps(x, g) { x.translate(g.cx, g.cy); if (this.tilt) x.rotate(this.tilt); x.scale(this.sx, this.sy); }

  draw(x, W, H) {
    const p = this.pose;
    const sauve = { ox: this.ox, oy: this.oy, sx: this.sx, sy: this.sy, tilt: this.tilt, pitch: this.pitch, yaw: this.yaw,
      roll: this.roll, es: this.es, open: this.open, blush: this.blush, tint: this.tint, col: this.col };
    this.ox += p.dx; this.oy += p.dy; this.sx *= p.sx; this.sy *= p.sy; this.tilt += p.inc; this.pitch += p.hoche;
    this.yaw += p.tourne; this.roll += p.roule; this.es *= p.es; this.open *= p.ouv; this.blush = Math.max(this.blush, p.rougit);
    const g = this.geo(W, H);
    x.save();
    x.globalAlpha *= clamp(p.alpha, 0, 1);
    if (p.echelle !== 1) { x.translate(g.cx, g.cy); x.scale(p.echelle, p.echelle); x.translate(-g.cx, -g.cy); }
    if (this.teinteCorps) {                               // couleurs d'origine : l'état teinte le corps, comme Coucou
      if (p.halo > this.tint) { this.tint = p.halo * 0.75; this.col = [p.hR, p.hG, p.hB]; }
    } else { this.dessinerHalo(x, g); this.tint = 0; }
    if (this.oreilles) this.dessinerOreilles(x, g);
    this.dessinerMains(x, g);
    super.draw(x, W, H);
    this.dessinerBouche(x, g);
    this.dessinerPastille(x, g);
    this.dessinerParticules2(x, g);
    x.restore();
    Object.assign(this, sauve);
  }

  dessinerHalo(x, g) {
    const p = this.pose, moteur = this.tint * (1 - this.morph);
    const force = Math.max(p.halo, moteur) * (1 - this.morph);
    if (force < 0.02) return;
    const c = p.halo >= moteur ? [p.hR, p.hG, p.hB] : this.col;
    const { R, cx, cy } = g;
    const h = x.createRadialGradient(cx, cy + R * 0.08, R * 0.6, cx, cy + R * 0.08, R * 1.75);
    h.addColorStop(0, rgba(c, 0.3 * force)); h.addColorStop(0.55, rgba(c, 0.12 * force)); h.addColorStop(1, rgba(c, 0));
    x.fillStyle = h; x.beginPath(); x.arc(cx, cy + R * 0.08, R * 1.75, 0, Math.PI * 2); x.fill();
  }

  drawBadge(x, badge, R, cx, cy) {                     // pastille du moteur décalée : les oreilles occupent le haut
    super.drawBadge(x, badge, R, cx - (this.oreilles ? R * 0.2 * this.sx : 0), cy + (this.oreilles ? R * 0.16 * this.sy : 0));
  }

  dessinerOreilles(x, g) {
    if (this.morph > 0.3) return;
    const { R, rx, ry } = g;
    x.save(); this.corps(x, g);
    const decalage = Math.sin(this.yaw) * rx * 0.2;
    for (const sd of [-1, 1]) {
      const L = R * 0.92 * this.oL, l = R * 0.34;
      x.save();
      x.translate(sd * rx * 0.37 + decalage, -ry * 0.6);
      x.rotate(sd * (0.14 + (sd < 0 ? this.oG : this.oD)));
      const p = new Path2D();
      p.moveTo(-l * 0.34, 0);
      p.bezierCurveTo(-l * 0.62, -L * 0.42, -l * 0.46, -L, 0, -L);
      p.bezierCurveTo(l * 0.46, -L, l * 0.62, -L * 0.42, l * 0.34, 0);
      p.closePath();
      const d = x.createLinearGradient(0, -L, 0, 0);
      d.addColorStop(0, rgba(BASE_TOP)); d.addColorStop(1, rgba(mix3(BASE_TOP, BASE_BOTTOM, 0.55)));
      x.fillStyle = d; x.fill(p);
      x.strokeStyle = "rgba(0,0,0,0.06)"; x.lineWidth = 1; x.stroke(p);
      const q = new Path2D();                         // creux de l'oreille, à peine rosé
      q.moveTo(-l * 0.12, -L * 0.16);
      q.bezierCurveTo(-l * 0.3, -L * 0.48, -l * 0.2, -L * 0.84, 0, -L * 0.86);
      q.bezierCurveTo(l * 0.2, -L * 0.84, l * 0.3, -L * 0.48, l * 0.12, -L * 0.16);
      q.closePath();
      x.fillStyle = "rgba(255,150,170,0.26)"; x.fill(q);
      const hl = x.createRadialGradient(-l * 0.12, -L * 0.8, 0, -l * 0.12, -L * 0.8, l * 0.5);   // reflet doux
      hl.addColorStop(0, "rgba(255,255,255,0.5)"); hl.addColorStop(1, "rgba(255,255,255,0)");
      x.fillStyle = hl; x.fill(p);
      x.restore();
    }
    x.restore();
  }

  /** Mains DERRIÈRE le corps, dans son repère (elles penchent et s'écrasent avec lui), comme la référence :
   *  k = 0 : cachée sous le corps ; k = 1 : sortie. L : 0 = boule (main posée), 1 = capsule (geste). */
  dessinerMains(x, g) {
    const p = this.pose;
    if (p.mgK < 0.01 && p.mdK < 0.01) return;
    x.save(); this.corps(x, g);
    for (const [c, sd] of [["mg", -1], ["md", 1]]) {
      const k = p[c + "K"];
      if (k < 0.01) continue;
      const kp = Math.min(1, k), L = clamp(p[c + "L"], 0, 1);
      const X = lerp(sd * 0.32, p[c + "X"], kp) * g.rx, Y = lerp(0.86, p[c + "Y"], kp) * g.ry;
      const lw = lerp(0.6, 0.8, L) * g.ry * k, lh = lerp(0.54, 0.44, L) * g.ry * k;
      x.save(); x.translate(X, Y); x.rotate(p[c + "A"]);
      const d = x.createLinearGradient(lw * 0.35, -lh * 0.5, -lw * 0.4, lh * 0.5);
      d.addColorStop(0, rgba(BASE_TOP)); d.addColorStop(1, rgba(BASE_BOTTOM));
      rondRect(x, -lw / 2, -lh / 2, lw, lh, lh / 2);
      x.fillStyle = d; x.fill(); x.strokeStyle = "rgba(0,0,0,0.08)"; x.lineWidth = 1; x.stroke();
      x.restore();
    }
    x.restore();
  }

  /** Bouche minimale, seulement quand il parle (ou bâille, ou fait « oh ») : demi-ovale, plus rond si p.rond. */
  dessinerBouche(x, g) {
    const p = this.pose, ouv = Math.max(this.bouche, p.bouche);
    if (ouv < 0.03 || this.morph > 0.3) return;
    const { R, rx, ry } = g;
    const tangage = EYE_P + this.pitch + this.roll - 0.42, cp = Math.cos(tangage);
    if (Math.cos(this.yaw) * cp < 0.15) return;
    x.save(); this.corps(x, g);
    x.translate(Math.sin(this.yaw) * cp * rx, -Math.sin(tangage) * ry);
    x.scale(Math.max(0.35, Math.cos(this.yaw)), Math.max(0.35, cp));
    // grande ouverture ronde (bâillement) : elle s'élargit aussi, sinon on obtient une fente verticale
    const w = R * (0.15 + 0.07 * ouv) * (1 - 0.35 * p.rond) + R * 0.06 * p.rond * Math.max(0, ouv - 0.6), h = R * (0.05 + 0.15 * ouv), haut = -h * 0.35;
    const chemin = new Path2D();
    chemin.moveTo(-w / 2, haut);
    if (p.rond > 0.01) chemin.ellipse(0, haut, w / 2, h * 0.75 * p.rond, 0, Math.PI, Math.PI * 2);
    else chemin.lineTo(w / 2, haut);
    chemin.ellipse(0, haut, w / 2, h, 0, 0, Math.PI); chemin.closePath();
    x.fillStyle = INK; x.strokeStyle = INK; x.lineJoin = "round"; x.lineWidth = R * 0.03;
    x.fill(chemin); x.stroke(chemin);                    // le trait arrondit les coins
    if (ouv > 0.35) {                                    // un peu de langue quand elle s'ouvre grand
      x.clip(chemin);
      x.fillStyle = "rgba(255,130,155,0.95)";
      x.beginPath(); x.ellipse(0, haut + h * 0.95, w * 0.3, h * 0.42, 0, 0, Math.PI * 2); x.fill();
    }
    x.restore();
  }

  dessinerPastille(x, g) {
    if (!this.pastille || this.pastilleS < 0.01 || this.morph > 0.25) return;
    const { R, cx, cy } = g;
    const bx = cx - R * (this.oreilles ? 0.92 : 0.72) * this.sx, by = cy - R * (this.oreilles ? 0.56 : 0.72) * this.sy;
    x.save(); x.translate(bx, by); x.scale(this.pastilleS, this.pastilleS);
    x.fillStyle = "#000"; x.beginPath(); x.arc(0, 0, R * 0.3, 0, Math.PI * 2); x.fill();
    x.fillStyle = this.pastille.couleur; x.beginPath(); x.arc(0, 0, R * 0.235, 0, Math.PI * 2); x.fill();
    dessinerGlyphe(x, this.pastille.glyphe, R * 0.235, this.pastille.couleur, this.pastille.val, now() - this.pastille.debut);
    x.restore();
  }

  dessinerParticules2(x, g) {
    const { R, cx, cy } = g;
    for (const q of this.parts2) {
      if (q.age <= 0) continue;
      const k = q.age / q.vie, a = k < 0.1 ? k / 0.1 : k > 0.7 ? 1 - (k - 0.7) / 0.3 : 1;
      const px = cx + (q.x + q.vx * q.age) * R, py = cy + (q.y + q.vy * q.age + 0.5 * q.g * q.age * q.age) * R;
      const sz = R * q.taille;
      x.save(); x.translate(px, py); x.globalAlpha *= clamp(a, 0, 1);
      switch (q.type) {
        case "piece": {                                  // petite pièce dorée qui tourne sur elle-même
          x.scale(Math.abs(Math.cos(q.age * 7 + q.rot)) * 0.85 + 0.15, 1);
          const d = x.createLinearGradient(0, -sz, 0, sz); d.addColorStop(0, "#ffe27a"); d.addColorStop(1, "#e0a400");
          x.fillStyle = d; x.beginPath(); x.arc(0, 0, sz, 0, Math.PI * 2); x.fill();
          x.strokeStyle = "#b07800"; x.lineWidth = sz * 0.16; x.stroke();          // liseré foncé : lisible sur le corps doré
          x.strokeStyle = "rgba(255,255,255,0.75)"; x.lineWidth = sz * 0.14; x.beginPath(); x.arc(0, 0, sz * 0.58, 0, Math.PI * 2); x.stroke();
          break; }
        case "confetti":
          x.translate(Math.sin(q.age * 9 + q.rot) * sz * 0.6, 0);
          x.rotate(q.rot + q.vr * q.age); x.scale(1, Math.abs(Math.cos(q.age * 6 + q.rot)) * 0.8 + 0.2);
          x.fillStyle = q.couleur; rondRect(x, -sz * 0.5, -sz * 0.22, sz, sz * 0.44, sz * 0.2); x.fill();
          break;
        case "larme":
          x.fillStyle = "#7CC7FF"; x.beginPath(); x.moveTo(0, -sz); x.quadraticCurveTo(sz * 0.8, sz * 0.2, 0, sz * 0.6);
          x.quadraticCurveTo(-sz * 0.8, sz * 0.2, 0, -sz); x.fill(); break;
        case "bouffee": {                                // vapeur : boule douce qui gonfle et s'efface
          const r = sz * (0.6 + 1.4 * k);
          const d = x.createRadialGradient(0, 0, 0, 0, 0, r); d.addColorStop(0, "rgba(176,183,194,0.9)"); d.addColorStop(0.55, "rgba(196,202,211,0.55)"); d.addColorStop(1, "rgba(210,215,222,0)");   // gris vapeur : visible sur fond clair comme sombre
          x.fillStyle = d; x.beginPath(); x.arc(0, 0, r, 0, Math.PI * 2); x.fill(); break; }
        case "onde": {                                   // onde sonore qui arrive vers l'oreille : double arc « )) » ou « (( »
          x.strokeStyle = rgba(hexToRGB(AO.bleu), 0.75); x.lineCap = "round";
          for (let j = 0; j < 2; j++) {
            const r = R * (0.16 + 0.07 * j) * (0.8 + 0.4 * k), dx = -q.cote * j * R * 0.07;
            x.lineWidth = R * (0.034 - 0.01 * j); x.beginPath();
            if (q.cote < 0) x.arc(dx - r, 0, r, -0.55, 0.55); else x.arc(dx + r, 0, r, Math.PI - 0.55, Math.PI + 0.55);
            x.stroke();
          }
          break; }
      }
      x.restore();
    }
  }
}

/** Les actions du chatbot AOCEDA : nom -> {groupe, titre, duree (s, Infinity = tant que dure l'état), debut?, f}.
 *  f(t, p, s, o) écrit la pose p à l'instant t ; s.ev(t, fn) = événement unique, s.tous(période, départ, fn). */
const ACTIONS_AOCEDA = {
  // ── conversation écrite ────────────────────────────────────────────────────────────────────────────────
  accueil: { groupe: "Conversation écrite", titre: "Ouverture du chatbot", duree: 3.9, apparition: true, f(t, p, s) {
    // Il sort de DERRIÈRE le titre (demande du client, 05/10/2026) : sur l'accueil, la page masque tout ce qui passe
    // sous le haut des lettres du titre (« horizon ») jusqu'à 2,1 s. dy en rayons du corps ; au repos, l'horizon est
    // à 2,15 R sous son centre (1,73 R jusqu'au bas de son cadre + 0,42 R jusqu'aux lettres) : 4,0 = tout caché
    // (oreilles comprises), 1,78 = seuls les oreilles, le haut de la tête et les yeux dépassent.
    p.alpha = Ez.out(seg(t, 0, 0.2));                   // ailleurs (galerie, sans horizon) : il apparaît en douceur
    // 1. il monte jusqu'à montrer le haut de sa tête ; 2. il guette ; 3. tassement, bond au-dessus de sa place, chute
    p.dy += kf(t, [[0, 4.0], [0.62, 1.78, Ez.out], [1.3, 1.78], [1.44, 1.94, Ez.inOut], [1.78, -0.32, Ez.out],
                   [1.98, 0, Ez.easeIn], [2.2, 0]]);
    // étiré en montant ; tassé avant le bond, étiré à la détente, rond en l'air, écrasé à l'arrivée, rebond (volume gardé)
    const sq = kf(t, [[0, 1], [0.25, 1.06, Ez.out], [0.62, 1, Ez.inOut], [1.3, 1], [1.44, 0.88, Ez.inOut],
                      [1.58, 1.12, Ez.out], [1.78, 1, Ez.inOut], [1.98, 0.86, Ez.easeIn], [2.26, 1, Ez.back]]);
    p.sy *= sq; p.sx *= 1 + (1 - sq) * 0.8;
    // 2. il guette : regard à gauche puis à droite (il cherche quelqu'un), oreilles qui frémissent, un clignement
    if (t >= 0.62 && t < 1.3) regarder(p, kf(t, [[0.62, 0], [0.74, -0.65, Ez.inOut], [0.96, -0.65], [1.08, 0.65, Ez.inOut],
                                                  [1.22, 0.65], [1.3, 0, Ez.inOut]]), -0.12);
    p.oL += 0.07 * cloche(t, 0.62, 0.86) + 0.05 * cloche(t, 1.04, 1.24);
    s.ev(0.98, this.blink);
    // 3. il vous a trouvé : yeux plissés de joie pendant le bond, halo doré
    if (t >= 1.62 && t < 1.96) p.yeux = "happy";
    teinte(p, AO.or, 0.6 * Ez.out(seg(t, 1.5, 1.9)) * (1 - Ez.inOut(seg(t, 3.0, 3.8))));
    // 4. coucou : il vous regarde, main droite qui s'agite, main gauche posée ; 5. il se pose, regard libre
    saluer(p, t, 2.3, 3.25);
    if (t >= 2.0 && t < 3.3) regarder(p, 0.12, 0.1);
    if (t >= 3.3) regarder(p, 0.12 * (1 - Ez.inOut(seg(t, 3.3, 3.6))), 0.1 * (1 - Ez.inOut(seg(t, 3.3, 3.6))), 1 - seg(t, 3.6, 3.9));
    s.ev(3.55, this.blink);
  } },
  frappe: { groupe: "Conversation écrite", titre: "Vous écrivez une question", f(t, p, s, o) {
    // attention : petit sursaut, oreilles qui se dressent, yeux un peu plus grands
    p.dy -= 0.04 * cloche(t, 0, 0.28);
    const a = Ez.back(seg(t, 0.05, 0.38));
    p.oL = 1 + 0.08 * a; p.oG = p.oD = -0.07 * a; p.es = 1 + 0.06 * Ez.out(seg(t, 0.1, 0.4));
    // il regarde la zone de saisie (o.regard : sa direction ; par défaut en bas à gauche) et lit ce que vous tapez :
    // saccades vers la droite, à un rythme irrégulier (fixations de 0,3 à 0,55 s), retour en début de ligne
    const base = o.regard ?? { x: -0.4, y: 0.55 }, sens = base.x > 0.05 ? 1 : -1;
    const rythme = [0.38, 0.52, 0.3, 0.46, 0.55, 0.34], cycle = rythme.reduce((a, b) => a + b, 0);
    let u = Math.max(0, t - 0.3) % cycle, pas = 0;
    while (pas < rythme.length - 1 && u > rythme[pas]) { u -= rythme[pas]; pas++; }
    regarder(p, base.x + (pas - 2.5) * 0.1, base.y, Ez.out(seg(t, 0.06, 0.3)));
    // tête penchée vers la saisie, qui se balance lentement par curiosité ; une oreille tournée vers elle
    const e = Ez.inOut(seg(t, 0.1, 0.5));
    p.inc += sens * (0.06 + 0.035 * Math.sin(t * 2 * Math.PI / 5.2)) * e;
    p.tourne += sens * (0.1 + 0.03 * Math.sin(t * 2 * Math.PI / 5.2 + 1)) * e;
    if (sens < 0) p.oG -= 0.12 * e; else p.oD -= 0.12 * e;
  } },
  voila: { groupe: "Conversation écrite", titre: "Réponse terminée (voilà)", duree: 1.0, f(t, p, s) {
    hocher(p, t, 0.05, 0.16, 0.45);                       // petit « voilà » : hochement, yeux contents, joues roses
    if (t > 0.08 && t < 0.6) p.yeux = "happy";
    p.rougit = 0.3 * cloche(t, 0.05, 0.9);
    regarder(p, 0, 0);
    s.ev(0.7, this.blink);
  } },
  salut: { groupe: "Conversation écrite", titre: "Bonjour / au revoir (signe de la main)", duree: 1.8, f(t, p, s) {
    coucou(p, t, s, this);
  } },
  recu: { groupe: "Conversation écrite", titre: "Question envoyée", duree: 0.95, f(t, p, s) {
    hocher(p, t, 0, 0.24, 0.5);                           // « compris ! »
    p.sy *= 1 - 0.05 * cloche(t, 0.1, 0.3); p.sx *= 1 + 0.035 * cloche(t, 0.1, 0.3);
    if (t > 0.12 && t < 0.56) p.yeux = "happy";
    regarder(p, 0, 0, 1 - seg(t, 0.62, 0.95));
    s.ev(0.64, this.blink);
  } },
  reflechit: { groupe: "Conversation écrite", titre: "Il réfléchit", f(t, p, s) {
    teinte(p, AO.violet, 0.55 * Ez.out(seg(t, 0.05, 0.45)));
    s.ev(0.14, () => this.montrerPastille("points", AO.violet));
    // les yeux montent et passent d'un côté à l'autre, comme quand on cherche une idée
    const cote = Math.floor(t / 1.9) % 2 ? 1 : -1;
    regarder(p, cote * 0.42, -0.52, Ez.out(seg(t, 0, 0.25)));
    p.hoche += 0.05 * Ez.inOut(seg(t, 0, 0.4));
    p.inc += (0.06 * Math.sin(t * 2 * Math.PI / 3.8)) * Ez.inOut(seg(t, 0, 0.6));
    p.dy -= 0.015 * Math.sin(t * 2 * Math.PI / 3.8 - 0.8);
    p.oG = 0.22 * Ez.out(seg(t, 0.1, 0.5)); p.oD = -0.05 * Ez.out(seg(t, 0.1, 0.5));
  } },
  ecrit: { groupe: "Conversation écrite", titre: "Il écrit la réponse", f(t, p, s) {
    teinte(p, AO.bleu, 0.35 * Ez.out(seg(t, 0, 0.4)));
    s.ev(0.1, () => this.montrerPastille("crayon", AO.bleu));
    p.hoche -= 0.1 * Ez.inOut(seg(t, 0, 0.4));
    // la main écrit par mots (0,55 s), petite pause, ligne suivante (retour rapide) ; les yeux suivent le crayon
    const u = t % 3.0, mot = u % 0.675, ecrit = u < 2.7 && mot < 0.55;
    const prog = u < 2.7 ? u / 2.7 : 1 - Ez.inOut(seg(u, 2.7, 3.0));
    const kD = Ez.back(seg(t, 0.05, 0.3)), kG = Ez.back(seg(t, 0.09, 0.34));
    // main tenue basse et inclinée (comme un crayon posé sous lui) ; le griffonnage se voit, par petites boucles
    const gx = ecrit ? Math.sin(t * 2 * Math.PI * 6) * 0.045 : 0, gy = ecrit ? Math.sin(t * 2 * Math.PI * 12 + 1) * 0.035 : 0;
    main(p, 1, kD, 1.0 + 0.1 * prog + gx, 0.62 + gy, 0.7 + (ecrit ? Math.sin(t * 2 * Math.PI * 6) * 0.06 : 0), 0.85);
    mainRepos(p, -1, kG);
    regarder(p, 0.22 + 0.36 * prog, 0.55, Ez.out(seg(t, 0, 0.3)));
    p.dx += 0.012 * (prog - 0.5) * Ez.out(seg(t, 0, 0.4));
    p.dy -= (ecrit ? 0.008 * Math.abs(Math.sin(t * 2 * Math.PI * 3)) : 0) * Ez.out(seg(t, 0, 0.4));   // le corps vit avec le geste
  } },
  parle: { groupe: "Conversation écrite", titre: "Il lit la réponse à voix haute", voix: "donnees",
    duree: (o) => (o.duree ?? 4) + 0.3,
    debut(o) { if (o.niveau) this.parole = o.niveau; else this.dire(o.duree ?? 4); },
    f(t, p) {
      regarder(p, 0, 0, Ez.out(seg(t, 0, 0.3)));          // il vous parle, en vous regardant
      p.oL = 1 + 0.03 * Ez.out(seg(t, 0, 0.3));
    } },
  pas_compris: { groupe: "Conversation écrite", titre: "Question pas claire", f(t, p, s) {
    p.dy += 0.025 * cloche(t, 0, 0.14);                   // petit tassement, puis la tête penche
    p.inc += 0.17 * Ez.back(seg(t, 0.1, 0.42)) + 0.035 * cloche(t, 1.5, 1.85);
    p.oD = 0.45 * Ez.out(seg(t, 0.12, 0.45)); p.oG = -0.08 * Ez.out(seg(t, 0.12, 0.45));
    teinte(p, AO.cyan, 0.45 * Ez.out(seg(t, 0.1, 0.4)));
    s.ev(0.24, () => this.montrerPastille("question", AO.cyan));
    if (t < 1.0) regarder(p, 0.32, -0.3, Ez.out(seg(t, 0.08, 0.3)));
    else regarder(p, 0.32 * (1 - Ez.inOut(seg(t, 1.0, 1.25))), -0.3 * (1 - Ez.inOut(seg(t, 1.0, 1.25))));
    s.ev(1.0, this.blink);
  } },
  nouvelle: { groupe: "Conversation écrite", titre: "Nouvelle conversation", duree: 1.75, f(t, p, s) {
    sauter(p, t, 0, 0.24, 0.32, 1);
    s.ev(0.52, () => { this.montrerPastille("plus", AO.vert); this.emit("spark", 4); });   // juste APRÈS l'impact
    if (t > 0.5 && t < 1.15) p.yeux = "happy";
    teinte(p, AO.vert, 0.4 * tenue(t, 0.4, 1.3, 0.2, 0.4));
    regarder(p, 0, 0);
    s.ev(1.22, this.blink); s.ev(1.32, this.cacherPastille);
  } },
  langue: { groupe: "Conversation écrite", titre: "Change de langue (dioula, baoulé…)", duree: 1.95, f(t, p, s) {
    const a = cloche(t, 0, 0.16);                         // tassement, puis le visage fait un tour complet
    p.dy += 0.03 * a; p.sy *= 1 - 0.06 * a; p.sx *= 1 + 0.04 * a;
    p.roule = 2 * Math.PI * Ez.inOut(seg(t, 0.12, 0.88));
    p.sy *= 1 + 0.04 * cloche(t, 0.12, 0.88);
    s.ev(0.5, () => this.montrerPastille("globe", AO.violet));
    teinte(p, AO.violet, 0.4 * tenue(t, 0.4, 1.4, 0.2, 0.4));
    if (t > 0.92 && t < 1.55) p.yeux = "wink";
    p.inc += 0.12 * tenue(t, 0.9, 1.4, 0.16, 0.24);
    regarder(p, 0, 0);
    s.ev(1.6, this.cacherPastille);
  } },
  // ── messages vocaux ────────────────────────────────────────────────────────────────────────────────────
  ecoute: { groupe: "Messages vocaux", titre: "Écoute votre vocal", f(t, p, s, o) {
    s.ev(0.08, () => this.montrerPastille("micro", AO.bleu));
    teinte(p, AO.bleu, 0.35 * Ez.out(seg(t, 0, 0.4)));
    const a = Ez.back(seg(t, 0.04, 0.4));                 // oreilles grandes ouvertes, il se penche vers vous
    p.oL = 1 + 0.14 * a; p.oG = p.oD = -0.1 * a; p.es = 1 + 0.08 * Ez.out(seg(t, 0, 0.4));
    p.dy += 0.02 * Ez.inOut(seg(t, 0, 0.5)); p.sy *= 1 - 0.015 * Ez.inOut(seg(t, 0, 0.5));
    regarder(p, 0, 0.05, Ez.out(seg(t, 0, 0.3)));
    // écoute active : petits hochements « mm-hm » à intervalles irréguliers
    for (const t0 of [1.5, 3.1, 4.3]) hocher(p, t % 5.2, t0, 0.09, 0.4);
    const onde = (cote) => {                               // une onde arrive vers une oreille, qui frémit en la recevant
      this.emettre("onde", { x: cote * 1.3, y: -1.25, vx: -cote * 0.5, vy: 0.08, vie: 0.6, cote });
      this.plusTard(0.55, () => { (cote > 0 ? this.ore.d : this.ore.g).v -= 2.6; });
    };
    if (o.niveau) {                                       // vrai micro : une onde quand VOUS parlez (au plus toutes les 0,45 s)
      if (o.niveau() > 0.06 && t - (s.derniereOnde ?? -9) > 0.45) { s.derniereOnde = t; s.cote = -(s.cote || 1); onde(s.cote); }
    } else s.tous(0.9, 0.25, (k) => onde(k % 2 ? 1 : -1));
  } },
  transcrit: { groupe: "Messages vocaux", titre: "Transcrit votre vocal", f(t, p, s) {
    s.ev(0.08, () => this.montrerPastille("lignes", AO.bleu, 0));
    if (this.pastille && this.pastille.glyphe === "lignes") this.pastille.val = (t % 2.2) / 2.0;
    teinte(p, AO.bleu, 0.35 * Ez.out(seg(t, 0, 0.4)));
    // il lit des lignes : 4 fixations de gauche à droite, retour rapide, ligne suivante
    const ligne = Math.floor(t / 1.1), u = t % 1.1, fix = Math.min(3, Math.floor(u / 0.24));
    regarder(p, u < 0.96 ? -0.45 + fix * 0.3 : -0.45, (ligne % 2 ? 0.12 : -0.04), Ez.out(seg(t, 0, 0.25)));
    p.hoche -= 0.05 * Ez.inOut(seg(t, 0, 0.4)); p.es = 1 + 0.04 * Ez.out(seg(t, 0, 0.4));
    p.tourne += 0.06 * (u < 0.96 ? -0.45 + fix * 0.3 : -0.45);
  } },
  patience: { groupe: "Messages vocaux", titre: "Voix baoulé en préparation (longue)", f(t, p, s) {
    s.ev(0.1, () => this.montrerPastille("sablier", AO.violet));
    teinte(p, AO.violet, 0.3 * Ez.out(seg(t, 0, 0.5)));
    const ph = t * 2 * Math.PI / 4.2;                     // balancement lent ; le corps suit l'inclinaison (contre-temps)
    p.inc += 0.05 * Math.sin(ph) * Ez.inOut(seg(t, 0, 1)); p.dx += 0.02 * Math.sin(ph - 0.6) * Ez.inOut(seg(t, 0, 1));
    p.oG = p.oD = 0.12 * Ez.inOut(seg(t, 0, 0.8));
    const u = t % 9;                                      // il jette un œil au sablier, bâille, y rejette un œil
    const coup = tenue(u, 1.2, 2.0, 0.15, 0.2) + tenue(u, 7.0, 7.8, 0.15, 0.2);
    if (coup > 0) regarder(p, -0.6, -0.45, coup);
    const b = cloche(u, 4.2, 5.7);
    p.sy *= 1 + 0.1 * b; p.sx *= 1 - 0.05 * b; p.hoche += 0.1 * b;
    p.bouche = 1.35 * cloche(u, 4.35, 5.55); p.rond = 1;
    if (u > 4.7 && u < 5.35) p.yeux = "closed";
  } },
  // ── données AOCEDA ─────────────────────────────────────────────────────────────────────────────────────
  lit_donnees: { groupe: "Données AOCEDA", titre: "Lit vos données", f(t, p, s) {
    s.ev(0.08, () => this.montrerPastille("loupe", AO.bleu));
    teinte(p, AO.bleu, 0.35 * Ez.out(seg(t, 0, 0.4)));
    p.hoche -= 0.06 * Ez.out(seg(t, 0, 0.3)); p.es = 1 + 0.06 * Ez.out(seg(t, 0, 0.3));
    p.oL = 1 + 0.05 * Ez.out(seg(t, 0, 0.4)); p.oD = 0.12 * Ez.out(seg(t, 0, 0.4)); p.oG = -0.04;
    // lecture d'un tableau : saccades de case en case (fixations de 0,24 s), pas un balayage régulier
    const i = Math.floor(t / 0.24), col = i % 4, ligne = Math.floor(i / 4) % 2;
    const rx = -0.5 + col * 0.33, ry = ligne ? 0.12 : -0.1;
    regarder(p, rx, ry, Ez.out(seg(t, 0, 0.2)));
    p.tourne += 0.08 * rx;                                // la tête suit un peu les yeux
  } },
  montre: { groupe: "Données AOCEDA", titre: "Vous montre une carte", duree: (o) => o.tenue ?? 3.0, f(t, p, s, o) {
    const a = o.angle ?? -0.6, c = o.cote ?? (Math.cos(a) >= 0 ? 1 : -1), fin = (o.tenue ?? 3.0) - 0.45;
    const cible = o.regard ?? { x: Math.cos(a), y: Math.sin(a) };
    // les yeux partent d'abord vers la carte, le corps suit ; petit recul d'anticipation
    p.dx -= c * 0.03 * cloche(t, 0, 0.26); p.sy *= 1 - 0.035 * cloche(t, 0, 0.2);
    const k = t < fin ? Ez.back(seg(t, 0.12, 0.42)) : 1 - Ez.easeIn(seg(t, fin, fin + 0.26));
    const tape = cloche(t, 0.55, 0.7) + cloche(t, 0.78, 0.93);   // « ici, ici »
    pointerVers(p, c, a, k, tape);
    mainRepos(p, -c, k * 0.9);
    const penche = Ez.inOut(seg(t, 0.15, 0.5)) * (1 - Ez.inOut(seg(t, fin - 0.1, fin + 0.3)));
    p.inc += c * 0.05 * penche; p.dx += c * 0.03 * penche;
    // il regarde la carte, puis vous (« voilà »), puis jette un œil à la carte
    if (t < 1.12 || (t > 2.0 && t < 2.45)) regarder(p, cible.x, cible.y);
    else regarder(p, 0, 0, t < fin ? 1 : 1 - seg(t, fin, fin + 0.4));
    s.ev(1.08, this.blink); s.ev(1.15, () => { if (!o.muet) this.dire(1.3); });   // muet : pas de bouche sans vraie voix
  } },
  facture: { groupe: "Données AOCEDA", titre: "Calcule votre facture", duree: 2.7, f(t, p, s) {
    s.ev(0.05, () => this.montrerPastille("franc", AO.vert));
    // il compte : les yeux en haut, une oreille puis l'autre bat la mesure, petit hochement à chaque compte
    if (t < 1.25) regarder(p, 0.42, -0.45, Ez.out(seg(t, 0, 0.25)));
    else regarder(p, 0, 0);
    for (let i = 0; i < 4; i++) { const t0 = 0.25 + i * 0.24; p.hoche -= 0.05 * cloche(t, t0, t0 + 0.16); }
    s.ev(0.25, () => { this.ore.g.v -= 3; }); s.ev(0.49, () => { this.ore.d.v -= 3; });
    s.ev(0.73, () => { this.ore.g.v -= 3; }); s.ev(0.97, () => { this.ore.d.v -= 3; });
    // « trouvé ! » : petit saut, yeux contents, la pastille pulse
    sauter(p, t, 1.2, 0.1, 0.22, 0.6);
    s.ev(1.42, () => { this.pulserPastille(); this.emit("spark", 3); });
    if (t > 1.45 && t < 2.15) p.yeux = "happy";
    teinte(p, AO.vert, 0.25 * Ez.out(seg(t, 0, 0.3)) + 0.25 * tenue(t, 1.4, 2.2, 0.15, 0.4));
    s.ev(2.25, this.blink); s.ev(2.4, this.cacherPastille);
  } },
  prevision: { groupe: "Données AOCEDA", titre: "Prévoit la fin du mois", f(t, p, s) {
    s.ev(0.1, () => this.montrerPastille("courbe", AO.violet, 0));
    if (this.pastille && this.pastille.glyphe === "courbe") this.pastille.val = Ez.inOut(clamp((t % 2.4) / 1.6, 0, 1));
    teinte(p, AO.violet, 0.45 * Ez.out(seg(t, 0, 0.4)));
    // il regarde vers la droite et le haut (l'avenir), la tête tournée, il flotte un peu
    regarder(p, 0.55, -0.5, Ez.out(seg(t, 0, 0.3)));
    p.tourne += 0.12 * Ez.inOut(seg(t, 0, 0.5)); p.inc -= 0.05 * Ez.inOut(seg(t, 0, 0.5));
    p.dy -= 0.02 * Math.sin(t * 2 * Math.PI / 3.2) * Ez.inOut(seg(t, 0, 0.8));
  } },
  alerte: { groupe: "Données AOCEDA", titre: "Alerte : consommation en hausse", f(t, p, s) {
    sauter(p, t, 0, 0.16, 0.22, 1.1);                    // sursaut sec, yeux grands ouverts, oreilles dressées
    p.es = kf(t, [[0, 1], [0.12, 1.22, Ez.out], [0.8, 1.12, Ez.inOut]]);
    const a = Ez.back(seg(t, 0.06, 0.28));
    p.oL = 1 + 0.12 * a; p.oG = p.oD = -0.12 * a;
    s.ev(0.2, () => this.montrerPastille("eclair", AO.orange));
    // flash orange, puis il s'apaise en restant vigilant (pouls lent)
    teinte(p, AO.orange, kf(t, [[0, 0], [0.25, 0.85, Ez.out], [0.9, 0.45, Ez.inOut]]) + (t > 0.9 ? 0.1 * Math.sin((t - 0.9) * 2 * Math.PI / 1.6) : 0));
    regarder(p, 0, 0);
    const u = (t - 1.4) % 2.4;                            // toutes les 2,4 s, deux petits rebonds pour attirer l'œil
    if (t > 1.4) p.dy -= 0.045 * (cloche(u, 0, 0.16) + cloche(u, 0.2, 0.36));
  } },
  economie: { groupe: "Données AOCEDA", titre: "Bravo : économie réalisée", duree: 2.6, f(t, p, s) {
    sauter(p, t, 0, 0.3, 0.38, 1.1); sauter(p, t, 0.86, 0.12, 0.24, 0.6);   // grand saut, puis un petit de joie
    if (t > 0.05 && t < 2.1) p.yeux = "happy";            // pendant la préparation, puis décollage (0,11 s), puis les bras
    // les deux bras levés EN DIAGONALE sur les côtés (à la verticale, ils se confondraient avec les oreilles)
    const bras = tenue(t, 0.17, 0.62, 0.2, 0.25, Ez.backDoux);   // 60 ms après le décollage (action secondaire), sortie souple
    pointerVers(p, -1, Math.PI + 0.55, bras, 0, 0.7); pointerVers(p, 1, -0.55, bras, 0, 0.7);
    s.ev(0.2, () => {                                     // une gerbe de pièces en éventail, de part et d'autre des oreilles
      [-1, 1, -0.55, 0.55, 0].forEach((c, i) => this.emettre("piece", { x: c * 0.35, y: -0.9, vx: c * 0.9, vy: -2.3 - 0.25 * (i % 2), g: 5.2, vie: 1.2, taille: 0.11, retard: i * 0.05 }));
    });
    teinte(p, AO.vert, 0.5 * tenue(t, 0.15, 1.9, 0.3, 0.5));
    p.rougit = 0.5 * tenue(t, 0.3, 1.9, 0.3, 0.4);
    regarder(p, 0, 0);
    s.ev(2.2, this.blink);
  } },
  conseil: { groupe: "Données AOCEDA", titre: "Donne un conseil (idée)", duree: 2.8, f(t, p, s, o) {
    // l'idée arrive d'en haut : il lève les yeux, « ding », puis lève le doigt comme pour dire « astuce »
    if (t < 0.55) regarder(p, -0.2, -0.55, Ez.out(seg(t, 0, 0.18))); else regarder(p, 0, 0);
    p.oL = 1 + 0.06 * Ez.out(seg(t, 0, 0.3));
    p.es = 1 + 0.16 * cloche(t, 0.28, 0.62); p.dy -= 0.06 * cloche(t, 0.28, 0.56);
    s.ev(0.3, () => { this.montrerPastille("idee", AO.or); this.emit("spark", 3); });
    teinte(p, AO.or, 0.4 * tenue(t, 0.28, 2.3, 0.2, 0.4));
    // la main se lève en diagonale (« j'ai une astuce ») et s'agite un peu ; verticale, elle ferait une 3e oreille
    const k = t < 2.25 ? Ez.back(seg(t, 0.55, 0.8)) : 1 - Ez.easeIn(seg(t, 2.25, 2.5));
    const agite = t > 0.85 && t < 2.2 ? Math.sin((t - 0.85) * 2 * Math.PI * 1.6) * 0.1 * (1 - seg(t, 1.9, 2.2)) : 0;
    pointerVers(p, 1, -0.7 + agite, k, 0, 0.85);
    mainRepos(p, -1, k * 0.9);
    p.inc += 0.06 * tenue(t, 0.6, 2.3, 0.3, 0.4);
    s.ev(0.6, this.blink); s.ev(0.85, () => { if (!o.muet) this.dire(1.4); }); s.ev(2.45, this.cacherPastille);
  } },
  coupe_appareil: { groupe: "Données AOCEDA", titre: "Propose de couper un appareil", duree: 3.0, f(t, p, s) {
    s.ev(0.08, () => this.montrerPastille("interrupteur", AO.vert, 1));
    // il regarde l'interrupteur, la main gauche sort du bord et monte en diagonale jusque sous la pastille, appuie
    // (la pastille s'enfonce), le bouton glisse sur « éteint »
    if (t < 1.75) regarder(p, -0.62, -0.52, Ez.out(seg(t, 0, 0.25))); else regarder(p, 0, 0);
    const k = t < 1.72 ? Ez.back(seg(t, 0.5, 0.82)) : 1 - Ez.easeIn(seg(t, 1.72, 1.98));
    const appui = kf(t, [[1.1, 0], [1.24, 1, Ez.out], [1.42, 0, Ez.inOut]]);   // vers la pastille, puis retrait
    main(p, -1, k, -1.14 + 0.62 * 0.07 * appui, -0.36 - 0.78 * 0.09 * appui, -0.9, 1);   // bras bien visible, bout sous la pastille
    p.inc -= 0.05 * tenue(t, 0.5, 1.7, 0.3, 0.3);
    p.sy *= 1 - 0.04 * cloche(t, 1.22, 1.44);
    const e = Ez.inOut(seg(t, 1.28, 1.5));
    if (this.pastille && this.pastille.glyphe === "interrupteur") {
      this.pastille.val = 1 - e; this.pastille.couleur = rgba(mix3(hexToRGB(AO.vert), hexToRGB(AO.gris), e));
    }
    s.ev(1.24, this.presserPastille);
    teinte(p, AO.vert, 0.35 * tenue(t, 0, 1.3, 0.3, 0.3));
    if (t > 1.62 && t < 2.3) p.yeux = "closed";            // satisfait
    hocher(p, t, 1.62, 0.14, 0.45);
    s.ev(2.4, this.blink); s.ev(2.6, this.cacherPastille);
  } },
  // ── appel Live ─────────────────────────────────────────────────────────────────────────────────────────
  appel: { groupe: "Appel Live", titre: "Appel Live : ça sonne (connexion)", f(t, p, s) {
    s.ev(0.05, () => this.montrerPastille("tel", AO.vert));
    teinte(p, AO.vert, 0.35 * Ez.out(seg(t, 0, 0.3)));
    regarder(p, 0, 0);
    const u = t % 1.2;                                    // « dring » toutes les 1,2 s : il frémit, les oreilles sursautent
    p.dx += 0.012 * Math.sin(u * 2 * Math.PI * 26) * cloche(u, 0.05, 0.55);
    p.dy -= 0.02 * cloche(u, 0.05, 0.3);
    s.tous(1.2, 0.07, () => { this.ore.g.v -= 3; this.ore.d.v -= 3; });
  } },
  connecte: { groupe: "Appel Live", titre: "Appel Live : connecté (coucou)", duree: 1.9, f(t, p, s) {
    s.ev(0, this.cacherPastille);
    coucou(p, t, s, this);
  } },
  ecoute_live: { groupe: "Appel Live", titre: "Vous écoute pendant l'appel", f(t, p, s, o) {
    const e = Ez.inOut(seg(t, 0, 0.4));
    regarder(p, 0, 0, Ez.out(seg(t, 0, 0.3)));
    if (o.microCoupe) { p.oG = p.oD = 0.32 * e; p.oL = 1 - 0.06 * e; p.inc += 0.04 * e; return; }   // micro coupé : il n'entend rien
    p.oL = 1 + 0.05 * e; p.es = 1 + 0.04 * e;
    // quand vous parlez (niveau du micro) : oreilles tendues, tête un peu penchée, petit « mm-hm » juste APRÈS un temps
    // fort de votre voix (au plus un toutes les 1,6 s) ; galerie : voix simulée
    const n = o.niveau ? o.niveau() : (Math.sin(t * 0.9) > 0 ? simulerParole(t) * 0.16 : 0);
    s.voix = Math.max(n, (s.voix || 0) * 0.92);
    const v = clamp(s.voix * 6, 0, 1);
    p.oG -= 0.08 * v; p.oD -= 0.08 * v; p.inc += 0.04 * v * e;
    if (v > 0.5 && t - (s.dernierHoche ?? -9) > 1.6) s.dernierHoche = t;
    if (s.dernierHoche != null) hocher(p, t, s.dernierHoche + 0.25, 0.08, 0.4);
  } },
  reconnexion: { groupe: "Appel Live", titre: "Reconnexion en cours", f(t, p, s) {
    s.ev(0.05, () => this.montrerPastille("relais", AO.bleu));
    teinte(p, AO.bleu, 0.3 * Ez.out(seg(t, 0, 0.4)));
    const b = Math.sin(t * 2 * Math.PI / 2.4) * Ez.inOut(seg(t, 0, 0.5));   // il cherche du regard, sans s'affoler
    regarder(p, 0.4 * b, -0.15); p.tourne += 0.08 * b; p.oG = 0.1 - 0.1 * b; p.oD = 0.1 + 0.1 * b;
  } },
  parle_live: { groupe: "Appel Live", titre: "Parle en direct (avec les mains)", voix: "donnees",
    duree: (o) => (o.duree ?? 4) + 0.3,
    debut(o) { if (o.niveau) this.parole = o.niveau; else this.dire(o.duree ?? 4); },
    f(t, p, s, o) {
      p.gesteParole = 1;
      regarder(p, 0, 0, Ez.out(seg(t, 0, 0.3)));
      p.oL = 1 + 0.03 * Ez.out(seg(t, 0, 0.3));
      const e = Ez.inOut(seg(t, 0, 0.5));                // humeur selon ce que disent les données (baisse / hausse)
      if (o.humeur === "contente") { teinte(p, AO.vert, 0.3 * e); p.rougit = 0.35 * e; if (Math.sin(t * 1.3) > 0.88) p.yeux = "happy"; }
      else if (o.humeur === "inquiete") { teinte(p, AO.orange, 0.3 * e); p.oG = p.oD = 0.22 * e; p.es = 1 + 0.06 * e; }
    } },
  interrompu: { groupe: "Appel Live", titre: "Vous lui coupez la parole", f(t, p, s) {
    // il s'arrête net : petit sursaut, « oh », oreilles dressées, puis il vous écoute
    p.dy -= 0.09 * cloche(t, 0, 0.3); p.sy *= 1 + 0.06 * cloche(t, 0, 0.18);
    p.es = kf(t, [[0, 1], [0.08, 1.22, Ez.out], [0.6, 1.08, Ez.inOut]]);
    if (t > 0.04 && t < 0.45) p.yeux = "dot";
    p.bouche = 0.32 * cloche(t, 0.04, 0.5); p.rond = 1;
    const a = Ez.back(seg(t, 0.02, 0.3));
    p.oL = 1 + 0.12 * a; p.oG = -0.08 * a; p.oD = -0.14 * a;
    p.dy += 0.015 * Ez.inOut(seg(t, 0.5, 0.9));
    regarder(p, 0, 0);
    s.ev(0.55, this.blink);
    // ensuite il vous écoute vraiment : petits hochements « mm-hm » irréguliers, tête un peu penchée
    if (t > 1.0) for (const t0 of [0.5, 2.1, 3.3]) hocher(p, (t - 1.0) % 4.2, t0, 0.08, 0.4);
    p.inc += 0.05 * Ez.inOut(seg(t, 0.9, 1.4));
  } },
  regarde_ecran: { groupe: "Appel Live", titre: "Regarde votre écran ou caméra", f(t, p, s) {
    s.ev(0.1, () => this.montrerPastille("oeil", AO.bleu));
    teinte(p, AO.bleu, 0.3 * Ez.out(seg(t, 0, 0.4)));
    p.echelle = 1 + 0.035 * Ez.inOut(seg(t, 0, 0.5)); p.dy += 0.02 * Ez.inOut(seg(t, 0, 0.5)); p.es = 1 + 0.15 * Ez.out(seg(t, 0, 0.4));
    const pts = [[0, 0.05], [-0.3, -0.1], [0.25, -0.05], [0.1, 0.2], [-0.15, 0.15]], q = pts[Math.floor(t / 0.45) % pts.length];
    regarder(p, q[0], q[1], Ez.out(seg(t, 0, 0.3)));
    hocher(p, t % 3.2, 2.4, 0.08, 0.4);                    // « hmm » de temps en temps
  } },
  ouvre_fenetre: { groupe: "Appel Live", titre: "Ouvre les Options", duree: 2.3, f(t, p, s, o) {
    const a = o.angle ?? -0.95, c = o.cote ?? (Math.cos(a) >= 0 ? 1 : -1);
    const cible = o.regard ?? { x: Math.cos(a), y: Math.sin(a) };
    if (t < 1.4) regarder(p, cible.x, cible.y, Ez.out(seg(t, 0, 0.15))); else regarder(p, 0, 0);
    p.dx -= c * 0.03 * cloche(t, 0, 0.24);
    const k = t < 1.38 ? Ez.back(seg(t, 0.14, 0.42)) : 1 - Ez.easeIn(seg(t, 1.38, 1.64));
    pointerVers(p, c, a, k, 1.5 * cloche(t, 0.6, 0.8));    // il appuie sur le bouton
    mainRepos(p, -c, k * 0.9);
    p.sy *= 1 - 0.035 * cloche(t, 0.62, 0.8);
    p.inc += c * 0.05 * tenue(t, 0.14, 1.3, 0.3, 0.3);
    if (t > 1.5 && t < 1.95) p.yeux = "happy";
    s.ev(2.02, this.blink);
  } },
  theme: { groupe: "Appel Live", titre: "Change le thème (clair / sombre)", duree: 2.0, f(t, p, s, o) {
    s.ev(0.12, () => this.montrerPastille(o.sombre ? "lune" : "soleil", o.sombre ? AO.nuit : AO.or));
    p.sy *= 1 - 0.05 * cloche(t, 0.36, 0.52);              // « clic »
    if (o.sombre) {                                        // la lumière baisse : il ferme doucement les yeux, les rouvre grands
      p.ouv = 1 - 0.92 * cloche(t, 0.4, 0.95);
      p.es = 1 + 0.1 * tenue(t, 0.9, 1.5, 0.25, 0.4);
      teinte(p, AO.nuit, 0.35 * tenue(t, 0.4, 1.4, 0.3, 0.4));
    } else {                                               // la lumière revient : ébloui, il plisse les yeux
      if (t > 0.45 && t < 0.95) p.yeux = "happy";
      p.hoche += 0.07 * cloche(t, 0.4, 1.0);
      teinte(p, AO.or, 0.4 * tenue(t, 0.4, 1.3, 0.2, 0.4));
    }
    regarder(p, 0, 0);
    s.ev(1.7, this.cacherPastille);
  } },
  relais: { groupe: "Appel Live", titre: "Change de modèle ou de compte", duree: 2.4, f(t, p, s) {
    s.ev(0.05, () => this.montrerPastille("relais", AO.bleu));
    teinte(p, AO.bleu, 0.35 * tenue(t, 0, 1.7, 0.25, 0.4));
    // passage de relais : il regarde à gauche, petit saut au changement, regarde à droite
    const vers = lerp(-1, 1, Ez.inOut(seg(t, 0.56, 0.76)));   // la tête passe de gauche à droite en 0,2 s
    regarder(p, vers * 0.55, 0, t < 1.35 ? 1 : 1 - seg(t, 1.35, 1.6));
    p.tourne += vers * 0.15 * (t < 1.35 ? 1 : 1 - Ez.inOut(seg(t, 1.35, 1.6))) * Ez.inOut(seg(t, 0, 0.25));
    sauter(p, t, 0.52, 0.08, 0.2, 0.6);                    // (les oreilles réagissent seules au saut, par leur ressort)
    if (t > 1.5 && t < 2.05) p.yeux = "wink";
    p.inc += 0.1 * tenue(t, 1.5, 1.9, 0.16, 0.24);
    s.ev(1.9, this.cacherPastille);
  } },
  au_revoir: { groupe: "Appel Live", titre: "Raccroche : au revoir", voix: "au_revoir",
    duree: (o) => (o.duree ?? 2.4) + (o.revenir === false ? 1.75 : 2.7),
    debut(o) { if (o.niveau) this.parole = o.niveau; else this.dire(o.duree ?? 2.4); },
    f(t, p, s, o) {
      const D = o.duree ?? 2.4;
      regarder(p, 0, 0);
      if (t > D && t < D + 0.35) p.yeux = "happy";
      saluer(p, t, D + 0.15, D + 1.0);
      // sortie (plus courte que l'entrée) : petit élan vers le haut, puis il rapetisse en descendant
      const e = Ez.easeIn(seg(t, D + 1.3, D + 1.62));
      p.dy -= 0.04 * cloche(t, D + 1.18, D + 1.34);
      p.echelle = lerp(1, 0.12, e); p.dy += 0.3 * e; p.alpha = 1 - Ez.easeIn(seg(t, D + 1.42, D + 1.62));
      if (o.revenir !== false) {                          // (galerie) il revient pour la suite
        const r = seg(t, D + 2.15, D + 2.6);
        if (r > 0) { p.echelle = lerp(0.12, 1, Ez.back(r)); p.dy = lerp(0.35, 0, Ez.out(r)); p.alpha = Ez.out(seg(t, D + 2.15, D + 2.33)); }
      }
    } },
  silence: { groupe: "Appel Live", titre: "Personne ne parle depuis longtemps", f(t, p, s) {
    // bâillement (bouche ronde, yeux fermés), les oreilles tombent lentement, puis il s'endort
    const b = cloche(t, 0.2, 1.5);
    p.sy *= 1 + 0.12 * b; p.sx *= 1 - 0.06 * b; p.hoche += 0.12 * b;
    p.bouche = 1.5 * cloche(t, 0.35, 1.4); p.rond = 1;     // un VRAI bâillement : grande bouche ronde
    if (t > 0.55) p.yeux = "closed";                       // les yeux ne se rouvrent pas : il s'endort
    p.oG = p.oD = 0.55 * Ez.inOut(seg(t, 0.8, 2.3)); p.oL = 1 - 0.05 * Ez.inOut(seg(t, 0.8, 2.3));
    if (t >= 1.9) {
      p.yeux = "closed";
      const r = Math.sin((t - 1.9) * 2 * Math.PI / 3.4), e = Ez.inOut(seg(t, 1.9, 2.6));
      p.sy *= 1 + 0.03 * r * e; p.sx *= 1 - 0.016 * r * e; p.dy += 0.035 * e; p.hoche -= 0.1 * e;
      s.tous(1.5, 2.2, () => this.emit("z", 1));
    }
    teinte(p, AO.nuit, 0.3 * Ez.inOut(seg(t, 1.2, 2.4)));
  } },
  // ── problèmes ──────────────────────────────────────────────────────────────────────────────────────────
  hors_ligne: { groupe: "Problèmes", titre: "Internet coupé", f(t, p, s) {
    s.ev(0.1, () => this.montrerPastille("wifi_coupe", AO.rouge));
    teinte(p, AO.rouge, 0.3 * Ez.out(seg(t, 0, 0.5)));
    // les oreilles font les antennes : elles balaient ensemble à la recherche du signal ; les yeux cherchent aussi
    const e = Ez.inOut(seg(t, 0, 0.6)), bal = Math.sin(t * 2 * Math.PI / 2.2) * e;
    p.oG = 0.18 * e - 0.32 * bal; p.oD = 0.18 * e + 0.32 * bal;
    regarder(p, 0.45 * bal, -0.25 * e);
    p.inc += 0.03 * bal;
    const u = t % 4.4;                                    // soupir déçu entre deux balayages
    p.sy *= 1 - 0.035 * cloche(u, 3.4, 4.2); p.dy += 0.02 * cloche(u, 3.4, 4.2);
  } },
  limite: { groupe: "Problèmes", titre: "Limite atteinte", f(t, p, s) {
    s.ev(0.1, () => this.montrerPastille("batterie", AO.rouge, 1));
    if (this.pastille && this.pastille.glyphe === "batterie") this.pastille.val = 1 - Ez.inOut(seg(t, 0.2, 2.8));
    teinte(p, AO.orange, 0.35 * Ez.out(seg(t, 0, 0.5)));
    const e = Ez.inOut(seg(t, 0, 0.9));                    // il s'affaisse, oreilles tombantes, souffle lourd
    p.dy += 0.05 * e; p.sy *= 1 - 0.04 * e; p.sx *= 1 + 0.025 * e;
    p.oG = p.oD = 0.6 * Ez.inOut(seg(t, 0.1, 1.0)); p.oL = 1 - 0.04 * e;
    const r = Math.sin(t * 2 * Math.PI / 2.2); p.sy *= 1 + 0.022 * r * e; p.sx *= 1 - 0.012 * r * e;
    if (t > 0.3) p.yeux = "tired";
    regarder(p, 0, 0.35, e);
    s.tous(1.7, 0.6, () => this.emit("sweat", 1));
  } },
  erreur: { groupe: "Problèmes", titre: "Erreur", f(t, p, s) {
    // tremblement : 3 cycles qui s'amortissent en 0,36 s, sans dépassement ; flash rouge qui s'apaise
    secouer(p, t, 0, "dx", 0.07, 3, 0.36); secouer(p, t, 0, "inc", 0.03, 3, 0.36);
    if (t > 0.02) p.yeux = "flat";
    const a = Ez.out(seg(t, 0, 0.25));
    p.oG = p.oD = 0.55 * a; p.oL = 1 - 0.06 * a;
    teinte(p, AO.rouge, kf(t, [[0, 0], [0.08, 0.9, Ez.out], [0.75, 0.42, Ez.inOut]]));
    s.ev(0.12, () => this.montrerPastille("croix", AO.rouge));
    regarder(p, 0, 0.3, Ez.inOut(seg(t, 0.4, 0.9)));      // un peu gêné, il baisse les yeux
    p.inc += 0.04 * Ez.inOut(seg(t, 0.4, 0.9));
  } },
  // ── émotions en plus ───────────────────────────────────────────────────────────────────────────────────
  reveil: { groupe: "Émotions en plus", titre: "Se réveille", duree: 1.3, f(t, p, s) {
    const e = cloche(t, 0, 0.7);                          // il s'étire (corps allongé, tête en arrière), ouvre les yeux,
    p.sy *= 1 + 0.1 * e; p.sx *= 1 - 0.05 * e; p.hoche += 0.08 * e;   // les oreilles remontent, petit « brr » de la tête
    if (t < 0.35) p.yeux = "closed";
    p.oL = 1 + 0.08 * Ez.back(seg(t, 0.2, 0.6));
    secouer(p, t, 0.75, "tourne", 0.12, 2, 0.4);
    regarder(p, 0, 0);
    s.ev(0.4, this.blink);
  } },
  triste: { groupe: "Émotions en plus", titre: "Triste", f(t, p, s) {
    // lent et vers le bas : les oreilles tombent, le corps s'affaisse, les paupières sont lourdes, il soupire
    // oreilles basses en biais et plus courtes (rabattues) ; à l'horizontale, elles feraient des cornes
    p.oG = p.oD = 0.5 * Ez.inOut(seg(t, 0, 1.1)); p.oL = 1 - 0.2 * Ez.inOut(seg(t, 0, 1.1));
    const e = Ez.inOut(seg(t, 0.1, 1.2));
    p.dy += 0.06 * e; p.sy *= 1 - 0.03 * e;
    const u = t % 5;
    p.sy *= 1 + 0.035 * cloche(u, 1.4, 2.2) - 0.03 * cloche(u, 2.2, 3.1);   // inspire... soupire
    regarder(p, 0.1, 0.65, Ez.inOut(seg(t, 0, 0.8)));
    p.ouv = 1 - 0.2 * e;
    teinte(p, AO.nuit, 0.3 * e);
    s.tous(5, 1.0, () => { const o = this.posOeil(-1); this.emettre("larme", { x: o.x, y: o.y + 0.16, vx: -0.03, vy: 0.04, g: 0.7, vie: 1.4, taille: 0.11 }); });
  } },
  rire: { groupe: "Émotions en plus", titre: "Rire", duree: 2.0, f(t, p, s) {
    if (t > 0.05 && t < 1.8) p.yeux = "happy";
    // « ha ha ha ha » : quatre éclats qui ralentissent et faiblissent, tête un peu en arrière
    let ha = 0;
    [[0.12, 1], [0.33, 0.9], [0.53, 0.75], [0.74, 0.55]].forEach(([t0, f]) => { ha += f * cloche(t, t0, t0 + 0.19); });
    p.dy -= 0.06 * ha; p.sy *= 1 + 0.05 * ha; p.sx *= 1 - 0.03 * ha;
    p.bouche = 0.35 * tenue(t, 0.08, 1.0, 0.1, 0.3) + 0.8 * ha; p.hoche += 0.12 * tenue(t, 0.05, 1.1, 0.2, 0.4);
    p.inc += 0.05 * Math.sin(t * 2 * Math.PI * 2.7) * (1 - seg(t, 1.0, 1.6));
    p.rougit = 0.5 * tenue(t, 0.1, 1.5, 0.2, 0.4);
    regarder(p, 0, 0);
    s.ev(1.9, this.blink);
  } },
  fete: { groupe: "Émotions en plus", titre: "Fête (danse)", duree: 3.4, f(t, p, s) {
    // danse à 120 battements/min : rebond à chaque temps, balancement toutes les deux mesures, bras en l'air à tour de rôle
    const on = t > 0.15 && t < 3.15, ph = (t - 0.15) / 0.5, e = tenue(t, 0.15, 2.85, 0.2, 0.3);   // e s'éteint avant la fin
    if (on) {
      const r = Math.abs(Math.sin(Math.PI * ph));
      p.dy -= 0.1 * r * e; p.sy *= 1 + (0.06 * r - 0.08 * Math.pow(1 - r, 6)) * e; p.sx *= 1 - (0.04 * r - 0.06 * Math.pow(1 - r, 6)) * e;
      p.inc += 0.14 * Math.sin(Math.PI * ph * 0.5) * e; p.dx += 0.05 * Math.sin(Math.PI * ph * 0.5 - 0.5) * e;
      const gauche = Math.floor(ph) % 2 === 0;
      const hG = gauche ? Math.abs(Math.sin(Math.PI * ph)) : 0, hD = gauche ? 0 : Math.abs(Math.sin(Math.PI * ph));
      pointerVers(p, -1, Math.PI - lerp(0.45, -0.72, hG), e, 0, 0.8); pointerVers(p, 1, lerp(0.45, -0.72, hD), e, 0, 0.8);   // jamais à la verticale (oreilles)
    }
    if (t > 0.1 && t < 3.0) p.yeux = "happy";
    s.ev(0.2, () => {
      const c = [AO.or, AO.bleu, AO.vert, "#ff8fa3", AO.violet];
      for (let i = 0; i < 14; i++) this.emettre("confetti", { x: (Math.random() - 0.5) * 1.2, y: -1.1, vx: (Math.random() - 0.5) * 1.6, vy: -1.3 - Math.random() * 0.6, g: 2.4, vie: 1.9, taille: 0.09, couleur: c[i % 5], retard: i * 0.03 });
      this.emit("star", 2);
    });
    teinte(p, AO.or, 0.4 * e);
    regarder(p, 0, 0);
    s.ev(3.2, this.blink);
  } },
  oui: { groupe: "Émotions en plus", titre: "Oui (hoche la tête)", duree: 1.2, f(t, p, s) {
    hocher(p, t, 0, 0.26, 0.42); hocher(p, t, 0.38, 0.18, 0.42);
    if (t > 0.45 && t < 0.95) p.yeux = "happy";
    regarder(p, 0, 0);
    s.ev(1.0, this.blink);
  } },
  non: { groupe: "Émotions en plus", titre: "Non (secoue la tête)", duree: 1.3, f(t, p, s) {
    const v = kf(t, [[0, 0], [0.13, -0.5, Ez.out], [0.33, 0.48], [0.52, -0.36], [0.7, 0.2], [0.92, 0]]);
    p.tourne += v; p.dx -= v * 0.02;                       // le corps compense un peu (contre-mouvement)
    regarder(p, 0, 0);
    s.ev(1.0, this.blink);
  } },
  timide: { groupe: "Émotions en plus", titre: "Timide (rougit)", duree: 3.2, f(t, p, s) {
    p.rougit = kf(t, [[0, 0], [0.4, 1, Ez.out], [2.6, 1], [3.2, 0]]);
    const e = tenue(t, 0, 2.6, 0.5, 0.6);                  // il se fait petit, oreilles repliées, tête penchée
    p.echelle = 1 - 0.04 * e; p.sy *= 1 - 0.03 * e; p.inc -= 0.1 * e;
    p.oG = p.oD = 0.5 * e; p.oL = 1 - 0.08 * e;
    // il regarde par terre, mais jette deux petits coups d'œil vers vous
    const coup = tenue(t, 1.1, 1.4, 0.08, 0.12) + tenue(t, 2.0, 2.2, 0.08, 0.12);
    regarder(p, lerp(-0.5, 0.05, coup), lerp(0.55, 0, coup), e > 0 ? Math.max(e, coup) : 0);
  } },
  colere: { groupe: "Émotions en plus", titre: "Énervé", duree: 2.7, f(t, p, s) {
    if (t > 0.05 && t < 2.3) p.yeux = "line";
    const e = tenue(t, 0, 2.25, 0.25, 0.4);               // il se gonfle, tremble ; de la vapeur sort des oreilles
    p.sx *= 1 + 0.06 * e; p.sy *= 1 - 0.05 * e;
    p.dx += 0.012 * Math.sin(t * 2 * Math.PI * 24) * tenue(t, 0.1, 0.8, 0.05, 0.2);
    p.oG = p.oD = 0.38 * e; p.oL = 1 - 0.12 * e;
    teinte(p, AO.rouge, kf(t, [[0, 0], [0.15, 0.85, Ez.out], [1.0, 0.5], [2.25, 0.5], [2.7, 0]]));
    p.rougit = 0.6 * e;
    for (const t0 of [0.3, 0.9, 1.5]) s.ev(t0, () => {
      for (const sd of [-1, 1]) { const b = this.boutOreille(sd); this.emettre("bouffee", { x: b.x, y: b.y, vx: sd * 0.25, vy: -0.5, vie: 0.85, taille: 0.1 }); }
    });
    p.dy -= 0.03 * cloche(t, 1.4, 1.6); p.sy *= 1 - 0.04 * cloche(t, 1.55, 1.7);   // « pff » : il tape du pied
    regarder(p, 0, 0);
  } },
};
// les chorégraphies qui gèrent elles-mêmes le souffle (pas de respiration d'ambiance en plus)
ACTIONS_AOCEDA.silence.f.souffle = true; ACTIONS_AOCEDA.limite.f.souffle = true; ACTIONS_AOCEDA.triste.f.souffle = true;

// ════════════════════════════════════════════════════════════════════════════════════════════════════════
// Scène du personnage AOCEDA : la toile qui l'affiche dans une page, à la taille de son CONTENEUR (un carré).
//  - La toile est plus grande que le conteneur (marge) : oreilles, pastille et particules débordent sans être coupées ;
//    elle ne reçoit aucun clic (seul le conteneur, à la taille du personnage, en reçoit).
//  - Elle ne dessine que si le personnage est visible (onglet affiché, conteneur à l'écran et pas masqué) : aucun
//    calcul inutile sur un téléphone ou sur le PC qui sert aussi de serveur.
//  - placer(autreConteneur) : le personnage change de place en glissant (technique FLIP), sans réapparaître.
//  - Mêmes proportions que la galerie et le banc d'essai (CADRE 80 %, débord 0,108).
// ════════════════════════════════════════════════════════════════════════════════════════════════════════

// Images par seconde (audit du 09/10/2026 : la page prenait ~25 % d'un cœur du processeur SANS RIEN FAIRE, le
// personnage étant redessiné 60 fois par seconde même au repos ; sur téléphone, la batterie fondait) :
// en mouvement (geste, réaction, parole, écoute) : 60 ; au repos (il respire, cligne des yeux) : 24 ; mouvements
// réduits demandés par le système : 12.
const IPS_MOUVEMENT = 60, IPS_REPOS = 24, IPS_REDUIT = 12;

class ScenePersonnage {
  constructor(conteneur, o = {}) {
    this.perso = o.perso || new PersonnageAoceda();
    this.cadre = { e: 0.8, bas: 0.07 };
    this.marge = o.marge ?? 1.6;
    this.actif = true; this.visible = false; this.raf = 0; this.avant = 0; this.taille = 0; this.dpr = 1;
    this.auRepos = false; this.minuterie = 0;         // auRepos : posé par la page (Directeur) quand rien ne bouge
    this.reduit = ScenePersonnage.mouvementReduit;
    matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", (e) => { this.reduit = e.matches; });
    this.toile = document.createElement("canvas");
    this.toile.className = "perso-toile";
    this.toile.setAttribute("aria-hidden", "true");
    Object.assign(this.toile.style, { position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)",
                                      pointerEvents: "none", display: "block" });
    this.ctx = this.toile.getContext("2d");
    this.io = new IntersectionObserver((e) => { this.visible = e[e.length - 1].isIntersecting; this.relancer(); });
    this.ro = new ResizeObserver(() => this.ajuster());
    document.addEventListener("visibilitychange", () => this.relancer());
    addEventListener("pointermove", (ev) => this.suivre(ev), { passive: true });
    this.placer(conteneur, false);
  }

  /** Mouvements réduits demandés par le système (accessibilité). */
  static get mouvementReduit() { return matchMedia("(prefers-reduced-motion: reduce)").matches; }

  /** Met le personnage dans un autre conteneur ; anime = il y glisse depuis sa place actuelle (ou depuis `depuis`, sa
   *  position mesurée AVANT un changement de mise en page). */
  placer(conteneur, anime = true, depuis = null) {
    if (!conteneur || conteneur === this.conteneur) return;
    const avant = !anime ? null : depuis || (this.toile.isConnected && this.taille ? this.toile.getBoundingClientRect() : null);
    if (this.conteneur) this.ro.unobserve(this.conteneur);
    this.conteneur = conteneur;
    if (getComputedStyle(conteneur).position === "static") conteneur.style.position = "relative";
    conteneur.appendChild(this.toile);
    this.ro.observe(conteneur);
    this.io.disconnect(); this.io.observe(conteneur);
    this.ajuster();
    if (!avant || !avant.width || ScenePersonnage.mouvementReduit) return;
    const apres = this.toile.getBoundingClientRect();
    if (!apres.width) return;
    const dx = avant.left + avant.width / 2 - (apres.left + apres.width / 2);
    const dy = avant.top + avant.height / 2 - (apres.top + apres.height / 2), k = avant.width / apres.width;
    this.toile.animate([{ transform: `translate(-50%, -50%) translate(${dx}px, ${dy}px) scale(${k})` },
                        { transform: "translate(-50%, -50%)" }], { duration: 560, easing: "cubic-bezier(.2, .8, .2, 1)" });
  }

  /** La toile suit la taille du conteneur (densité de pixels bornée à 2). */
  ajuster() {
    const t = this.conteneur.clientWidth;
    this.taille = t;
    if (!t) return;
    this.dpr = Math.min(2, devicePixelRatio || 1);
    const cote = Math.round(t * this.marge), px = Math.round(cote * this.dpr);
    this.toile.style.width = this.toile.style.height = cote + "px";
    // largeur ET hauteur : une toile neuve fait 300 x 150 ; à 125 % de zoom, 240 px x 1,25 = 300 tombait pile sur sa
    // largeur, la hauteur restait à 150 et la moitié basse du personnage était coupée (vu le 05/10/2026)
    if (this.toile.width !== px || this.toile.height !== px) { this.toile.width = px; this.toile.height = px; }
    this.relancer();
  }

  /** Centre du corps, en coordonnées de la page (t : taille du conteneur). */
  centre() {
    const r = this.conteneur.getBoundingClientRect(), t = r.width, e = this.cadre.e;
    return { x: r.left + t / 2, y: r.top + e * 0.518 * t + (1 - e) * t / 2 + this.cadre.bas * t, t };
  }

  /** Direction d'un élément de la page vu par le personnage : {angle (bord du corps -> cible), cote, regard}. */
  viser(el) {
    const c = this.centre(), e = el.getBoundingClientRect();
    const ex = e.left + e.width / 2, ey = e.top + e.height / 2, cote = ex >= c.x ? 1 : -1;
    const R = 0.3 * c.t * this.cadre.e;                   // mêmes mesures que le moteur (rx = 1,14 R)
    const borne = (v) => Math.max(-1, Math.min(1, v)), d = Math.max(c.t * 1.2, 160);
    return { angle: Math.atan2(ey - c.y, ex - (c.x + cote * 1.14 * R)), cote,
             regard: { x: borne((ex - c.x) / d), y: borne((ey - c.y) / d) } };
  }

  /** Les yeux suivent la souris (seulement si le personnage est à l'écran). */
  suivre(ev) {
    if (!this.visible || !this.taille) return;
    const c = this.centre(), d = Math.max(180, c.t * 2), b = (v) => Math.max(-1, Math.min(1, v));
    this.perso.regarderSouris(b((ev.clientX - c.x) / d), b((ev.clientY - c.y) / d));
  }

  pause(oui) { this.actif = !oui; this.relancer(); }
  doitTourner() { return this.actif && this.visible && !document.hidden && this.taille > 0; }
  relancer() {
    if (this.raf || this.minuterie || !this.doitTourner()) return;
    this.avant = performance.now();
    this.raf = requestAnimationFrame(() => this.image());
  }
  /** Cadence voulue maintenant (images par seconde). */
  cadence() { return this.reduit ? IPS_REDUIT : this.auRepos ? IPS_REPOS : IPS_MOUVEMENT; }
  /** Il se remet à bouger : l'image suivante part tout de suite (sans attendre la fin de la pause du repos). */
  accelerer() {
    if (!this.minuterie) return;
    clearTimeout(this.minuterie); this.minuterie = 0;
    this.relancer();
  }
  /** Image suivante : à la prochaine trame de l'écran en mouvement ; au repos, le navigateur DORT entre deux images
   *  (minuterie, pas 60 réveils par seconde pour rien). */
  suivante() {
    const ips = this.cadence();
    if (ips >= IPS_MOUVEMENT) { this.raf = requestAnimationFrame(() => this.image()); return; }
    this.minuterie = setTimeout(() => {
      this.minuterie = 0;
      if (!this.raf && this.doitTourner()) this.raf = requestAnimationFrame(() => this.image());
    }, Math.max(0, 1000 / ips - 16));
  }
  image() {
    this.raf = 0;
    if (!this.doitTourner()) return;
    const t = performance.now(), dt = Math.min(0.1, (t - this.avant) / 1000);   // 0,1 s au plus : à 12 images/s
    this.avant = t;                                                              // le mouvement garde sa vitesse
    this.perso.update(dt);
    this.dessiner();
    if (typeof this.apresImage === "function") this.apresImage();
    this.suivante();
  }
  dessiner() {
    const { ctx, dpr, taille: t } = this, e = this.cadre.e, decal = (t * this.marge - t) / 2, debord = t * 0.108;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.toile.width, this.toile.height);
    this.perso.particleOverhang = debord;
    ctx.setTransform(dpr * e, 0, 0, dpr * e, dpr * (decal + t * (1 - e) / 2), dpr * (decal + t * (1 - e) / 2 + this.cadre.bas * t));
    this.perso.draw(ctx, t, t - debord);
  }
}

changerCouleurs(hexToRGB("#ffe07a"), hexToRGB("#f2b300"), "rgb(22,33,46)");   // couleurs AOCEDA
window.AocedaPersonnage = Object.freeze({ PersonnageAoceda, ScenePersonnage, ACTIONS_AOCEDA, changerCouleurs, hexToRGB });
})();
