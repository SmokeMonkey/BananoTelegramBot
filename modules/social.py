import configparser
import logging
import os
from datetime import datetime
from decimal import Decimal

import nano
import pyqrcode
import telegram

from . import currency, db

# Read config and parse constants
config = configparser.ConfigParser()
config.read(os.environ['MY_CONF_DIR'] + '/webhooks.ini')
logging.basicConfig(handlers=[logging.StreamHandler()], level=logging.INFO)
# Telegram API
TELEGRAM_KEY = config.get('webhooks', 'telegram_key')

# Constants
MIN_TIP = config.get('webhooks', 'min_tip')
NODE_IP = config.get('webhooks', 'node_ip')
BOTNAME = config.get('webhooks', 'bot_id_telegram')

# Connect to Telegram
telegram_bot = telegram.Bot(token=TELEGRAM_KEY)

# Connect to node
rpc = nano.rpc.Client(NODE_IP)
raw_denominator = 10**10


def send_dm(receiver, message):
    """
    Send the provided message to the provided receiver
    """

    try:
        telegram_bot.sendMessage(chat_id=receiver, text=message)
    except Exception as e:
        logging.info("{}: Send DM - Telegram ERROR: {}".format(
            datetime.utcnow(), e))
        pass


def check_message_action(message):
    """
    Check to see if there are any key action values mentioned in the message.
    """
    logging.info("{}: in check_message_action.".format(datetime.utcnow()))
    try:
        botname = "@{}".format(BOTNAME).lower()
        message['bot'] = message['text'].index(botname)
        message['action_index'] = message['text'].index("!tip")
    except ValueError:
        message['action'] = None
        return message

    message['action'] = message['text'][message['action_index']].lower()
    message['starting_point'] = message['action_index'] + 1

    return message


def validate_tip_amount(message):
    """
    Validate the message includes an amount to tip, and if that tip amount is greater than the minimum tip amount.
    """
    logging.info("{}: in validate_tip_amount".format(datetime.utcnow()))
    try:
        message['tip_amount'] = Decimal(
            message['text'][message['starting_point']])
    except Exception:
        logging.info("{}: Tip amount was not a number: {}".format(
            datetime.utcnow(), message['text'][message['starting_point']]))
        not_a_number_text = 'Looks like the value you entered to tip was not a number.  You can try to tip ' \
                            'again using the format !tip 1234 @username'
        send_reply(message, not_a_number_text)

        message['tip_amount'] = -1
        return message

    if Decimal(message['tip_amount']) < Decimal(MIN_TIP):
        min_tip_text = (
            "The minimum tip amount is {} Nos.  Please update your tip amount and try again."
            .format(MIN_TIP))
        send_reply(message, min_tip_text)

        message['tip_amount'] = -1
        logging.info("{}: User tipped less than {} Nos.".format(
            datetime.utcnow(), MIN_TIP))
        return message

    try:
        message['tip_amount_raw'] = Decimal(
            message['tip_amount']) * raw_denominator
    except Exception as e:
        logging.info(
            "{}: Exception converting tip_amount to tip_amount_raw".format(
                datetime.utcnow()))
        logging.info("{}: {}".format(datetime.utcnow(), e))
        message['tip_amount'] = -1
        return message

    # create a string to remove scientific notation from small decimal tips
    if str(message['tip_amount'])[0] == ".":
        message['tip_amount_text'] = "0{}".format(str(message['tip_amount']))
    else:
        message['tip_amount_text'] = str(message['tip_amount'])

    return message


def set_tip_list(message, users_to_tip):
    """
    Loop through the message starting after the tip amount and identify any users that were tagged for a tip.  Add the
    user object to the users_to_tip dict to process the tips.
    """
    logging.info("{}: in set_tip_list.".format(datetime.utcnow()))

    logging.info("trying to set tiplist in telegram: {}".format(message))
    for t_index in range(message['starting_point'] + 1, len(message['text'])):
        if len(message['text'][t_index]) > 0:
            if str(message['text'][t_index][0]) == "@" and str(
                    message['text'][t_index]).lower() != (
                        "@" + str(message['sender_screen_name']).lower()):
                check_user_call = "SELECT member_id, member_name FROM telegram_chat_members WHERE chat_id = %s and member_name = %s"
                arguments = (message['chat_id'], message['text'][t_index][1:])

                user_check_data = db.get_db_data(check_user_call, arguments)
                if user_check_data:
                    receiver_id = user_check_data[0][0]
                    receiver_screen_name = user_check_data[0][1]

                    user_dict = {
                        'receiver_id': receiver_id,
                        'receiver_screen_name': receiver_screen_name,
                        'receiver_account': None,
                        'receiver_register': None
                    }
                    users_to_tip.append(user_dict)
                else:
                    logging.info(
                        "User not found in DB: chat ID:{} - member name:{}".
                        format(message['chat_id'],
                               message['text'][t_index][1:]))
                    missing_user_message = (
                        "{} not found in our records.  In order to tip them, they need to be a "
                        "member of the channel.  If they are in the channel, please have them "
                        "send a message in the chat so I can add them. They also need to have Telegram username set up."
                        .format(message['text'][t_index]))
                    send_reply(message, missing_user_message)
                    users_to_tip.clear()
                    return message, users_to_tip

    logging.info("{}: Users_to_tip: {}".format(datetime.utcnow(), users_to_tip))
    message['total_tip_amount'] = message['tip_amount']
    if len(users_to_tip) > 0 and message['tip_amount'] != -1:
        message['total_tip_amount'] *= len(users_to_tip)

    return message, users_to_tip


def validate_sender(message):
    """
    Validate that the sender has an account with the tip bot, and has enough NANO to cover the tip.
    """
    logging.info("{}: validating sender".format(datetime.utcnow()))
    logging.info("sender id: {}".format(message['sender_id']))
    db_call = "SELECT account, register FROM users where user_id = %s"
    arguments = (message['sender_id'])
    sender_account_info = db.get_db_data(db_call, arguments)

    if not sender_account_info:
        no_account_text = (
            "You do not have an account with the bot.  Please send a DM to me with !register to set up "
            "an account.")
        send_reply(message, no_account_text)

        logging.info("{}: User tried to send a tip without an account.".format(
            datetime.utcnow()))
        message['sender_account'] = None
        return message

    message['sender_account'] = sender_account_info[0][0]
    message['sender_register'] = sender_account_info[0][1]

    if message['sender_register'] != 1:
        db_call = "UPDATE users SET register = 1 WHERE user_id = {}".format(
            message['sender_id'])
        db.set_db_data(db_call)

    currency.receive_pending(message['sender_account'])
    message['sender_balance_raw'] = rpc.account_balance(
        account='{}'.format(message['sender_account']))
    message['sender_balance'] = message['sender_balance_raw'][
        'balance'] / raw_denominator

    return message


def validate_total_tip_amount(message):
    """
    Validate that the sender has enough Nano to cover the tip to all users
    """
    logging.info("{}: validating total tip amount".format(datetime.utcnow()))
    if message['sender_balance_raw']['balance'] < (
            message['total_tip_amount'] * raw_denominator):
        not_enough_text = (
            "You do not have enough Nos to cover this {} Nos tip.  Please check your balance by "
            "sending a DM to me with !balance and retry.".format(
                message['total_tip_amount']))
        send_reply(message, not_enough_text)

        logging.info(
            "{}: User tried to send more than in their account.".format(
                datetime.utcnow()))
        message['tip_amount'] = -1
        return message

    return message


def send_reply(message, text):
    telegram_bot.sendMessage(chat_id=message['chat_id'], text=text)


def check_telegram_member(chat_id, chat_name, member_id, member_name):
    check_user_call = "SELECT member_id, member_name FROM telegram_chat_members WHERE chat_id = %s and member_name = %s"
    arguments = (chat_id, member_name)
    user_check_data = db.get_db_data(check_user_call, arguments)

    logging.info("checking if user exists")
    if not user_check_data:
        logging.info("{}: User {}-{} not found in DB, inserting".format(
            datetime.utcnow(), chat_id, member_name))
        new_chat_member_call = (
            "INSERT INTO telegram_chat_members (chat_id, chat_name, member_id, member_name) "
            "VALUES ({}, '{}', {}, '{}')".format(chat_id, chat_name, member_id,
                                                 member_name))
        db.set_db_data(new_chat_member_call)

    return


def send_account_message(account_text, message, account):
    """
    Send a message to the user with their account information.
    """

    send_dm(message['sender_id'], account_text)
    send_dm(message['sender_id'], account)
