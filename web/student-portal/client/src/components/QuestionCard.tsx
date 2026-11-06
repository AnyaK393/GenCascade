import type { QuizQuestion } from '../types/api';

interface Props {
  index: number;
  question: QuizQuestion;
  selected: number | null;
  onChange: (option: number) => void;
}

export default function QuestionCard({ index, question, selected, onChange }: Props) {
  return (
    <fieldset className="rounded-xl bg-white p-4 shadow-sm">
      <legend className="sr-only">Question {index + 1}</legend>
      <p className="mb-3 font-medium">{index + 1}. {question.question}</p>
      <div className="space-y-2">
        {question.options.map((option, i) => (
          <label key={option} className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 ${selected === i ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200'}`}>
            <input type="radio" name={`question-${index}`} checked={selected === i} onChange={() => onChange(i)} />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
