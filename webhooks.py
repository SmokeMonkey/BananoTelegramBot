import os
from http import HTTPStatus
import click
import re

from flask import Flask, render_template, request

from modules.orchestration import *
from modules.social import *
from modules.db import *

# Read config and parse constants
config = configparser.ConfigParser()
config.read(os.environ['MY_CONF_DIR'] + '/webhooks.ini')
logging.basicConfig(handlers=[logging.StreamHandler()], level=logging.INFO)

# Telegram API
TELEGRAM_KEY = config.get('webhooks', 'telegram_key')

# IDs
BOT_ID_TELEGRAM = config.get('webhooks', 'bot_id_telegram')
SERVER_URL = config.get('webhooks', 'server_url')

# Set up Flask routing
app = Flask(__name__)


# Creating databases
@app.cli.command('db_init')
def db_init():
    delete_db()
    create_db()
    create_tables()
    logging.info('Succesfully initiated database.')


@app.cli.command('db_create_tables')
def db_init():
    create_tables()
    logging.info('Successfully created tables.')


@app.cli.command('db_drop_table')
@click.argument('name')
def db_drop(name):
    drop_table(name)


# Connect to Telegram
telegram_bot = telegram.Bot(token=TELEGRAM_KEY)


@app.cli.command('telegram_webhook')
def telegram_webhook():
    # 443, 80, 88, 8443
    response = telegram_bot.setWebhook(SERVER_URL)
    if response:
        logging.info("Webhook setup successfully")
    else:
        logging.info("Error {}".format(response))
    return response


# Flask routing
@app.route('/', defaults={'path': ''}, methods=["POST"])
@app.route('/<path:path>', methods=["POST"])
def telegram_event(path):
    try:
        message = {
            # id:                     ID of the received message - Error logged through None value
            # text:                   A list containing the text of the received message, split by ' '
            # sender_account:         Nano account of sender - Error logged through None value
            # sender_register:        Registration status with Tip Bot of sender account
            # sender_balance_raw:     Amount of Nano in sender's account, stored in raw
            # sender_balance:         Amount of Nano in sender's account, stored in Nano

            # action_index:           Location of key action value *(currently !tip only)
            # action:                 Action found in the received message - Error logged through None value

            # starting_point:         Location of action sent via message (currently !tip only)

            # tip_amount:             Value of tip to be sent to receiver(s) - Error logged through -1
            # tip_amount_text:        Value of the tip stored in a string to prevent formatting issues
            # total_tip_amount:       Equal to the tip amount * number of users to tip
            # tip_id:                 ID of the tip, used to prevent double sending of tips.  Comprised of
            #                         message['id'] + index of user in users_to_tip
            # send_hash:              Hash of the send RPC transaction
        }

        users_to_tip = [
            # List including dictionaries for each user to send a tip.  Each index will include
            # the below parameters
            #    receiver_account:       Nano account of receiver
            #    receiver_register:      Registration status with Tip Bot of receiver account
        ]

        request_json = request.get_json()
        logging.info("request_json: {}".format(request_json))

        if 'message' in request_json.keys():
            if request_json['message']['chat']['type'] == 'private':
                logging.info(
                    "Direct message received in Telegram.  Processing.")
                message['sender_id'] = request_json['message']['from']['id']

                message['sender_screen_name'] = request_json['message'][
                        'from']['username']

                message['dm_id'] = request_json['update_id']
                message['text'] = request_json['message']['text']
                message['dm_array'] = message['text'].split(" ")
                message['dm_action'] = message['dm_array'][0].lower() # TODO: use regex!

                logging.info("{}: action identified: {}".format(
                    datetime.now(), message['dm_action']))

                parse_action(message)

            elif (request_json['message']['chat']['type'] == 'supergroup'
                  or request_json['message']['chat']['type'] == 'group'):
                if 'text' in request_json['message']:
                    message['sender_id'] = request_json['message']['from'][
                        'id']

                    message['sender_screen_name'] = request_json['message'][
                        'from']['username']

                    message['id'] = request_json['message']['message_id']
                    message['chat_id'] = request_json['message']['chat']['id']
                    chat_name = re.sub('\W+',' ', request_json['message']['chat'][
                        'title'] )
                    message['chat_name'] = chat_name


                    check_telegram_member(
                        message['chat_id'], message['chat_name'],
                        message['sender_id'], message['sender_screen_name'])

                    message['text'] = request_json['message']['text']
                    message['text'] = message['text'].replace('\n', ' ')
                    message['text'] = message['text'].lower()
                    message['text'] = message['text'].split(' ')

                    message = check_message_action(message)
                    if message['action'] is None:
                        logging.debug(
                            "{}: Mention of nano tip bot without a !tip command."
                            .format(datetime.now()))
                        return '', HTTPStatus.OK

                    message = validate_tip_amount(message)
                    if message['tip_amount'] <= 0:
                        return '', HTTPStatus.OK

                    if message['action'] != -1 and str(
                            message['sender_id']) != str(BOT_ID_TELEGRAM):
                        new_pid = os.fork()
                        if new_pid == 0:
                            try:
                                tip_process(message, users_to_tip)
                            except Exception as e:
                                logging.info("Exception: {}".format(e))
                                raise e

                            os._exit(0)
                        else:
                            return '', HTTPStatus.OK

                elif 'new_chat_member' in request_json['message']:
                    logging.info("new member joined chat, adding to DB")
                    chat_id = request_json['message']['chat']['id']
                    chat_name = request_json['message']['chat']['title']
                    member_id = request_json['message']['new_chat_member'][
                        'id']
                    member_name = request_json['message']['new_chat_member'][
                        'username']

                    new_chat_member_call = (
                        "INSERT INTO telegram_chat_members (chat_id, chat_name, member_id, member_name) "
                        "VALUES ({}, '{}', {}, '{}')".format(
                            chat_id, chat_name, member_id, member_name))
                    set_db_data(new_chat_member_call)

                elif 'left_chat_member' in request_json['message']:
                    chat_id = request_json['message']['chat']['id']
                    chat_name = request_json['message']['chat']['title']
                    member_id = request_json['message']['left_chat_member'][
                        'id']
                    member_name = request_json['message']['left_chat_member'][
                        'username']

                    logging.info(
                        "member {}-{} left chat {}-{}, removing from DB.".
                        format(member_id, member_name, chat_id, chat_name))

                    remove_member_call = (
                        "DELETE FROM telegram_chat_members "
                        "WHERE chat_id = {} AND member_id = {}".format(
                            chat_id, member_id))
                    set_db_data(remove_member_call)

                elif 'group_chat_created' in request_json['message']:
                    chat_id = request_json['message']['chat']['id']
                    chat_name = request_json['message']['chat']['title']
                    member_id = request_json['message']['from']['id']
                    member_name = request_json['message']['from']['username']

                    logging.info(
                        "member {} created chat {}, inserting creator into DB."
                        .format(member_name, chat_name))

                    new_chat_call = (
                        "INSERT INTO telegram_chat_members (chat_id, chat_name, member_id, member_name) "
                        "VALUES ({}, '{}', {}, '{}')".format(
                            chat_id, chat_name, member_id, member_name))
                    set_db_data(new_chat_call)

            else:
                logging.info("In try: request: {}".format(request_json))

    except Exception as e:
        logging.info("In error: request: {}".format(request_json))
        logging.error('Fatal error: {}'.format(e))
    finally:
        logging.info("In finally: request: {}".format(request_json))
        return 'ok'

if __name__ == "__main__":
    app.run()
