import configparser
import logging
import os
from datetime import datetime
from decimal import *

import pymysql

# Read config and parse constants
config = configparser.ConfigParser()
config.read(os.environ['MY_CONF_DIR'] + '/webhooks.ini')
logging.basicConfig(handlers=[logging.StreamHandler()], level=logging.INFO)
# DB connection settings
DB_HOST = config.get('webhooks', 'host')
DB_USER = config.get('webhooks', 'user')
DB_PW = config.get('webhooks', 'password')
DB_SCHEMA = config.get('webhooks', 'schema')
DB_PORT = int(config.get('webhooks', 'port'))
getcontext().prec = 3


def check_db_exist():
    db = pymysql.connect(
        host=DB_HOST, user=DB_USER, passwd=DB_PW, port=DB_PORT)
    with db:
        sql = "SHOW DATABASES LIKE '{}'".format(DB_SCHEMA)
        db_cursor = db.cursor()
        a = db_cursor.execute(sql)
        return a == 1


def create_db():
    db = pymysql.connect(
        host=DB_HOST, user=DB_USER, passwd=DB_PW, port=DB_PORT)
    with db:
        db_cursor = db.cursor()
        sql = 'CREATE DATABASE IF NOT EXISTS {}'.format(DB_SCHEMA)
        db_cursor.execute(sql)
        db.commit()
        logging.info('Created database')


def delete_db():
    try:
        if check_db_exist():
            db = pymysql.connect(
                host=DB_HOST, user=DB_USER, passwd=DB_PW, port=DB_PORT)
            with db:
                db_cursor = db.cursor()
                sql = 'DROP DATABASE {}'.format(DB_SCHEMA)
                db_cursor.execute(sql)
        else:
            logging.info('No db')
    except Exception as e:
        logging.info('Failed removing db: {}'.format(e))
    else:
        logging.info('Deleted database.')
    check_db_exist()


def check_table_exists(table_name):
    db = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PW,
        db=DB_SCHEMA,
        port=DB_PORT,
        use_unicode=True,
        charset="utf8")
    with db:
        db_cursor = db.cursor()
        stmt = "SHOW TABLES LIKE '{}'".format(table_name)
        db_cursor.execute(stmt)
        result = db_cursor.fetchall()
        return result


def execute_sql(sql):
    db = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PW,
        port=DB_PORT,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    with db:
        db_cursor = db.cursor()
        db_cursor.execute(sql)


def drop_table(table_name):
    exist = check_table_exists(table_name)
    sql = 'DROP TABLE {}'.format(table_name)
    try:
        if exist:
            execute_sql(sql)
            logging.info('Dropped table {}'.format(table_name))
        else:
            logging.info('Table {} does not exist'.format(table_name))
    except Exception as e:
        logging.info('Failed dropping table {}, got error {}'.format(
            table_name, e))


def create_tables():
    users_exist = check_table_exists('users')
    if not users_exist:
        # create users table
        sql = """
        CREATE TABLE IF NOT EXISTS users ( 
            user_id INT,
            user_name  CHAR(64),
            account CHAR(128),  
            register SMALLINT)
            """
        execute_sql(sql)
        logging.info("Checking if table was created: {}".format(
            check_table_exists('users')))

    users_exist = check_table_exists('telegram_chat_members')
    if not users_exist:
        # create telegram_chat_members table
        sql = """
        CREATE TABLE IF NOT EXISTS telegram_chat_members (
            chat_id BIGINT,
            chat_name  CHAR(128),
            member_id INT,  
            member_name CHAR(128))
            """
        res = execute_sql(sql)

    users_exist = check_table_exists('tip_list')
    if not users_exist:
        # create tip_list table
        sql = """
        CREATE TABLE IF NOT EXISTS tip_list (
            dm_id INT,
            tx_id  INT,
            processed INT,  
            sender_id INT,  
            receiver_id INT,  
            dm_text CHAR(128),  
            amount INT)
            """
        res = execute_sql(sql)


def get_db_data(db_call, arguments):
    """
    Retrieve data from DB
    """
    db = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        port=DB_PORT,
        passwd=DB_PW,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    with db:
        db_cursor = db.cursor()
        db_cursor.execute(db_call, arguments)
        db_data = db_cursor.fetchall()
        return db_data


def set_db_data(db_call, arguments):
    """
    Enter data into DB
    """
    db = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PW,
        port=DB_PORT,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    try:
        with db:
            db_cursor = db.cursor()
            db_cursor.execute(db_call, arguments)
            logging.info("{}: record inserted into DB".format(datetime.now()))
    except pymysql.ProgrammingError as e:
        logging.info("{}: Exception entering data into database".format(
            datetime.now()))
        logging.info("{}: {}".format(datetime.now(), e))
        raise e


def set_db_data_tip(message, users_to_tip, t_index):
    """
    Special case to update DB information to include tip data
    """
    logging.info("{}: inserting tip into DB.".format(datetime.now()))
    db = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PW,
        port=DB_PORT,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    try:
        with db:
            db_cursor = db.cursor()
            message_text = ' '.join(message['text']).replace('!', '').replace(
                '@', '')
            sql = "INSERT INTO tip_list VALUES ({dm_id}, {tx_id}, 2, {sender_id}, {receiver_id}, '{dm_text}', {amount})".format(
                dm_id=message['id'],
                tx_id=message['tip_id'],
                sender_id=message['sender_id'],
                receiver_id=users_to_tip[t_index]['receiver_id'],
                dm_text=message_text,
                amount=Decimal(message['tip_amount']))
            logging.info('Query: {}'.format(sql))
            db_cursor.execute(sql)
    except Exception as e:
        logging.info("{}: Exception in set_db_data_tip".format(datetime.now()))
        logging.info("{}: {}".format(datetime.now(), e))
        raise e
