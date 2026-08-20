interface TopbarProps {
  isDarkMode: boolean;
  onToggleDarkMode: () => void;
  nombreCompleto: string | null;
  rol: string | null;
}

export default function Topbar({ isDarkMode, onToggleDarkMode, nombreCompleto, rol }: TopbarProps) {
  return (
    <div className="inline-flex items-center gap-4 bg-white/10 backdrop-blur-md border border-white/10 rounded-2xl pl-3 pr-4 py-2 shadow-lg transition-colors duration-300">
      <button
        onClick={onToggleDarkMode}
        className="text-gray-300 hover:bg-white/10 p-2 rounded-full transition-colors"
        aria-label="Alternar modo oscuro"
      >
        {isDarkMode ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        )}
      </button>

      <div className="flex items-center gap-3 pl-4 border-l border-white/10">
        <div className="text-right hidden sm:block">
          <div className="text-sm font-semibold text-white">{nombreCompleto ?? "Usuario"}</div>
          <div className="text-xs text-gray-300">{rol ?? ""}</div>
        </div>
        <img
          className="w-10 h-10 rounded-full border-2 border-[#ccff00] object-cover"
          src={`https://ui-avatars.com/api/?name=${encodeURIComponent(nombreCompleto ?? "Usuario")}&background=2d3748&color=ccff00`}
          alt="Avatar del usuario"
        />
      </div>
    </div>
  );
}
