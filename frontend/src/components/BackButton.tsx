import { Link } from 'react-router-dom'

export default function BackButton({ to, label = 'Back' }: { to: string; label?: string }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-sm mb-4 hover:text-indigo-400 transition-colors"
      style={{ color: 'var(--text-secondary)' }}
    >
      ← {label}
    </Link>
  )
}
