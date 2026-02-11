{% macro generate_surrogate_key(natural_key, timestamp_field) %}
    cast(abs(hash({{ natural_key }}, cast({{ timestamp_field }} as string))) as bigint)
{% endmacro %}