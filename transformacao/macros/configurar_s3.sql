{% macro configurar_s3() %}
    {% do run_query("load httpfs") %}
    {% do run_query("load iceberg") %}
    {% do run_query("set s3_endpoint='" ~ env_var('S3_HOST', 'seaweedfs:8333') ~ "'") %}
    {% do run_query("set s3_access_key_id='" ~ env_var('S3_ACCESS_KEY', 'leitos') ~ "'") %}
    {% do run_query("set s3_secret_access_key='" ~ env_var('S3_SECRET_KEY', 'leitos-segredo') ~ "'") %}
    {% do run_query("set s3_use_ssl=false") %}
    {% do run_query("set s3_url_style='path'") %}
    {% do run_query("set s3_region='us-east-1'") %}
{% endmacro %}
