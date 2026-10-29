import { Columns3 } from 'lucide-react'
import type { DemoUser, Principal } from '../types'
import { ROLE_COLORS } from '../theme'
import { getTokenExpiry } from '../api'

/** Keys for the 4 pinned demo personas. */
const PINNED_KEYS = ['contractor', 'ops_manager', 'hr_partner', 'ceo']

interface Props {
  demoUsers: DemoUser[]
  currentUserKey: string | null
  principal: Principal | null
  onSelectUser: (key: string) => void
  compareMode: boolean
  onToggleCompare: () => void
}

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

function expiryLabel(): string {
  const exp = getTokenExpiry()
  if (!exp) return 'no token'
  const mins = Math.max(0, Math.round((exp - Date.now()) / 60_000))
  return `expires in ${mins}m`
}

export function PeopleRail({ demoUsers, currentUserKey, principal, onSelectUser, compareMode, onToggleCompare }: Props) {
  const pinned = PINNED_KEYS.map((k) => demoUsers.find((u) => u.key === k)).filter(Boolean) as DemoUser[]
  const rest = demoUsers.filter((u) => !PINNED_KEYS.includes(u.key))

  return (
    <aside className="people-rail">
      {/* Identity card */}
      {principal && (
        <div className="identity-card">
          <span className="identity-label">Current Subject</span>
          <span className="identity-name">{principal.name || principal.employee_id}</span>
          <span className="identity-title">{principal.title || principal.role}</span>
          <div className="identity-meta">
            <div className="identity-meta-row">
              <span className="label">Role</span>
              <span className={`role-badge ${principal.role}`}>{principal.role.replace(/_/g, ' ')}</span>
            </div>
            <div className="identity-meta-row">
              <span className="label">Dept</span>
              <span>{principal.department}</span>
            </div>
            <div className="identity-meta-row">
              <span className="label">Token</span>
              <span className="identity-expiry">{expiryLabel()}</span>
            </div>
          </div>
          {principal.groups.length > 0 && (
            <div className="identity-groups">
              {principal.groups.map((g) => (
                <span key={g} className="group-pill">{g}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Compare switch */}
      <button className={`compare-switch ${compareMode ? 'active' : ''}`} onClick={onToggleCompare}>
        <Columns3 size={14} />
        <span>Compare Roles</span>
      </button>

      {/* Pinned personas */}
      <div className="section-label">Demo Personas</div>
      <div className="user-list">
        {pinned.map((u) => (
          <UserCard key={u.key} user={u} active={currentUserKey === u.key} onSelect={onSelectUser} />
        ))}
      </div>

      {/* Rest */}
      {rest.length > 0 && (
        <>
          <div className="section-label">More Employees</div>
          <div className="user-list">
            {rest.map((u) => (
              <UserCard key={u.key} user={u} active={currentUserKey === u.key} onSelect={onSelectUser} />
            ))}
          </div>
        </>
      )}
    </aside>
  )
}

function UserCard({ user, active, onSelect }: { user: DemoUser; active: boolean; onSelect: (key: string) => void }) {
  const color = ROLE_COLORS[user.role] || '#6b7280'
  return (
    <button
      className={`user-card ${active ? 'active' : ''}`}
      onClick={() => onSelect(user.key)}
      style={{ borderLeftColor: active ? undefined : color }}
    >
      <div className="user-avatar" style={{ background: color }}>
        {initials(user.name || user.key)}
      </div>
      <div className="user-card-info">
        <span className="user-card-name">{user.name}</span>
        <span className="user-card-role">
          {user.title || user.description} &middot; {user.role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
        </span>
      </div>
    </button>
  )
}
