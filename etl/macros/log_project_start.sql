
{% macro log_project_start() %}

    {% set glue_session_id = env_var('GLUE_SESSION_ID', 'unknown') %}
    {% set worker_type     = env_var('WORKER_TYPE', 'G.1X') %}
    {% set num_workers     = env_var('NUM_WORKERS', '3') %}
    {% set aws_profile     = env_var('AWS_PROFILE', 'mondayskills.development') %}
    {% set aws_region      = env_var('AWS_REGION', 'us-east-1') %}

    {{ log(
        '{"event":"on_run_start"'
        ~ ',"glue_session_id":"' ~ glue_session_id ~ '"'
        ~ ',"worker_type":"' ~ worker_type ~ '"'
        ~ ',"num_workers":' ~ num_workers
        ~ ',"aws_profile":"' ~ aws_profile ~ '"'
        ~ ',"aws_region":"' ~ aws_region ~ '"'
        ~ ',"dbt_version":"' ~ dbt_version ~ '"'
        ~ ',"project_name":"' ~ project_name ~ '"'
        ~ ',"target_name":"' ~ target.name ~ '"'
        ~ ',"target_schema":"' ~ target.schema ~ '"'
        ~ '}',
        info=True
    ) }}

{% endmacro %}