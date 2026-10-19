export function BrandLogo({ dark = true }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="relative w-[70px] h-[58px] rounded-[3px] flex items-center justify-center overflow-hidden ring-1 ring-black/20"
        style={{
          background:
            "repeating-linear-gradient(90deg, rgba(255,255,255,0.18) 0 2px, rgba(0,0,0,0.06) 2px 5px), linear-gradient(160deg, #f1f3f5 0%, #b9c0c8 45%, #e6e9ec 70%, #8e969f 100%)",
        }}
      >
        <span
          className="text-[38px] font-black tracking-[-0.08em] leading-none text-[#111] -ml-1"
          style={{ textShadow: "0 1px 0 rgba(255,255,255,0.7)" }}
        >
          MB
        </span>
      </div>
      <div className={`text-[17px] font-extrabold leading-[1.15] tracking-wide ${dark ? "text-white" : "text-graphite"}`}>
        METALLIC
        <br />
        BELLOWS
        <br />
        PVT LTD
      </div>
    </div>
  );
}
