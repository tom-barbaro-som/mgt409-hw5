/** Original, simple bulldog badge in Yale blue (a nod to Handsome Dan, not the official mark). */
export function HandsomeDan({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Handsome Dan bulldog">
      <circle cx="32" cy="32" r="31" fill="#fff" />
      <circle cx="32" cy="32" r="28" fill="#00356b" />
      {/* ears */}
      <path d="M14 20 L21 12 L25 22 Z" fill="#e8e2d6" />
      <path d="M50 20 L43 12 L39 22 Z" fill="#e8e2d6" />
      {/* head + jowls */}
      <ellipse cx="32" cy="32" rx="17" ry="15" fill="#f4efe6" />
      <ellipse cx="24" cy="40" rx="9" ry="7" fill="#f4efe6" />
      <ellipse cx="40" cy="40" rx="9" ry="7" fill="#f4efe6" />
      {/* brow, eyes, nose, mouth */}
      <path d="M22 26 Q26 23 29 26" stroke="#5b4a3a" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M35 26 Q38 23 42 26" stroke="#5b4a3a" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <circle cx="26" cy="29" r="2.2" fill="#1f2933" />
      <circle cx="38" cy="29" r="2.2" fill="#1f2933" />
      <ellipse cx="32" cy="35" rx="5" ry="3.4" fill="#1f2933" />
      <path d="M26 43 Q32 47 38 43" stroke="#1f2933" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M28 44 L29 41 L30 44 Z M34 44 L35 41 L36 44 Z" fill="#fff" />
      {/* collar with a Y tag */}
      <path d="M18 50 Q32 57 46 50" stroke="#286dc0" strokeWidth="3" fill="none" />
      <circle cx="32" cy="55" r="4" fill="#ffd34d" />
      <text x="32" y="57.4" fontSize="6" fontWeight="700" fontFamily="Georgia, serif" textAnchor="middle" fill="#00356b">Y</text>
    </svg>
  )
}
