"use client";

import { useId } from "react";

export function BrandLogo({ dark = true }: { dark?: boolean }) {
  const fg = dark ? "text-white" : "text-graphite";
  const border = dark ? "border-white" : "border-graphite";
  return (
    <div className={`flex items-center gap-2.5 ${fg}`}>
      <div className={`border-2 ${border} px-1.5 py-0.5 leading-none`}>
        <span className="text-[26px] font-black tracking-tighter">MB</span>
      </div>
      <div className="text-[11px] font-bold leading-[1.15] tracking-wide">
        METALLIC
        <br />
        BELLOWS
        <br />
        PVT LTD
      </div>
    </div>
  );
}

const RIBS = 11;
const RIB_STEP = 9;

function Bellows({ x, y, scale, gid }: { x: number; y: number; scale: number; gid: string }) {
  const ribEnd = 10 + RIBS * RIB_STEP;
  const frontCx = ribEnd + 20;
  const holes = Array.from({ length: 10 }, (_, i) => (i / 10) * Math.PI * 2);
  return (
    <g transform={`translate(${x} ${y}) scale(${scale}) rotate(-18)`}>
      <ellipse cx="0" cy="0" rx="13" ry="47" fill={`url(#${gid}-flange)`} stroke="#3e4852" strokeWidth="0.6" />
      {Array.from({ length: RIBS }, (_, i) => (
        <rect
          key={i}
          x={8 + i * RIB_STEP}
          y={-39}
          width={12}
          height={78}
          rx={6}
          fill={`url(#${gid}-rib)`}
          stroke="#4f5963"
          strokeWidth="0.4"
        />
      ))}
      <rect x={ribEnd + 4} y={-35} width={14} height={70} fill={`url(#${gid}-rib)`} stroke="#4f5963" strokeWidth="0.4" />
      <ellipse cx={frontCx} cy="0" rx="15" ry="49" fill={`url(#${gid}-flange)`} stroke="#3e4852" strokeWidth="0.6" />
      <ellipse cx={frontCx} cy="0" rx="9" ry="31" fill={`url(#${gid}-bore)`} stroke="#2a3138" strokeWidth="0.6" />
      {holes.map((t, i) => (
        <circle
          key={i}
          cx={frontCx + 11.5 * Math.cos(t)}
          cy={41 * Math.sin(t)}
          r={2}
          fill="#2b323a"
          opacity={0.85}
        />
      ))}
    </g>
  );
}

export function BellowsIllustration({ className = "" }: { className?: string }) {
  const gid = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 230 170" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`${gid}-rib`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5f6973" />
          <stop offset="0.16" stopColor="#d9dee3" />
          <stop offset="0.32" stopColor="#ffffff" />
          <stop offset="0.52" stopColor="#a7b0b9" />
          <stop offset="0.74" stopColor="#e4e8ec" />
          <stop offset="1" stopColor="#4a545e" />
        </linearGradient>
        <linearGradient id={`${gid}-flange`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f4f6f8" />
          <stop offset="0.45" stopColor="#b4bcc4" />
          <stop offset="1" stopColor="#59636d" />
        </linearGradient>
        <radialGradient id={`${gid}-bore`} cx="0.4" cy="0.4" r="0.7">
          <stop offset="0" stopColor="#7d8791" />
          <stop offset="1" stopColor="#1d2329" />
        </radialGradient>
      </defs>
      <Bellows x={70} y={62} scale={0.62} gid={gid} />
      <Bellows x={30} y={112} scale={0.82} gid={gid} />
    </svg>
  );
}
