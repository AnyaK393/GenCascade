const PATHS = {
  home: 'M3 11.500 12 4l9 7.500M5.500 9.500V20h13V9.500M10 20v-6h4v6',
  chat: 'M21 12a8 8 0 0 1-11.800 7L4 20.500 5.500 15.500A8 8 0 1 1 21 12z',
  quiz: 'M9 4h6l1 2h3v14.500H5V6h3zM8.500 11l1.500 1.500 2.500-3M8.500 16.500h7',
  logout: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
  send: 'M4 12 20 4l-5 16-3-7z',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  back: 'M19 12H5M11 6l-6 6 6 6',
  check: 'M5 12.500 10 17.500 19.500 7',
  cross: 'M6 6l12 12M18 6 6 18',
  menu: 'M4 7h16M4 12h16M4 17h16',
  target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  star: 'M12 4l2.500 5.200 5.700.8-4.100 4 1 5.700L12 17.300 6.900 20l1-5.700-4.100-4 5.700-.8z',
  book: 'M12 6.500C10 5 7 4.500 4 5v14c3-.5 6 0 8 1.500 2-1.500 5-2 8-1.500V5c-3-.5-6 0-8 1.500zM12 6.500V20',
  shield: 'M12 3 19.500 6v5.500c0 4.700-3 8-7.500 9.500-4.500-1.500-7.500-4.800-7.500-9.500V6z',
};

export default function Icon({ name, className = 'h-5 w-5' }: { name: keyof typeof PATHS; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
