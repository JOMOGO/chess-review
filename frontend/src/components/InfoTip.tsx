import { useState, useRef, useEffect, type ReactNode } from 'react'

/**
 * Inline help icon. Hover or focus shows a popover with the explanation.
 */
export default function InfoTip({
  children,
  label = 'More info',
  side = 'top',
}: {
  children: ReactNode
  label?: string
  side?: 'top' | 'bottom'
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <span ref={ref} className="relative inline-block align-middle">
      <button
        type="button"
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="w-4 h-4 inline-flex items-center justify-center rounded-full text-[10px] font-bold border align-middle leading-none"
        style={{
          color: 'var(--text-secondary)',
          borderColor: 'var(--border)',
          background: 'var(--bg-card)',
        }}
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute left-1/2 -translate-x-1/2 z-50 w-64 p-2.5 text-xs rounded-md border shadow-lg ${
            side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5'
          }`}
          style={{
            color: 'var(--text-primary)',
            background: 'var(--bg-card)',
            borderColor: 'var(--border)',
          }}
        >
          {children}
        </span>
      )}
    </span>
  )
}

