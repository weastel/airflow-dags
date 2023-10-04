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
    pg_hook = PostgresHook(postgres_conn_id='postgres_result_db')
    pg_conn = pg_hook.get_conn()
    pg_cursor = pg_conn.cursor()
    ti = kwargs['ti']
    transform_data_output = ti.xcom_pull(task_ids='transform_data')
    for transform_row in transform_data_output:
        pg_cursor.execute(
            'INSERT INTO course_user_point_mapping (table_unique_key,'
            'course_id,'
            'course_name,'
            'course_start_timestamp,'
            'course_end_timestamp,'
            'user_id,'
            'created_at,'
            'content_type,'
            'mcq_course_user_mapping_id,'
            'lecture_id,'
            'assignment_course_user_question_mapping_id,'
            'one_to_one_id,'
            'milestone_user_question_mapping_id,'
            'points,'
            'is_deleted,'
            'points_version,'
            'topic_id,'
            'point_type)'
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
            'on conflict (table_unique_key) do update set course_name = EXCLUDED.course_name,'
            'course_start_timestamp = EXCLUDED.course_start_timestamp,'
            'course_end_timestamp = EXCLUDED.course_end_timestamp,'
            'created_at = EXCLUDED.created_at,'
            'points = EXCLUDED.points,'
            'is_deleted = EXCLUDED.is_deleted,'
            'topic_id = EXCLUDED.topic_id,'
            'point_type = EXCLUDED.point_type;',
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
            )
        )
    pg_conn.commit()


dag = DAG(
    'course_user_point_mapping_dag',
    default_args=default_args,
    description='course user points mapping dag',
    schedule_interval='0 21 * * *',
    catchup=False
)

create_table = PostgresOperator(
    task_id='create_table',
    postgres_conn_id='postgres_result_db',
    sql='''CREATE TABLE IF NOT EXISTS course_user_point_mapping (
            id serial,
            table_unique_key text NOT NULL PRIMARY KEY,
            course_id bigint,
            course_name text,
            course_start_timestamp timestamp,
            course_end_timestamp timestamp,
            user_id bigint,
            created_at timestamp, 
            content_type text,
            mcq_course_user_mapping_id bigint,
            lecture_id bigint,
            assignment_course_user_question_mapping_id bigint,
            one_to_one_id bigint,
            milestone_user_question_mapping_id bigint,
            points int,
            is_deleted boolean,
            points_version text, 
            topic_id int, 
            point_type int
        );
    ''',
    dag=dag
)

transform_data = PostgresOperator(
    task_id='transform_data',
    postgres_conn_id='postgres_read_replica',
    sql='''
        select 
            concat(courses_courseuserpointmapping.user_id,'_', courses_courseuserpointmapping.object_id, '_', courses_courseuserpointmapping.content_type_id, '_', version) as table_unique_key,
            courses_course.id as course_id,
            courses_course.title as course_name,
            courses_course.start_timestamp as course_start_timestamp,
            courses_course.end_timestamp as course_end_timestamp, 
            courses_courseuserpointmapping.user_id,
            courses_courseuserpointmapping.created_at,
            case
                when content_type_id = 26 then 'Assessments'
                when content_type_id = 46 then 'Lectures'
                when content_type_id = 64 then 'Assignments'
                when content_type_id = 100 then 'One to One'
                when content_type_id = 119 then 'Arena'
            end as content_type,
            case
                when content_type_id = 26 then courses_courseuserpointmapping.object_id end as mcq_course_user_mapping_id,
            case    
                when content_type_id = 46 then courses_courseuserpointmapping.object_id end as lecture_id,
            case    
                when content_type_id = 64 then courses_courseuserpointmapping.object_id end as assignment_course_user_question_mapping_id,
            case    
                when content_type_id = 100 then courses_courseuserpointmapping.object_id end as one_to_one_id,
            case    
                when content_type_id = 119 then courses_courseuserpointmapping.object_id end as milestone_user_question_mapping_id,
            courses_courseuserpointmapping.points,
            is_deleted,
            case
                when version = 1 then 'Original'
                when version = 2 then 'XP'
            end as points_version,
            topic_id, 
            point_type
        from
            courses_courseuserpointmapping
        left join courses_course
            on courses_course.id = courses_courseuserpointmapping.course_id
        left join courses_courseusermapping
            on courses_courseusermapping.course_id = courses_course.id
                and courses_courseusermapping.user_id = courses_courseuserpointmapping.user_id
        group by 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18;
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