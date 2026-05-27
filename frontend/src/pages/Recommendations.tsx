import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  getRecommendations,
  type Recommendation,
  type RecommendationAction,
  type TimeRange,
} from '../api/client'
import BackButton from '../components/BackButton'
import TimeRangeFilter from '../components/TimeRangeFilter'
import InfoTip from '../components/InfoTip'

const KIND_LABELS: Record<Recommendation['kind'], string> = {
  opening_leak: 'Opening',
  phase_weakness: 'Phase',
  time_pressure: 'Time',
  rating_wall: 'Rating',
  color_asymmetry: 'Color',
  missed_wins: 'Conversion',
  anti_repertoire: 'Unprepared',
  blunder_pattern: 'Blunder kind',
  time_of_day: 'Time of day',
  tilt: 'Tilt',
}

const KIND_COLORS: Record<Recommendation['kind'], string> = {
  opening_leak: '#a78bfa',
  phase_weakness: '#fb923c',
  time_pressure: '#f87171',
  rating_wall: '#facc15',
  color_asymmetry: '#34d399',
  missed_wins: '#60a5fa',
  anti_repertoire: '#c084fc',
  blunder_pattern: '#f43f5e',
  time_of_day: '#22d3ee',
  tilt: '#fb7185',
}

const TREND_GLYPH: Record<'improving' | 'worsening' | 'stable', string> = {
  improving: '↓',
  worsening: '↑',
  stable: '·',
}

const TREND_COLOR: Record<'improving' | 'worsening' | 'stable', string> = {
  improving: '#10b981',
  worsening: '#ef4444',
  stable: 'var(--text-muted)',
}

function formatBucketLocal(utcStartHour: number, bucketHours: number): string {
  // Build a sample Date for today at that UTC hour, then format the local hour.
  const start = new Date()
  start.setUTCHours(utcStartHour, 0, 0, 0)
  const end = new Date(start.getTime() + bucketHours * 3600 * 1000)
  const localStart = start.getHours().toString().padStart(2, '0')
  const localEnd = end.getHours().toString().padStart(2, '0')
  return `${localStart}:00-${localEnd}:00`
}

export default function Recommendations() {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<TimeRange>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['recommendations', id, range],
    queryFn: () => getRecommendations(id!, range),
    enabled: !!id,
  })

  if (query.isLoading) return <p style={{ color: 'var(--text-secondary)' }}>Computing…</p>
  if (query.isError)
    return (
      <p style={{ color: 'var(--text-secondary)' }}>
        Couldn't load recommendations.
      </p>
    )

  const data = query.data!
  const recs = data.recommendations
  const baseline = data.baseline

  return (
    <div>
      <BackButton to={'/players/' + id} label="Dashboard" />
      <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
        What should you train?
      </h1>
      <p className="mb-3" style={{ color: 'var(--text-secondary)' }}>
        Your weaknesses ranked by how much they hurt you. Each item shows the
        numbers it's based on so you can decide if it's worth working on.
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <span className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
          Range
        </span>
        <TimeRangeFilter value={range} onChange={setRange} />
        <span className="ml-auto text-xs inline-flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
          How is this scored?
          <InfoTip>
            Each weakness gets a 0-1 priority blending <strong>severity</strong>{' '}
            (how much worse than your own baseline) and <strong>volume</strong>{' '}
            (how often it hits you). All thresholds are relative to your own
            CPL, so the advice scales to your level.
          </InfoTip>
        </span>
      </div>

      <div
        className="rounded-lg p-4 mb-6 border grid grid-cols-2 md:grid-cols-4 gap-4"
        style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
      >
        <BaselineStat label="Games" value={baseline.games} />
        <BaselineStat label="Baseline accuracy" value={`${baseline.accuracy}%`} />
        <BaselineStat label="Baseline CPL" value={baseline.avg_cpl.toFixed(1)} />
        <BaselineStat
          label="Blunder rate"
          value={`${(baseline.blunder_rate * 100).toFixed(1)}%`}
        />
      </div>

      {data.message && (
        <p className="mb-4" style={{ color: 'var(--text-muted)' }}>{data.message}</p>
      )}

      <Catalogue />

      {recs.length === 0 ? (
        <div
          className="rounded-lg p-6 border text-center"
          style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
        >
          <p className="text-lg" style={{ color: 'var(--text-primary)' }}>
            Nothing obviously broken in this range.
          </p>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            Either your stats are tight or there aren't enough games yet to spot a
            pattern. Try widening the range.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {recs.map((r, i) => {
            const isOpen = expanded === r.id
            return (
              <div
                key={r.id}
                className="rounded-lg border"
                style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
              >
                <button
                  onClick={() => setExpanded(isOpen ? null : r.id)}
                  className="w-full p-3 text-left flex items-start gap-3"
                >
                  <span
                    className="mt-0.5 w-7 h-7 flex items-center justify-center rounded-full font-bold text-xs flex-shrink-0"
                    style={{
                      background: KIND_COLORS[r.kind] + '22',
                      color: KIND_COLORS[r.kind],
                    }}
                  >
                    {i + 1}
                  </span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded"
                        style={{
                          background: KIND_COLORS[r.kind] + '22',
                          color: KIND_COLORS[r.kind],
                        }}
                      >
                        {KIND_LABELS[r.kind]}
                      </span>
                      <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {r.title}
                      </span>
                    </div>
                    <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
                      {localiseSummary(r)}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 self-center">
                    <ScoreBar score={r.score} />
                    {r.trend && <TrendChip trend={r.trend} />}
                  </div>
                  <span
                    className="w-5 text-center self-center"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {isOpen ? '▴' : '▾'}
                  </span>
                </button>
                {isOpen && <RecommendationDetail rec={r} />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TrendChip({ trend }: { trend: NonNullable<Recommendation['trend']> }) {
  const tone = TREND_COLOR[trend.direction]
  const glyph = TREND_GLYPH[trend.direction]
  const deltaText =
    trend.direction === 'stable'
      ? 'stable'
      : `${trend.delta >= 0 ? '+' : ''}${(trend.delta * 100).toFixed(0)}`
  const tooltip =
    trend.note
      ?? `Severity now ${(trend.current * 100).toFixed(0)} vs ${(trend.prior * 100).toFixed(0)} prior.`
  return (
    <span
      title={tooltip}
      className="text-[10px] font-bold inline-flex items-center gap-0.5"
      style={{ color: tone }}
    >
      {glyph} {deltaText}
    </span>
  )
}

/** Rewrite UTC labels in a time_of_day summary to the user's local TZ. */
function localiseSummary(r: Recommendation): string {
  if (r.kind !== 'time_of_day') return r.summary
  const e = r.evidence as {
    worst_bucket_utc_start_hour?: number
    best_bucket_utc_start_hour?: number
    bucket_hours?: number
    worst_bucket_cpl?: number
    best_bucket_cpl?: number
    ratio?: number
  }
  if (
    e.worst_bucket_utc_start_hour == null
    || e.best_bucket_utc_start_hour == null
    || e.bucket_hours == null
  )
    return r.summary
  const worst = formatBucketLocal(e.worst_bucket_utc_start_hour, e.bucket_hours)
  const best = formatBucketLocal(e.best_bucket_utc_start_hour, e.bucket_hours)
  return (
    `CPL at ${worst} local is ${e.worst_bucket_cpl}`
    + ` vs ${e.best_bucket_cpl} at ${best} local`
    + ` (${e.ratio}× worse).`
  )
}

type CatalogueEntry = {
  kind: Recommendation['kind']
  title: string
  what: string
  when_triggered: string
  evidence: string
  actions: string
}

const CATALOGUE: CatalogueEntry[] = [
  {
    kind: 'opening_leak',
    title: 'Opening leak',
    what:
      'An opening (split by color) where you score badly OR play far less accurately than your overall baseline.',
    when_triggered:
      'You have at least 5 games in the opening AND (average CPL in it ≥ 1.4× your baseline CPL OR win rate < 40%).',
    evidence:
      'Opening name, ECO code, color, total games, W/D/L, win rate, opening CPL, your baseline CPL.',
    actions:
      'Review your games in that opening (link to the Openings page filtered to it); open Lichess Opening Explorer for the line.',
  },
  {
    kind: 'phase_weakness',
    title: 'Phase weakness',
    what:
      'A game phase (opening, middlegame, endgame) where your accuracy collapses vs your overall play.',
    when_triggered:
      'Average CPL in that phase ≥ 1.25× your baseline CPL.',
    evidence:
      'Phase, total user moves in it, average CPL, blunder/mistake/inaccuracy rate, baseline CPL.',
    actions:
      'Open the Phase Performance page; jump to Lichess puzzles tagged with that phase theme (opening / middlegame / endgame).',
  },
  {
    kind: 'time_pressure',
    title: 'Time-pressure cliff',
    what:
      'Your accuracy drops sharply once your clock falls below a certain threshold in a given time class.',
    when_triggered:
      'For the time class (bullet/blitz/rapid/classical), the worst clock-bucket CPL ≥ 1.5× your best-bucket CPL.',
    evidence:
      'Time class, worst bucket (label, sample size, CPL, blunder rate), best bucket, CPL ratio.',
    actions:
      'Open Time Pressure page; try a slower time control; practise on a clock (puzzle rush link).',
  },
  {
    kind: 'rating_wall',
    title: 'Rating wall',
    what:
      'An opponent rating bucket where you consistently lose — either because you blunder against stronger play, or because you get out-prepared.',
    when_triggered:
      '≥ 5 games against the bucket AND win rate < 30%.',
    evidence:
      'Bucket label, games, W/D/L, win rate, CPL in bucket, baseline CPL, and a mode: "blunder-driven" (your CPL is high) or "out-prepared / positional" (your CPL is fine, so something else is losing).',
    actions:
      'Blunder-driven: tactics puzzles + review losses. Out-prepared: study opening repertoire + review losses.',
  },
  {
    kind: 'color_asymmetry',
    title: 'Color asymmetry',
    what:
      'A large gap between how you score with white versus black — almost always means one repertoire is weaker than the other.',
    when_triggered:
      '≥ 5 games as each color AND score-rate gap ≥ 15 percentage points (where score = wins + 0.5·draws).',
    evidence:
      'Weaker color, full breakdown for each color (games, W/D/L, score rate, win rate, CPL), gap in points.',
    actions:
      'Strengthen the weaker repertoire (Lichess studies link); filter the Games list to the weaker color to find patterns.',
  },
  {
    kind: 'missed_wins',
    title: 'Missed wins',
    what:
      'Games where your evaluation reached a winning advantage but you didn\'t convert. Strong signal that the win-conversion stage is leaking points.',
    when_triggered:
      'You reached ≥ +3.0 eval in at least 5 games AND converted < 60% of those games to wins.',
    evidence:
      'How many games reached a winning eval, how many you converted, drew, lost, conversion rate, sample game IDs.',
    actions:
      'Drill endgame puzzles; open the Phase Performance page to inspect endgame CPL specifically.',
  },
  {
    kind: 'anti_repertoire',
    title: 'Unprepared line',
    what:
      'An opening you face only a few times but score badly in. Means you have a gap in your repertoire that opponents are stumbling into.',
    when_triggered:
      '3 or 4 games in the line (below the opening-leak threshold) AND (win rate < 40% OR CPL ≥ 1.3× baseline). Skipped if the line is already flagged as a full opening leak.',
    evidence:
      'Opening name, ECO, color, games, W/D/L, win rate, opening CPL, baseline CPL.',
    actions:
      'Open the Lichess Opening Browser for the line; review the few games you have.',
  },
  {
    kind: 'blunder_pattern',
    title: 'Blunder pattern (hung pieces)',
    what:
      'Tells you what *kind* of blunder you make. If most of your blunders just put a piece on a square attacked more than defended, you need basic-safety training, not deep tactics.',
    when_triggered:
      '≥ 20 user blunders analysed AND ≥ 40% of them are simple hung-piece blunders (heuristic on the resulting position).',
    evidence:
      'Total blunders examined, hung-piece count, percentage, 3 sample game IDs.',
    actions:
      'Solve Lichess "hanging piece" puzzles; build the habit of asking what each move attacks/defends before playing it.',
  },
  {
    kind: 'time_of_day',
    title: 'Time-of-day weakness',
    what:
      'You play meaningfully worse during certain hours. Often correlates with fatigue or late-night sessions.',
    when_triggered:
      'A 3-hour UTC bucket with ≥ 10 games where average CPL is ≥ 1.3× the best bucket\'s average CPL. The page converts those hours into your local timezone.',
    evidence:
      'Worst and best buckets (label, sample size, CPL), ratio between them.',
    actions:
      'Save serious chess for your strong hours; play casually outside them.',
  },
  {
    kind: 'tilt',
    title: 'Tilt (post-loss drop)',
    what:
      'Within a single session, the game you play right after a loss is meaningfully less accurate than the game after a win. Suggests emotional control, not chess skill, is the bottleneck.',
    when_triggered:
      '≥ 10 in-session post-loss games AND ≥ 10 in-session post-win games AND post-loss accuracy is ≥ 5 points lower. Sessions are defined as games < 60 minutes apart.',
    evidence:
      'Average accuracy after a loss vs after a win, sample sizes, the gap.',
    actions:
      'Hard rule: stop playing after 2 consecutive losses; open Accuracy Trend to see the dip in context.',
  },
]

const KIND_BADGE: Record<Recommendation['kind'], string> = KIND_LABELS

function Catalogue() {
  const [open, setOpen] = useState(false)
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
      className="rounded-lg border mb-4"
      style={{ background: 'var(--bg-card)', borderColor: 'var(--border)' }}
    >
      <summary
        className="cursor-pointer select-none px-4 py-2 text-sm font-medium"
        style={{ color: 'var(--text-primary)' }}
      >
        How does this work? {open ? '▴' : '▾'}
      </summary>
      <div className="p-4 border-t" style={{ borderColor: 'var(--border)' }}>
        <p className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
          Every recommendation is one of five kinds. Each one has a fixed
          trigger condition (relative to your own baseline, not a global
          number), shows the evidence behind it, and proposes one or more
          concrete training actions. Priority is{' '}
          <strong>0.65·severity + 0.35·volume</strong>:
          <em> severity</em> measures how much worse than your baseline this is;{' '}
          <em>volume</em> measures how often the situation comes up.
        </p>
        <div className="space-y-3">
          {CATALOGUE.map((c) => (
            <div
              key={c.kind}
              className="rounded p-3 border"
              style={{ background: 'var(--bg-hover)', borderColor: 'var(--border)' }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded"
                  style={{
                    background: KIND_COLORS[c.kind] + '22',
                    color: KIND_COLORS[c.kind],
                  }}
                >
                  {KIND_BADGE[c.kind]}
                </span>
                <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {c.title}
                </span>
              </div>
              <dl className="text-xs grid grid-cols-1 md:grid-cols-[110px_1fr] gap-x-3 gap-y-1">
                <dt style={{ color: 'var(--text-muted)' }}>What it means</dt>
                <dd style={{ color: 'var(--text-secondary)' }}>{c.what}</dd>
                <dt style={{ color: 'var(--text-muted)' }}>Triggered when</dt>
                <dd style={{ color: 'var(--text-secondary)' }}>{c.when_triggered}</dd>
                <dt style={{ color: 'var(--text-muted)' }}>Evidence shown</dt>
                <dd style={{ color: 'var(--text-secondary)' }}>{c.evidence}</dd>
                <dt style={{ color: 'var(--text-muted)' }}>Suggested actions</dt>
                <dd style={{ color: 'var(--text-secondary)' }}>{c.actions}</dd>
              </dl>
            </div>
          ))}
        </div>
      </div>
    </details>
  )
}

function BaselineStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</p>
      <p className="text-xl font-bold text-indigo-400">{value}</p>
    </div>
  )
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 70 ? '#ef4444' : pct >= 40 ? '#f59e0b' : '#10b981'
  return (
    <div className="flex flex-col items-end self-center min-w-[60px]">
      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>priority</span>
      <span className="text-sm font-bold" style={{ color }}>{pct}</span>
    </div>
  )
}

function RecommendationDetail({ rec }: { rec: Recommendation }) {
  return (
    <div className="px-3 pb-3 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide mb-1" style={{ color: 'var(--text-muted)' }}>
            Why this matters
          </p>
          <div className="text-xs space-y-0.5" style={{ color: 'var(--text-secondary)' }}>
            <p>Severity: {(rec.severity * 100).toFixed(0)}/100</p>
            <p>Volume: {(rec.volume * 100).toFixed(0)}/100</p>
            <p>Priority: {(rec.score * 100).toFixed(0)}/100</p>
          </div>
          <p className="text-xs uppercase tracking-wide mt-3 mb-1" style={{ color: 'var(--text-muted)' }}>
            Evidence
          </p>
          <pre
            className="text-[11px] p-2 rounded overflow-x-auto"
            style={{
              background: 'var(--bg-hover)',
              color: 'var(--text-secondary)',
              maxHeight: 200,
            }}
          >
            {JSON.stringify(rec.evidence, null, 2)}
          </pre>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>
            Suggested actions
          </p>
          <div className="space-y-1.5">
            {rec.actions.map((a, i) => (
              <ActionLink key={i} action={a} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ActionLink({ action }: { action: RecommendationAction }) {
  const className =
    'block rounded px-3 py-2 text-sm border transition-colors hover:border-indigo-500'
  const style = {
    background: 'var(--bg-card)',
    borderColor: 'var(--border)',
    color: 'var(--text-primary)',
  }
  const labelWithExt = action.external ? `${action.label} ↗` : action.label

  if (!action.href) {
    return (
      <div className={className} style={{ ...style, opacity: 0.7 }}>
        {action.label}
      </div>
    )
  }
  if (action.external) {
    return (
      <a
        className={className}
        style={style}
        href={action.href}
        target="_blank"
        rel="noreferrer noopener"
      >
        {labelWithExt}
      </a>
    )
  }
  return (
    <Link className={className} style={style} to={action.href}>
      {action.label}
    </Link>
  )
}
