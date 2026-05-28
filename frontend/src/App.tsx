import { Routes, Route, Link, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import PlayerImport from './pages/PlayerImport'
import PlayerDashboard from './pages/PlayerDashboard'
import GameList from './pages/GameList'
import GameReview from './pages/GameReview'
import Openings from './pages/Openings'
import OpeningsLegacyRedirect from './pages/OpeningsLegacyRedirect'
import PhaseDashboard from './pages/PhaseDashboard'
import TimePressure from './pages/TimePressure'
import AccuracyTrend from './pages/AccuracyTrend'
import RatingPerformance from './pages/RatingPerformance'
import Recommendations from './pages/Recommendations'
import TacticalPatterns from './pages/TacticalPatterns'
import EndgameConversion from './pages/EndgameConversion'
import ImportToast from './components/ImportToast'
import { getStoredPlayer, getStoredImport, isToastVisible, setToastVisible, onImportChanged } from './lib/storage'
import { useTheme } from './lib/theme'

function AppRoutes() {
  const navigate = useNavigate()

  useEffect(() => {
    const saved = getStoredPlayer()
    if (saved && window.location.pathname === '/') {
      navigate(`/players/${saved.id}`, { replace: true })
    }
  }, [navigate])

  return (
    <Routes>
      <Route path="/" element={<PlayerImport />} />
      <Route path="/players/:id" element={<PlayerDashboard />} />
      <Route path="/players/:id/games" element={<GameList />} />
      <Route path="/games/:id" element={<GameReview />} />
      <Route path="/players/:id/openings" element={<Openings />} />
      <Route path="/players/:id/phases" element={<PhaseDashboard />} />
      <Route path="/players/:id/time" element={<TimePressure />} />
      <Route path="/players/:id/accuracy" element={<AccuracyTrend />} />
      {/* Legacy URL: redirect to umbrella with the list tab pre-selected. */}
      <Route path="/players/:id/opening-stats" element={<OpeningsLegacyRedirect />} />
      <Route path="/players/:id/ratings" element={<RatingPerformance />} />
      <Route path="/players/:id/recommendations" element={<Recommendations />} />
      <Route path="/players/:id/tactics" element={<TacticalPatterns />} />
      <Route path="/players/:id/endgames" element={<EndgameConversion />} />
    </Routes>
  )
}

function App() {
  const { theme } = useTheme()
  const bg = theme === 'dark' ? 'bg-[#1a1a2e]' : 'bg-gray-100'
  const navBg = theme === 'dark' ? 'bg-[#16162a] border-gray-700' : 'bg-white border-gray-200'

  return (
    <div className={`min-h-screen ${bg}`}>
      <nav className={`${navBg} border-b px-6 py-3 flex items-center justify-between`}>
        <Link to="/" className="text-xl font-bold hover:text-indigo-400"
          style={{ color: 'var(--text-primary)' }}>
          Chess Review
        </Link>
        <div className="flex items-center gap-3">
          <PlayerNav />
          <ToastToggle />
          <ThemeToggle />
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <AppRoutes />
      </main>
      <ImportToast />
    </div>
  )
}

function PlayerNav() {
  const saved = getStoredPlayer()
  if (!saved) return null
  return (
    <Link to={`/players/${saved.id}`} style={{ color: 'var(--text-secondary)' }}
      className="text-sm hover:opacity-80">
      {saved.username}
    </Link>
  )
}

function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      onClick={toggle}
      className="w-8 h-8 rounded-lg flex items-center justify-center border transition-colors"
      style={{
        borderColor: 'var(--border)',
        color: 'var(--text-secondary)',
        background: 'var(--bg-card)',
      }}
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? '☀' : '☽'}
    </button>
  )
}

function ToastToggle() {
  const [hasImport, setHasImport] = useState(!!getStoredImport())
  const [visible, setVis] = useState(isToastVisible())

  useEffect(() => onImportChanged(() => {
    setHasImport(!!getStoredImport())
    setVis(isToastVisible())
  }), [])

  if (!hasImport) return null
  if (visible) return null  // toast is already showing, no need for icon

  return (
    <button
      onClick={() => setToastVisible(true)}
      className="w-8 h-8 rounded-lg flex items-center justify-center border transition-colors relative"
      style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)', background: 'var(--bg-card)' }}
      title="Show analysis progress"
    >
      ♛
      <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-indigo-500 rounded-full animate-pulse" />
    </button>
  )
}

export default App
