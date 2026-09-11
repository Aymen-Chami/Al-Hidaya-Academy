// Large line-art "sky" motifs for the period cards — atmosphere, not icons. Everything is
// drawn in currentColor with a non-scaling stroke, so colour, opacity and weight come from CSS
// (--art-opacity, --art-stroke on each [data-period]); the card positions and scales the SVG.
// Suns live in a 200×200 box; the night field in a wide 320×140 one.

const polar = (cx, cy, r, deg) => {
  const a = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
};

function rays(cx, cy, inner, outer, angles) {
  return angles
    .map((deg) => {
      const [x1, y1] = polar(cx, cy, inner, deg);
      const [x2, y2] = polar(cx, cy, outer, deg);
      return `M${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}`;
    })
    .join("");
}

// Period 1 — sunrise: half disc on the horizon, rays fanning upward, soft reflection below.
function Sunrise() {
  return (
    <>
      <path d="M8 132H192" />
      <path d="M52 132A48 48 0 0 1 148 132" />
      <path d="M72 132A28 28 0 0 1 128 132" opacity="0.55" />
      <path d={rays(100, 132, 62, 86, [160, 137, 113, 90, 67, 43, 20])} />
      <path d="M58 148H142M74 162H126M88 176H112" opacity="0.6" />
    </>
  );
}

// Period 2 — midday: the full sun, long and short rays alternating (drawn a touch bolder).
function Noon() {
  const long = [0, 60, 120, 180, 240, 300];
  const short = [30, 90, 150, 210, 270, 330];
  return (
    <>
      <circle cx="100" cy="100" r="38" />
      <circle cx="100" cy="100" r="24" opacity="0.55" />
      <path d={rays(100, 100, 52, 82, long)} />
      <path d={rays(100, 100, 52, 68, short)} />
    </>
  );
}

// Period 3 — sunset: the mirror of sunrise, the disc sinking below a higher horizon,
// reflection lines tapering away underneath.
function Sunset() {
  // Circle (100,138) r46 cut by the horizon at y=120.
  return (
    <>
      <path d="M8 120H192" />
      <path d="M57.7 120A46 46 0 0 1 142.3 120" />
      <path d={rays(100, 138, 56, 72, [150, 120, 90, 60, 30])} opacity="0.8" />
      <path d="M60 134H140M72 148H128M84 162H116M94 176H106" opacity="0.6" />
    </>
  );
}

// All Periods — night: a scatter of dot "stars" (same dot accent as the hero art). Unlike
// the suns, this is a wide field across the top of the card (its own 320×140 box), kept
// above the text block.
const STARS = [
  [22, 18, 2, "white"],
  [58, 46, 2.6, "gold"],
  [96, 14, 1.6, "white"],
  [128, 54, 1.8, "white"],
  [162, 26, 2.4, "pink"],
  [196, 62, 1.6, "white"],
  [224, 18, 2, "blue"],
  [254, 48, 2.8, "gold"],
  [288, 22, 1.6, "white"],
  [302, 74, 2, "white"],
  [236, 94, 1.6, "blue"],
  [92, 84, 1.4, "white"],
];

function Night() {
  return STARS.map(([cx, cy, r, tone]) => <circle key={`${cx}-${cy}`} className={`period-art__star period-art__star--${tone}`} cx={cx} cy={cy} r={r} />);
}

const ART = { 1: Sunrise, 2: Noon, 3: Sunset, year: Night };

export default function PeriodArt({ period }) {
  const Art = ART[period] ?? Night;
  const wide = Art === Night;
  return (
    <svg
      className={wide ? "period-art period-art--wide" : "period-art"}
      viewBox={wide ? "0 0 320 140" : "0 0 200 200"}
      preserveAspectRatio={wide ? "xMidYMid slice" : undefined}
      aria-hidden="true"
      focusable="false"
    >
      <Art />
    </svg>
  );
}
