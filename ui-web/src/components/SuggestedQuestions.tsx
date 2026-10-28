import { Sparkles } from 'lucide-react'

const QUESTIONS = [
  'What is my salary?',
  'Show me all open P1 tickets',
  'What are the Halcyon board minutes about?',
  'Search for employees in Engineering',
  'What deals are renewing this quarter?',
  'Show me recent messages in #ops-alerts',
  'What is the average salary in the Engineering department?',
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
