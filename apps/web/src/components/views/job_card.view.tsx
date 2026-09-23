import { Clock3 } from 'lucide-react'
import type { ViewRendererProps } from '../view-renderer'

function JobCardView({ spec, jobs }: ViewRendererProps) {
  const job = jobs?.[String(spec.props.job_id)]
  if (!job) return <div className="surface-error" role="alert">Job unavailable in this session.</div>
  return <section className="job-view" aria-label="Submitted job">
    <div className="table-view-heading"><span className="view-kind">Submitted job</span><h3>{String(spec.props.title)}</h3></div>
    <div className="job-status"><Clock3 size={17} />Pending</div>
    <dl className="job-details">
      <dt>Job</dt><dd>{job.job_id}</dd><dt>Application</dt><dd>{job.app_id}</dd>
      <dt>Specimen query</dt><dd>{job.specimen_handle}</dd><dt>Confirmed version</dt><dd>{job.confirmed_version}</dd>
      {Object.entries(job.parameters).map(([name, value]) => <div className="job-parameter" key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>)}
    </dl>
  </section>
}

JobCardView.kind = 'job_card'
JobCardView.version = 1
export default JobCardView