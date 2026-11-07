import type { QuizQuestion } from '../types/api';

interface Props {
  index: number;
  question: QuizQuestion;
  selected: number | null;
  onChange: (option: number) => void;
}

export default function QuestionCard({ index, question, selected, onChange }: Props) {
  return (
    <fieldset key={index} className="card animate-fade-up">
      <legend className="sr-only">Question {index + 1}</legend>
      <p className="mb-5 text-lg font-bold leading-snug">{index + 1}. {question.question}</p>
      <div className="space-y-3">
        {question.options.map((option, i) => (
          <label key={option} className={`flex cursor-pointer items-center gap-3 rounded-xl border-2 px-4 py-3 transition duration-200 ${selected === i ? 'border-brand-500 bg-brand-50 font-semibold text-brand-800' : 'border-ink-100 hover:border-brand-200 hover:bg-canvas'}`}>
            <input type="radio" className="h-4 w-4 accent-brand-600" name={`question-${index}`} checked={selected === i} onChange={() => onChange(i)} />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
