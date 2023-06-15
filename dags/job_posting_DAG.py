from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 3, 16),
}

def extract_data_to_nested(**kwargs):
    def clean_input(data_type, data_value):
        if data_type == 'string':
            return 'null' if not data_value else f'\"{data_value}\"'
        elif data_type == 'datetime':
            return 'null' if not data_value else f'CAST(\'{data_value}\' As TIMESTAMP)'
        else:
            return data_value

    pg_hook = PostgresHook(postgres_conn_id='postgres_result_db')
    pg_conn = pg_hook.get_conn()
    pg_cursor = pg_conn.cursor()
    ti = kwargs['ti']
    transform_data_output = ti.xcom_pull(task_ids='transform_data')
    for transform_row in transform_data_output:
        pg_cursor.execute(
            'INSERT INTO job_postings (table_unique_key,skills,company,max_ctc,min_ctc,job_role,job_type,job_title,'
            'department,job_source,is_duplicate,job_location,raw_response,max_experience,min_experience,'
            'relevancy_score,job_description_url,job_description_raw_text,job_description_url_without_job_id,'
            '_airbyte_ab_id,_airbyte_emitted_at,_airbyte_normalized_at,_airbyte_job_openings_hashid,'
            '_airbyte_unique_key,number_of_openings)'
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
            'on conflict (table_unique_key) do update setskills=EXCLUDED.skills,company=EXCLUDED.company,'
            'max_ctc=EXCLUDED.max_ctc,min_ctc=EXCLUDED.min_ctc,job_role=EXCLUDED.job_role,'
            'job_type=EXCLUDED.job_type,job_title=EXCLUDED.job_title,department=EXCLUDED.department,'
            'job_source=EXCLUDED.job_source,is_duplicate=EXCLUDED.is_duplicate,job_location=EXCLUDED.job_location,'
            'raw_response=EXCLUDED.raw_response,max_experience=EXCLUDED.max_experience,'
            'min_experience=EXCLUDED.min_experience,relevancy_score=EXCLUDED.relevancy_score,'
            'job_description_url=EXCLUDED.job_description_url,job_description_raw_text=EXCLUDED.job_description_raw_text,'
            'job_description_url_without_job_id=EXCLUDED.job_description_url_without_job_id,'
            '_airbyte_ab_id=EXCLUDED._airbyte_ab_id,_airbyte_emitted_at=EXCLUDED._airbyte_emitted_at,'
            '_airbyte_normalized_at=EXCLUDED._airbyte_normalized_at,'
            '_airbyte_job_openings_hashid=EXCLUDED._airbyte_job_openings_hashid,'
            '_airbyte_unique_key=EXCLUDED._airbyte_unique_key,number_of_openings=EXCLUDED.number_of_openings ;',
            (
                transform_row[0],
                transform_row[1],
                transform_row[2],
                transform_row[3],
                transform_row[4],
                transform_row[5],
                transform_row[6],
                transform_row[7],
                transform_row[8],
                transform_row[9],
                transform_row[10],
                transform_row[11],
                transform_row[12],
                transform_row[13],
                transform_row[14],
                transform_row[15],
                transform_row[16],
                transform_row[17],
                transform_row[18],
                transform_row[19],
                transform_row[20],
                transform_row[21],
                transform_row[22],
                transform_row[23],
            )
        )
    pg_conn.commit()


dag = DAG(
    'Job_Posting_DAG',
    default_args=default_args,
    description='A DAG for Job Posting data from Job Posting Analytics DB',
    schedule_interval='30 15 * * *',
    catchup=False
)

create_table = PostgresOperator(
    task_id='create_table',
    postgres_conn_id='postgres_result_db',
    sql='''CREATE TABLE IF NOT EXISTS job_postings (
            id serial,
            table_unique_key varchar(200) not null PRIMARY KEY,
            skills JSONB,
            company varchar(200),
            max_ctc real,
            min_ctc real,
            job_role varchar(200),
            job_type varchar(200),
            job_title varchar(200), 
            department varchar(200),
            job_source varchar(50),
            is_duplicate boolean,
            job_location  varchar(200),
            raw_response JSONB,
            max_experience int,
            min_experience int,
            relevancy_score int,
            job_description_url  varchar(500),
            job_description_raw_text varchar(35000),
            job_description_url_without_job_id varchar(400),
            _airbyte_ab_id varchar(50),
            _airbyte_emitted_at DATE,
            _airbyte_normalized_at DATE,
            _airbyte_job_openings_hashid varchar(200),
            _airbyte_unique_key varchar(200),
            number_of_openings int
        );
    ''',
    dag=dag
)

transform_data = PostgresOperator(
    task_id='transform_data',
    postgres_conn_id='postgres_job_posting',
    sql='''select
            distinct concat(_airbyte_unique_key,_airbyte_job_openings_hashid,_airbyte_ab_id) as table_unique_key,
            job_openings.skills,
            job_openings.company,
            job_openings.max_ctc,
            job_openings.min_ctc,
            job_openings.job_role,
            job_openings.job_type,
            job_openings.job_title,
            job_openings.department,
            job_openings.job_source,
            job_openings.is_duplicate,
            job_openings.job_location,
            job_openings.raw_response,
            job_openings.max_experience,
            job_openings.min_experience,
            job_openings.relevancy_score,
            job_openings.job_description_url,
            job_openings.job_description_raw_text,
            job_openings.job_description_url_without_job_id,
            job_openings._airbyte_ab_id,
            date(job_openings._airbyte_emitted_at) as _airbyte_emitted_at,
            date(job_openings._airbyte_normalized_at) as _airbyte_normalized_at,
            job_openings._airbyte_job_openings_hashid,
            job_openings._airbyte_unique_key,
            raw_response -> 'vacancy' as number_of_openings
            from job_openings;
        ''',
    dag=dag
)

extract_python_data = PythonOperator(
    task_id='extract_python_data',
    python_callable=extract_data_to_nested,
    provide_context=True,
    dag=dag
)

create_table >> transform_data >> extract_python_data