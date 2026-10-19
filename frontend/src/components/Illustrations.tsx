"use client";

import { useId } from "react";

function MetalDefs({ gid }: { gid: string }) {
  return (
    <>
      <linearGradient id={`${gid}-rib`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#4d5762" />
        <stop offset="0.14" stopColor="#d3d9df" />
        <stop offset="0.3" stopColor="#ffffff" />
        <stop offset="0.5" stopColor="#9ba5af" />
        <stop offset="0.72" stopColor="#e4e8ec" />
        <stop offset="1" stopColor="#3b444e" />
      </linearGradient>
      <linearGradient id={`${gid}-flange`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#f7f9fb" />
        <stop offset="0.45" stopColor="#aeb7c0" />
        <stop offset="1" stopColor="#4c5660" />
      </linearGradient>
      <radialGradient id={`${gid}-bore`} cx="0.4" cy="0.4" r="0.7">
        <stop offset="0" stopColor="#77818b" />
        <stop offset="1" stopColor="#171c22" />
      </radialGradient>
    </>
  );
}

/** One stainless bellows expansion joint drawn along +x (back flange, convolution pack,
 * collar, front flange with bolt holes and open bore), then placed via translate/scale/rotate. */
function Bellows({
  x, y, scale, rotate, gid, ribs = 11,
}: { x: number; y: number; scale: number; rotate: number; gid: string; ribs?: number }) {
  const step = 9;
  const ribEnd = 10 + ribs * step;
  const frontCx = ribEnd + 20;
  const holes = Array.from({ length: 10 }, (_, i) => (i / 10) * Math.PI * 2);
  return (
    <g transform={`translate(${x} ${y}) scale(${scale}) rotate(${rotate})`}>
      <ellipse cx="0" cy="0" rx="13" ry="47" fill={`url(#${gid}-flange)`} stroke="#36404a" strokeWidth="0.6" />
      {Array.from({ length: ribs }, (_, i) => (
        <rect key={i} x={8 + i * step} y={-39} width={12} height={78} rx={6}
          fill={`url(#${gid}-rib)`} stroke="#48525c" strokeWidth="0.4" />
      ))}
      <rect x={ribEnd + 4} y={-35} width={14} height={70} fill={`url(#${gid}-rib)`} stroke="#48525c" strokeWidth="0.4" />
      <ellipse cx={frontCx} cy="0" rx="15" ry="49" fill={`url(#${gid}-flange)`} stroke="#36404a" strokeWidth="0.6" />
      <ellipse cx={frontCx} cy="0" rx="9" ry="31" fill={`url(#${gid}-bore)`} stroke="#22282f" strokeWidth="0.6" />
      {holes.map((t, i) => (
        <circle key={i} cx={frontCx + 11.5 * Math.cos(t)} cy={41 * Math.sin(t)} r={2} fill="#21272e" opacity={0.85} />
      ))}
    </g>
  );
}

/** Product cluster for the top of the left panel: several bellows joints on a deep-blue field. */
export function PromoArt({ className = "" }: { className?: string }) {
  const gid = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 290 300" className={className} aria-hidden="true" preserveAspectRatio="xMidYMid slice">
      <defs>
        <MetalDefs gid={gid} />
        <linearGradient id={`${gid}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0b2f66" />
          <stop offset="0.55" stopColor="#1257ad" />
          <stop offset="1" stopColor="#1b74d0" />
        </linearGradient>
        <radialGradient id={`${gid}-hi`} cx="0.75" cy="0.7" r="0.6">
          <stop offset="0" stopColor="#5fb2ff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#5fb2ff" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${gid}-floor`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0a2652" stopOpacity="0" />
          <stop offset="1" stopColor="#081d40" stopOpacity="0.85" />
        </linearGradient>
      </defs>
      <rect width="290" height="300" fill={`url(#${gid}-bg)`} />
      <rect width="290" height="300" fill={`url(#${gid}-hi)`} />
      <Bellows x={258} y={128} scale={0.95} rotate={90} gid={gid} ribs={10} />
      <Bellows x={196} y={160} scale={0.8} rotate={90} gid={gid} ribs={7} />
      <Bellows x={128} y={182} scale={0.62} rotate={90} gid={gid} ribs={5} />
      <rect y="240" width="290" height="60" fill={`url(#${gid}-floor)`} />
      <Bellows x={168} y={262} scale={1.05} rotate={172} gid={gid} ribs={9} />
    </svg>
  );
}

/** Blueprint-paper banner background: grid, faint section lines and dimension marks, with a
 * large bellows joint whose open flange faces the viewer. */
export function HeroArt({ className = "" }: { className?: string }) {
  const gid = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 1000 178" className={className} aria-hidden="true" preserveAspectRatio="xMaxYMid slice">
      <defs>
        <MetalDefs gid={gid} />
        <pattern id={`${gid}-grid`} width="22" height="22" patternUnits="userSpaceOnUse">
          <path d="M22 0H0V22" fill="none" stroke="#b9c7d6" strokeWidth="0.5" />
        </pattern>
        <linearGradient id={`${gid}-fade`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#eef2f6" />
          <stop offset="0.35" stopColor="#eef2f6" stopOpacity="0.6" />
          <stop offset="1" stopColor="#eef2f6" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="1000" height="178" fill="#e9eef4" />
      <rect width="1000" height="178" fill={`url(#${gid}-grid)`} opacity="0.55" />
      <g fill="none" stroke="#9fb1c4" strokeWidth="0.8" opacity="0.7">
        <rect x="430" y="18" width="250" height="130" />
        <line x1="430" y1="83" x2="680" y2="83" strokeDasharray="10 4 2 4" />
        <path d="M460 50 l14 -14 l14 14 l14 -14 l14 14 l14 -14 l14 14 l14 -14 l14 14 l14 -14 l14 14" />
        <path d="M460 116 l14 14 l14 -14 l14 14 l14 -14 l14 14 l14 -14 l14 14 l14 -14 l14 14 l14 -14" />
        <circle cx="560" cy="83" r="58" />
        <line x1="440" y1="160" x2="670" y2="160" />
        <line x1="440" y1="155" x2="440" y2="165" />
        <line x1="670" y1="155" x2="670" y2="165" />
        <rect x="520" y="120" width="70" height="26" />
        <line x1="520" y1="133" x2="590" y2="133" />
      </g>
      <g fill="#8ea2b8" fontFamily="Consolas, monospace" fontSize="8" opacity="0.8">
        <text x="535" y="157">600.0 OAL</text>
        <text x="526" y="130">SECTION A-A</text>
        <text x="526" y="143">SCALE 1:4</text>
      </g>
      <Bellows x={820} y={70} scale={1.55} rotate={168} gid={gid} ribs={9} />
      <rect width="1000" height="178" fill={`url(#${gid}-fade)`} />
    </svg>
  );
}

/** Very faint blueprint drawing of a bellows for the page background (bottom-right). */
export function BlueprintWatermark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 520 300" className={className} aria-hidden="true">
      <g fill="none" stroke="#6f8db0" strokeWidth="1">
        <ellipse cx="420" cy="170" rx="70" ry="120" />
        <ellipse cx="420" cy="170" rx="44" ry="78" />
        {Array.from({ length: 9 }, (_, i) => (
          <ellipse key={i} cx={360 - i * 30} cy="170" rx="34" ry="108" />
        ))}
        <ellipse cx="80" cy="170" rx="62" ry="118" />
        <line x1="20" y1="170" x2="500" y2="170" strokeDasharray="14 5 3 5" />
        <line x1="80" y1="30" x2="420" y2="30" />
        <line x1="80" y1="24" x2="80" y2="36" />
        <line x1="420" y1="24" x2="420" y2="36" />
      </g>
      <g fill="#6f8db0" fontFamily="Consolas, monospace" fontSize="14">
        <text x="230" y="24">600</text>
        <text x="450" y="60">ø260</text>
        <text x="20" y="280">B 9558</text>
      </g>
    </svg>
  );
}
