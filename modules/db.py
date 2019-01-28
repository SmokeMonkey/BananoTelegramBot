import configparser
import logging
import MySQLdb
from datetime import datetime
from decimal import *

# Set Log File
logging.basicConfig(
    handlers=[
        logging.FileHandler('/root/webhooks/webhooks.log', 'a', 'utf-8')
    ],
    level=logging.INFO)

# Read config and parse constants
config = configparser.ConfigParser()
config.read('/root/webhooks/webhookconfig.ini')

# DB connection settings
DB_HOST = config.get('webhooks', 'host')
DB_USER = config.get('webhooks', 'user')
DB_PW = config.get('webhooks', 'password')
DB_SCHEMA = config.get('webhooks', 'schema')


def get_db_data(db_call):
    """
    Retrieve data from DB
    """
    db = MySQLdb.connect(
        host=DB_HOST,
        port=3306,
        user=DB_USER,
        passwd=DB_PW,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    db_cursor = db.cursor()
    db_cursor.execute(db_call)
    db_data = db_cursor.fetchall()
    db_cursor.close()
    db.close()
    return db_data


def set_db_data(db_call):
    """
    Enter data into DB
    """
    db = MySQLdb.connect(
        host=DB_HOST,
        port=3306,
        user=DB_USER,
        passwd=DB_PW,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    try:
        db_cursor = db.cursor()
        db_cursor.execute(db_call)
        db.commit()
        db_cursor.close()
        db.close()
        logging.info("{}: record inserted into DB".format(datetime.now()))
    except MySQLdb.ProgrammingError as e:
        logging.info("{}: Exception entering data into database".format(
            datetime.now()))
        logging.info("{}: {}".format(datetime.now(), e))
        raise e


def set_db_data_tip(message, users_to_tip, t_index):
    """
    Special case to update DB information to include tip data
    """
    logging.info("{}: inserting tip into DB.".format(datetime.now()))
    db = MySQLdb.connect(
        host=DB_HOST,
        port=3306,
        user=DB_USER,
        passwd=DB_PW,
        db=DB_SCHEMA,
        use_unicode=True,
        charset="utf8")
    try:
        db_cursor = db.cursor()
        db_cursor.execute(
            "INSERT INTO tip_list (dm_id, tx_id, processed, sender_id, receiver_id, system, dm_text, amount)"
            " VALUES (%s, %s, 2, %s, %s, %s, %s, %s)",
            (message['id'], message['tip_id'], message['sender_id'],
             users_to_tip[t_index]['receiver_id'], message['system'],
             message['text'], Decimal(message['tip_amount'])))
        db.commit()
        db_cursor.close()
        db.close()
    except Exception as e:
        logging.info("{}: Exception in set_db_data_tip".format(datetime.now()))
        logging.info("{}: {}".format(datetime.now(), e))
        raise e
