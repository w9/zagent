import { Activity, ChartColumn, FileText, Shapes, Table2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const kinds: Record<string, { label: string; icon: LucideIcon }> = {
  table: { label: 'Table', icon: Table2 },
  chart: { label: 'Chart', icon: ChartColumn },
  draft_form: { label: 'Analysis draft', icon: FileText },
  job_card: { label: 'Analysis job', icon: Activity },
  job_grid: { label: 'Analysis jobs', icon: Activity },
}

/** The label and icon that name an artifact kind in cards, the list and the panel header. */
export function artifactKind(kind: string): { label: string; icon: LucideIcon } {
  return kinds[kind] ?? { label: 'Artifact', icon: Shapes }
}
