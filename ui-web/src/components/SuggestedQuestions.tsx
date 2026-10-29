import { Sparkles } from 'lucide-react'

const QUESTIONS = [
  'What is my salary?',
  'Show me the salary for employee 44',
  'Show me the org chart',
  'Show me all open P1 tickets',
  'What deals are renewing this quarter?',
  'Show me recent messages in #ops-alerts',
  'Show me HR complaints',
]

interface Props {
  onSelect: (question: string) => void
}

export function SuggestedQuestions({ onSelect }: Props) {
  return (
    <div className="suggested-questions">
      <div className="suggested-header">
        <Sparkles size={14} />
        <span>Try asking</span>
      </div>
      <div className="suggested-chips">
        {QUESTIONS.map((q) => (
          <button key={q} className="suggested-chip" onClick={() => onSelect(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
