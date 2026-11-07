// All artwork is drawn here as inline SVG: no external files, so it works offline and passes the CSP.
const TEAL = '#105e58';
const TEAL_MID = '#1f9083';
const TEAL_SOFT = '#a7dfd6';
const CORAL = '#e8674a';
const SUN = '#f7cf6e';

export function Logo({ className = 'h-9 w-9' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <path d="M20 2 35 7.500v11.700c0 9.200-6.100 16.300-15 18.800C11.100 35.500 5 28.400 5 19.200V7.500z" fill={TEAL} />
      <path d="M12 13h16v4H12z" fill={TEAL_SOFT} />
      <path d="M15 19.500h10v4H15z" fill={SUN} />
      <path d="M18 26h4v4h-4z" fill={CORAL} />
    </svg>
  );
}

/** Login panel: load cascading down a ladder of steps and being held by the shield. */
export function ShieldScene({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 440 340" className={className} aria-hidden="true">
      <circle cx="220" cy="170" r="150" fill="#fff" opacity=".05" />
      <circle cx="220" cy="170" r="104" fill="#fff" opacity=".06" />
      <g fill="#fff" opacity=".9">
        <rect x="26" y="74" width="120" height="14" rx="7" opacity=".95" />
        <rect x="52" y="112" width="96" height="14" rx="7" fill={SUN} opacity="1" />
        <rect x="78" y="150" width="72" height="14" rx="7" fill="#f3a18c" opacity="1" />
        <rect x="104" y="188" width="46" height="14" rx="7" fill={CORAL} opacity="1" />
      </g>
      <g className="animate-float" style={{ transformOrigin: 'center' }}>
        <path d="M250 62 330 92v76c0 54-34 90-80 108-46-18-80-54-80-108V92z" fill={TEAL_MID} />
        <path d="M250 62 330 92v76c0 54-34 90-80 108z" fill="#3dab9d" />
        <path d="M250 84 310 106v62c0 42-25 70-60 86-35-16-60-44-60-86v-62z" fill={TEAL} />
        <path d="m222 164 21 21 40-46" fill="none" stroke="#fff" strokeWidth="13" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <g className="animate-float-slow">
        <rect x="346" y="60" width="72" height="46" rx="13" fill="#fff" />
        <path d="m362 104-3 16 17-14z" fill="#fff" />
        <circle cx="366" cy="83" r="4.500" fill={TEAL_MID} /><circle cx="382" cy="83" r="4.500" fill={TEAL_MID} /><circle cx="398" cy="83" r="4.500" fill={TEAL_MID} />
      </g>
      <g className="animate-float-slow">
        <path d="M46 244c14-8 30-8 44 0v46c-14-8-30-8-44 0z" fill="#fff" />
        <path d="M90 244c14-8 30-8 44 0v46c-14-8-30-8-44 0z" fill={TEAL_SOFT} />
      </g>
      <g className="animate-float">
        <rect x="350" y="228" width="58" height="58" rx="15" fill={SUN} />
        <path d="m366 258 9 9 18-21" fill="none" stroke={TEAL} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

/** Dashboard hero: a study desk. */
export function StudyDesk({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 340 210" className={className} aria-hidden="true">
      <ellipse cx="172" cy="190" rx="150" ry="13" fill="#000" opacity=".14" />
      <path d="M278 126c-4-24 6-44 20-52 2 22-2 42-12 54z" fill="#3dab9d" />
      <path d="M284 128c10-16 26-24 40-22-6 16-20 26-34 28z" fill={TEAL_SOFT} />
      <path d="M266 130h38l-6 54h-26z" fill={CORAL} />
      <rect x="82" y="46" width="172" height="112" rx="10" fill="#fff" />
      <rect x="92" y="56" width="152" height="92" rx="5" fill="#ecf8f6" />
      <rect x="104" y="116" width="20" height="22" rx="4" fill={TEAL_SOFT} />
      <rect x="132" y="98" width="20" height="40" rx="4" fill="#3dab9d" />
      <rect x="160" y="80" width="20" height="58" rx="4" fill={TEAL_MID} />
      <rect x="188" y="88" width="20" height="50" rx="4" fill={TEAL} />
      <rect x="216" y="68" width="18" height="70" rx="4" fill={CORAL} />
      <path d="M62 158h212l14 26a4 4 0 0 1-4 6H52a4 4 0 0 1-4-6z" fill="#d2efea" />
      <rect x="146" y="166" width="44" height="7" rx="3.500" fill="#70c8bb" />
      <rect x="10" y="168" width="62" height="12" rx="3" fill={SUN} />
      <rect x="16" y="156" width="52" height="12" rx="3" fill="#fff" />
      <rect x="8" y="180" width="66" height="10" rx="3" fill={CORAL} />
      <g className="animate-float">
        <circle cx="42" cy="66" r="24" fill={SUN} />
        <path d="m32 67 8 8 14-17" fill="none" stroke={TEAL} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

/** Empty tutor conversation. */
export function TutorBubbles({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 130" className={className} aria-hidden="true">
      <g className="animate-float">
        <rect x="16" y="14" width="118" height="66" rx="20" fill={TEAL} />
        <path d="m44 78-6 26 30-24z" fill={TEAL} />
        <rect x="38" y="35" width="74" height="7" rx="3.500" fill={TEAL_SOFT} />
        <rect x="38" y="51" width="50" height="7" rx="3.500" fill="#3dab9d" />
      </g>
      <g className="animate-float-slow">
        <rect x="104" y="60" width="82" height="48" rx="17" fill={CORAL} />
        <path d="m158 106 12 18-30-16z" fill={CORAL} />
        <circle cx="127" cy="84" r="5" fill="#fff" /><circle cx="145" cy="84" r="5" fill="#fff" /><circle cx="163" cy="84" r="5" fill="#fff" />
      </g>
    </svg>
  );
}

export function LostMap({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 220 150" className={className} aria-hidden="true">
      <path d="M14 34 76 14l68 20 62-20v102l-62 20-68-20-62 20z" fill="#d2efea" />
      <path d="M76 14v102M144 34v102" stroke="#a7dfd6" strokeWidth="3" />
      <path d="M34 106c20-32 38 2 58-20s34-12 56-34" fill="none" stroke={TEAL_MID} strokeWidth="4" strokeDasharray="3 10" strokeLinecap="round" />
      <g className="animate-float">
        <path d="M172 26c-13 0-22 9-22 22 0 16 22 38 22 38s22-22 22-38c0-13-9-22-22-22z" fill={CORAL} />
        <circle cx="172" cy="47" r="8" fill="#fff" />
      </g>
    </svg>
  );
}
