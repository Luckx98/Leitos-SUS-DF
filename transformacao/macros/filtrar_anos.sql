{% macro filtrar_anos(coluna) -%}
    {%- set anos = var('anos', []) -%}
    {%- if anos | length > 0 %}
    and year({{ coluna }}) in ({{ anos | join(', ') }})
    {%- endif %}
{%- endmacro %}
