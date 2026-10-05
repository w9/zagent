import { Dna } from 'lucide-react'

export function Wordmark() {
  return (
    <div className="flex items-center gap-2">
      <Dna aria-hidden className="hidden size-icon-lg text-accent tablet:block" />
      <h1 className="font-serif text-2xl leading-none text-strong">
        Zagent<span className="text-accent">.</span>
      </h1>
    </div>
  )
}
