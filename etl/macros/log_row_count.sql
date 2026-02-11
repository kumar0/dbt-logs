
{% macro log_row_count() %}

    {% set row_count_query %}
        select count(*) as row_count from {{ this }}
    {% endset %}

    {% set results = run_query(row_count_query) %}

    {% if execute %}
        {% set row_count = results.columns[0].values()[0] %}
        {{ log("ROW_COUNT | " ~ this ~ " | rows: " ~ row_count, info=True) }}
    {% endif %}

{% endmacro %}