allow_k8s_contexts('k3d-zagent-plan9')
if k8s_context() != 'k3d-zagent-plan9':
    fail('Use make cluster; this Tiltfile only targets k3d-zagent-plan9.')
analytics_settings(False)
ci_settings(k8s_grace_period='30s')
disable_snapshots()
docker_prune_settings(disable=True)
state = read_json('.cluster/config.json')
recording_changes = ['services/agent/zagent/cassettes'] if state['mode'] == 'live' else []
watch_settings(ignore=['.cluster', 'docs/evals', '**/test-results', '**/__pycache__', '.pytest_cache', '.ruff_cache'] + recording_changes)
watch_file('deploy/cluster')
custom_build('zagent-backend:plan9', ['python3', 'deploy/cluster/images.py', 'backend'],
    disable_push=True, skips_local_docker=True,
    deps=['pyproject.toml', 'uv.lock', 'services/agent/zagent',
        'apps/web/package.json', 'apps/web/package-lock.json', 'apps/web/scripts',
        'services/agent/Dockerfile', 'deploy/cluster/images.py'],
    live_update=[
        fall_back_on(['pyproject.toml', 'uv.lock', 'services/agent/Dockerfile', 'deploy/cluster/images.py',
            'services/agent/zagent/migrations', 'services/agent/zagent/catalog.json',
            'services/agent/zagent/view_schemas', 'services/agent/zagent/cassettes',
            'services/agent/zagent/job_ui', 'services/agent/zagent/sops',
            'services/agent/zagent/job_worker.py', 'services/agent/zagent/dispatcher.py',
            'services/agent/zagent/executors.py', 'services/agent/zagent/kubernetes_executor.py',
            'services/agent/zagent/jobs.py']),
        sync('services/agent/zagent', '/app/services/agent/zagent'),
    ])
custom_build('zagent-worker:plan9', ['python3', 'deploy/cluster/images.py', 'backend'],
        disable_push=True, skips_local_docker=True, match_in_env_vars=True,
        deps=['pyproject.toml', 'uv.lock', 'services/agent/Dockerfile',
                    'services/agent/zagent/job_worker.py', 'deploy/cluster/images.py'])
custom_build('zagent-web:plan9', ['python3', 'deploy/cluster/images.py', 'web'],
    disable_push=True, skips_local_docker=True,
    deps=['apps/web', 'services/agent/zagent/view_schemas', 'evals/fixtures'],
    live_update=[fall_back_on(['apps/web/package.json', 'apps/web/package-lock.json']),
                 sync('apps/web/src', '/app/apps/web/src'),
                 sync('apps/web/index.html', '/app/apps/web/index.html')])
custom_build('zagent-event-db:plan9', ['python3', 'deploy/cluster/images.py', 'event-db'],
    disable_push=True, skips_local_docker=True, deps=['deploy/cluster/EventDB.Dockerfile'])
k8s_yaml(local(['python3', 'deploy/cluster/manifests.py'], quiet=True,
    env={'ZAGENT_API_IP': state['api_ip'], 'ZAGENT_CLUSTER_MODE': state['mode']}))
k8s_resource('postgres', labels=['clinical'])
k8s_resource('privacy', resource_deps=['postgres'], labels=['clinical'])
for name in ['tools-gateway', 'jobs', 'dispatcher']:
    k8s_resource(name, resource_deps=['privacy'], labels=['clinical'])
k8s_resource('event-db', resource_deps=['privacy'], labels=['neutral'])
k8s_resource('llm-gateway', resource_deps=['privacy'], labels=['agent'])
k8s_resource('kb', labels=['neutral'])
k8s_resource('agent-runtime', resource_deps=['event-db', 'llm-gateway', 'tools-gateway', 'jobs', 'kb'], labels=['agent'])
k8s_resource('bff', resource_deps=['agent-runtime'], labels=['clinical'], port_forwards=[port_forward(8109, 8000, name='API')])
k8s_resource('web', resource_deps=['bff'], labels=['clinical'], port_forwards=[port_forward(5185, 5173, name='Zagent')])
k8s_resource('tempo', labels=['neutral'], port_forwards=[port_forward(3284, 3200, name='Tempo')])
k8s_resource('otel-collector', resource_deps=['tempo'], labels=['neutral'])
k8s_resource('grafana', resource_deps=['tempo'], labels=['neutral'], port_forwards=[port_forward(3285, 3000, name='Grafana')])