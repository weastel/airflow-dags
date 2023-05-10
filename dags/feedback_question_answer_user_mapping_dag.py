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
            'INSERT INTO feedback_form_all_responses (table_unique_key,'
            'feedback_form_user_mapping_id,user_id,feedback_form_id,'
            'course_id,feedback_question_id, created_at, completed_at,'
            'entity_content_type_id,entity_object_id,feedback_answer)'
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
            'on conflict (table_unique_key) do update set feedback_form_user_mapping_id = EXCLUDED.feedback_form_user_mapping_id,'
            'user_id = EXCLUDED.user_id,'
            'feedback_form_id = EXCLUDED.feedback_form_id,'
            'course_id = EXCLUDED.course_id,'
            'feedback_question_id = EXCLUDED.feedback_question_id,'
            'created_at = EXCLUDED.created_at,'
            'completed_at = EXCLUDED.completed_at,'
            'entity_content_type_id = EXCLUDED.entity_content_type_id,'
            'entity_object_id = EXCLUDED.entity_object_id,'
            'feedback_answer = EXCLUDED.feedback_answer;',
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
                transform_row[10]
            )
        )
    pg_conn.commit()


dag = DAG(
    'feedback_question_answer_user_mapping_dag',
    default_args=default_args,
    description='per user per feedback question response ',
    schedule_interval='0 5 * * *',
    catchup=False,
    max_active_runs=1
)

create_table = PostgresOperator(
    task_id='create_table',
    postgres_conn_id='postgres_result_db',
    sql='''CREATE TABLE IF NOT EXISTS feedback_form_all_responses (
            table_unique_key double precision not null PRIMARY KEY,
            feedback_form_user_mapping_id bigint,
            user_id bigint,
            feedback_form_id bigint,
            course_id int,
            feedback_question_id int,
            created_at timestamp,
            completed_at timestamp,
            entity_content_type_id int,
            entity_object_id bigint,
            feedback_answer varchar(60000)
    );
    ''',
    dag=dag
)

transform_data = PostgresOperator(
    task_id='transform_data',
    postgres_conn_id='postgres_read_replica',
    sql='''Select  
    *
from

    (with raw as
    
        (Select
            feedback_feedbackformusermapping.id as feedback_form_user_mapping_id,
            feedback_feedbackformusermapping.filled_by_id as user_id,
            feedback_feedbackform.id as feedback_form_id,
            feedback_feedbackformusermapping.course_id,
            feedback_feedbackquestion.id as feedback_question_id,
            feedback_feedbackformusermapping.created_at,
            feedback_feedbackformusermapping.completed_at,
            feedback_feedbackformusermapping.entity_content_type_id,
            feedback_feedbackformusermapping.entity_object_id,
            
            case 
                when feedback_feedbackanswer.text is null then feedback_feedbackformuserquestionanswermapping.other_answer
                else feedback_feedbackanswer.text 
            end as feedback_answer
            
        from
            feedback_feedbackformusermapping
        
        left join feedback_feedbackform
            on feedback_feedbackform.id = feedback_feedbackformusermapping.feedback_form_id
        
        left join feedback_feedbackformuserquestionanswermapping
            on feedback_feedbackformusermapping.id = feedback_feedbackformuserquestionanswermapping.feedback_form_user_mapping_id
        
        left join feedback_feedbackformuserquestionanswerm2m
            on feedback_feedbackformuserquestionanswermapping.id = feedback_feedbackformuserquestionanswerm2m.feedback_form_user_question_answer_mapping_id
        
        left join feedback_feedbackanswer
            on feedback_feedbackformuserquestionanswerm2m.feedback_answer_id = feedback_feedbackanswer.id
            
        left join feedback_feedbackquestion
            on feedback_feedbackformuserquestionanswermapping.feedback_question_id = feedback_feedbackquestion.id)
        
        
    select
        cast(concat(feedback_form_user_mapping_id, feedback_question_id, row_number() over(order by feedback_answer)) as bigint) as table_unique_key,
        raw.*
    from
        raw) final_query;
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