import { useEffect, useState } from 'react'
import { shouldUseDemoMode } from '../demo'

export function DemoBanner() {
  const [isDemo, setIsDemo] = useState(false)

  useEffect(() => {
    shouldUseDemoMode().then(setIsDemo)
  }, [])

  if (!isDemo) return null

  return (
    <div
      style={{
        background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
        color: '#fff',
        textAlign: 'center',
        padding: '6px 16px',
        fontSize: 13,
        fontWeight: 500,
        gridColumn: '1 / -1',
        letterSpacing: '0.02em',
      }}
    >
      Demo Mode — Using pre-recorded responses. Switch personas and try different queries to see permission enforcement.
      <a
        href="https://github.com/Mansi2221/keystone"
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: '#e0e7ff', marginLeft: 12, textDecoration: 'underline' }}
      >
        View Source
      </a>
    </div>
  )
}
