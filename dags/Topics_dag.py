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
            'INSERT INTO topics (topic_node_id,topic_id,topic_name,'
            'topic_template_id,template_name) '
            'VALUES (%s,%s,%s,%s,%s)'
            'on conflict (topic_node_id) do update set topic_name = EXCLUDED.topic_name,'
            'template_name = EXCLUDED.template_name;',
            (
                transform_row[0],
                transform_row[1],
                transform_row[2],
                transform_row[3],
                transform_row[4]
            )
        )
    pg_conn.commit()

def cleanup_assignment_question_mapping(**kwargs):
    pg_hook_read_replica = PostgresHook(postgres_conn_id='postgres_read_replica')  # Use the read replica connection
    pg_conn_read_replica = pg_hook_read_replica.get_conn()
    pg_cursor_read_replica = pg_conn_read_replica.cursor()

    pg_cursor_read_replica.execute('''
        select 
            technologies_topicnode.id as topic_node_id
        from
            technologies_topic
        join technologies_topicnode
            on technologies_topicnode.topic_id = technologies_topic.id
        join technologies_topictemplate
            on technologies_topictemplate.id = technologies_topicnode.topic_template_id and technologies_topictemplate.course_template = false 
                and technologies_topictemplate.master_template = false and technologies_topictemplate.is_deleted = false
        group by 1
    ''')

    unique_keys = [row[0] for row in pg_cursor_read_replica.fetchall()]
    pg_conn_read_replica.close()

    pg_hook_result_db = PostgresHook(postgres_conn_id='postgres_result_db')
    pg_conn_result_db = pg_hook_result_db.get_conn()
    pg_cursor_result_db = pg_conn_result_db.cursor()

    pg_cursor_result_db.execute(f'''
        DELETE FROM topics
        WHERE topic_node_id NOT IN ({','.join(['%s'] * len(unique_keys))})
    ''', unique_keys)

    pg_conn_result_db.commit()


dag = DAG(
    'Topics_and_Template_mapping',
    default_args=default_args,
    description='Topics and template mapping',
    schedule_interval='30 20 * * *',
    catchup=False
)

create_table = PostgresOperator(
    task_id='create_table',
    postgres_conn_id='postgres_result_db',
    sql='''CREATE TABLE IF NOT EXISTS topics (
            id serial,
            topic_node_id bigint not null PRIMARY KEY,
            topic_id bigint ,
            topic_name varchar(128),
            topic_template_id int,
            template_name varchar(128)
        );
    ''',
    dag=dag
)

transform_data = PostgresOperator(
    task_id='transform_data',
    postgres_conn_id='postgres_read_replica',
    sql='''select 
    technologies_topicnode.id as topic_node_id,
    technologies_topic.id as topic_id,
    technologies_topic.title as topic_name,
    technologies_topictemplate.id as topic_template_id,
    technologies_topictemplate.title as template_name
from
    technologies_topic
join technologies_topicnode
    on technologies_topicnode.topic_id = technologies_topic.id
join technologies_topictemplate
    on technologies_topictemplate.id = technologies_topicnode.topic_template_id and technologies_topictemplate.course_template = false 
        and technologies_topictemplate.master_template = false and technologies_topictemplate.is_deleted = false
group by 1,2,3,4,5;
        ''',
    dag=dag
)

extract_python_data = PythonOperator(
    task_id='extract_python_data',
    python_callable=extract_data_to_nested,
    provide_context=True,
    dag=dag
)

cleanup_data = PythonOperator(
    task_id='cleanup_data',
    python_callable=cleanup_assignment_question_mapping,
    provide_context=True,
    dag=dag
)

create_table >> transform_data >> extract_python_data >> cleanup_data