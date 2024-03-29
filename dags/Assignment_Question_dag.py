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
            'INSERT INTO assignment_question (assignment_question_id,'
            'created_at,'
            'created_by_id,'
            'hash,'
            'is_deleted,'
            'max_points,'
            'max_marks,'
            'peer_reviewed,'
            'peer_reviewed_by_id,'
            'question_for_assignment_type,'
            'question_title,'
            'question_type,'
            'test_case_count,'
            'verified,'
            'feedback_evaluable,'
            'rating,'
            'difficulty_type,'
            'mandatory,'
            'topic_id,'
            'question_utility_type,'
            'relevance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
            'on conflict (assignment_question_id) do update set peer_reviewed = EXCLUDED.peer_reviewed, '
            'peer_reviewed_by_id = EXCLUDED.peer_reviewed_by_id, '
            'question_for_assignment_type = EXCLUDED.question_for_assignment_type, '
            'question_title = EXCLUDED.question_title, '
            'test_case_count = EXCLUDED.test_case_count, '
            'verified = EXCLUDED.verified, '
            'rating = EXCLUDED.rating, difficulty_type = EXCLUDED.difficulty_type, '
            'mandatory = EXCLUDED.mandatory, '
            'topic_id = EXCLUDED.topic_id, '
            'question_utility_type = EXCLUDED.question_utility_type, '
            'relevance = EXCLUDED.relevance;',
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
                transform_row[20]
            )
        )
    pg_conn.commit()


dag = DAG(
    'assignment_question_dag',
    default_args=default_args,
    description='Assignment Questions raw',
    schedule_interval='30 20 * * *',
    catchup=False
)

create_table = PostgresOperator(
    task_id='create_table',
    postgres_conn_id='postgres_result_db',
    sql='''CREATE TABLE IF NOT EXISTS assignment_question (
            id serial,
            assignment_question_id bigint not null PRIMARY KEY,
            created_at timestamp,
            created_by_id bigint,
            hash text,
            is_deleted boolean,
            max_points int,
            max_marks int,
            peer_reviewed boolean,
            peer_reviewed_by_id bigint,
            question_for_assignment_type integer[],
            question_title text,
            question_type int,
            test_case_count int,
            verified boolean,
            feedback_evaluable boolean,
            rating bigint,
            difficulty_type int,
            mandatory boolean,
            topic_id bigint,
            question_utility_type int,
            relevance int
        );
    ''',
    dag=dag
)

transform_data = PostgresOperator(
    task_id='transform_data',
    postgres_conn_id='postgres_read_replica',
    sql='''select 
    assignments_assignmentquestion.id as assignment_question_id,
    assignments_assignmentquestion.created_at,
    assignments_assignmentquestion.created_by_id,
    assignments_assignmentquestion.hash,
    assignments_assignmentquestion.is_deleted,
    assignments_assignmentquestion.max_points,
    assignments_assignmentquestion.max_marks,
    assignments_assignmentquestion.peer_reviewed,
    assignments_assignmentquestion.peer_reviewed_by_id,
    assignments_assignmentquestion.question_for_assignment_type,
    assignments_assignmentquestion.question_title,
    assignments_assignmentquestion.question_type,
    total_test_cases as test_cases_count,
    assignments_assignmentquestion.verified,
    assignments_assignmentquestion.feedback_evaluable,
    assignments_assignmentquestion.rating, 
    assignments_assignmentquestion.difficulty_type, 
    assignments_assignmentquestiontopicmapping.mandatory, 
    assignments_assignmentquestiontopicmapping.topic_id,
    assignments_assignmentquestiontopicmapping.question_utility_type,
    assignments_assignmentquestiontopicmapping.relevance
from
    assignments_assignmentquestion
left join assignments_assignmentquestiontopicmapping
    on assignments_assignmentquestiontopicmapping.assignment_question_id = assignments_assignmentquestion.id and main_topic = true
left join 
    (select
            assignment_question_id,
            count(distinct id) as total_test_cases
        from
            assignments_assignmentquestiontestcasemapping
        group by 1) test_cases_count on test_cases_count.assignment_question_id = assignments_assignmentquestion.id;
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