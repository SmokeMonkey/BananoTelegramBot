import configparser
import logging
import os
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus

import nano

from . import currency, db, social

# Read config and parse constants
config = configparser.ConfigParser()
config.read(os.environ['MY_CONF_DIR'] + '/webhooks.ini')
logging.basicConfig(handlers=[logging.StreamHandler()], level=logging.INFO)
# Set constants
BULLET = u"\u2022"
NODE_IP = config.get('webhooks', 'node_ip')
WALLET = config.get('webhooks', 'wallet')
MIN_TIP = config.get('webhooks', 'min_tip')

# Connect to global functions
rpc = nano.rpc.Client(NODE_IP)
raw_denominator = 10**10


def parse_action(message):
    if message['dm_action'] == '!help' or message[
            'dm_action'] == '/help' or message['dm_action'] == '/start':
        new_pid = os.fork()
        if new_pid == 0:
            try:
                help_process(message)
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    elif message['dm_action'] == '!balance' or message[
            'dm_action'] == '/balance':
        new_pid = os.fork()
        if new_pid == 0:
            try:
                balance_process(message)
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    elif message['dm_action'] == '!register' or message[
            'dm_action'] == '/register':
        new_pid = os.fork()
        if new_pid == 0:
            try:
                register_process(message)
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    elif message['dm_action'] == '!tip' or message['dm_action'] == '/tip':
        new_pid = os.fork()
        if new_pid == 0:
            try:
                redirect_tip_text = (
                    "Tips are processed through public messages now.  Please send this message in group chat in the format "
                    "@NosTipBot !tip 1 @user1.")
                social.send_dm(message['sender_id'], redirect_tip_text)
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    elif message['dm_action'] == '!withdraw' or message[
            'dm_action'] == '/withdraw':
        new_pid = os.fork()
        if new_pid == 0:
            try:
                withdraw_process(message)
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    elif message['dm_action'] == '!account' or message[
            'dm_action'] == '/account':
        new_pid = os.fork()
        if new_pid == 0:
            try:
                account_process(message)
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    else:
        new_pid = os.fork()
        if new_pid == 0:
            try:
                wrong_format_text = (
                    "The command or syntax you sent is not recognized.  Please send !help for a list "
                    "of commands and what they do.")
                social.send_dm(message['sender_id'], wrong_format_text)
                logging.info('unrecognized syntax')
            except Exception as e:
                logging.info("Exception: {}".format(e))
                raise e
            os._exit(0)
        else:
            return '', HTTPStatus.OK

    return '', HTTPStatus.OK


def help_process(message):
    """
    Reply to the sender with help commands
    """
    help_message = (
        "Thank you for using my services @NOSTipBot!  Below is a list of commands, and a description of how you can interact with me:\n\n"
        + BULLET +
        " !help: The NOSTipBot will respond to your DM with a list of commands and their functions. If you forget something, use this to get a hint of how to do it!n\n\n"
        + BULLET +
        " !register: Creates a fresh NOS (XNOS) account address specifically for you.  This is used to store your tips. Make sure to withdraw to a private wallet, as the tip bot is not meant to be a long term storage device for NOS (XNOS).\n\n"
        + BULLET +
        " !balance: This shows you how much funds are in your your account.\n\n"
        + BULLET +
        " !tip: Tips are sent directly to @username on telegram.  Tag @NOSTipBot and mention !tip <amount> <@username>.  EXAMPLE: @NOSTipBot !tip 1 @user will send a 1 NOS (XNOS) tip to another user.\n\n"
        + BULLET +
        " !account: Returns the account number.  You can use this to deposit more NOS (XNOS) to tip from your personal wallet.\n\n"
        + BULLET +
        " !withdraw: Proper usage is !withdraw nos_12345.  This will send the full balance of your tip account to another external NOS (XNOS) account.  Optional: You can include an amount to withdraw by sending !withdraw <amount> <address>.  Example: !withdraw 1 nos_123 would withdraw 1 Nos to account nos_123\n\n"
    )
    social.send_dm(message['sender_id'], help_message)
    logging.info("{}: Help message sent!".format(datetime.now()))


def balance_process(message):
    """
    When the user sends a DM containing !balance, reply with the balance of the account linked with their Twitter ID
    """
    logging.info("{}: In balance process".format(datetime.now()))
    balance_call = (
        "SELECT account, register FROM users WHERE user_id = {} ".format(
            message['sender_id']))
    data = db.get_db_data(balance_call)
    if not data:
        logging.info(
            "{}: User tried to check balance without an account".format(
                datetime.now()))
        balance_message = (
            "There is no account linked to your username.  Please respond with !register to "
            "create an account.")
        social.send_dm(message['sender_id'], balance_message)
    else:
        message['sender_account'] = data[0][0]
        sender_register = data[0][1]

        if sender_register == 0:
            set_register_call = (
                "UPDATE users SET register = 1 WHERE user_id = {} AND register = 0"
                .format(message['sender_id']))
            db.set_db_data(set_register_call)

        currency.receive_pending(message['sender_account'])
        balance_return = rpc.account_balance(
            account="{}".format(message['sender_account']))
        message['sender_balance_raw'] = balance_return['balance']
        message['sender_balance'] = balance_return['balance'] / raw_denominator

        balance_text = "Your balance is {} Nos.".format(
            message['sender_balance'])
        social.send_dm(message['sender_id'], balance_text)
        logging.info("{}: Balance Message Sent!".format(datetime.now()))


def register_process(message):
    """
    When the user sends !register, create an account for them and mark it registered.  If they already have an account
    reply with their account number.
    """
    logging.info("{}: In register process.".format(datetime.now()))
    register_call = (
        "SELECT account, register FROM users WHERE user_id = {}".format(
            message['sender_id']))
    data = db.get_db_data(register_call)

    if not data:
        # Create an account for the user
        sender_account = rpc.account_create(
            wallet="{}".format(WALLET), work=False)
        account_create_call = (
            "INSERT INTO users (user_id, user_name, account, register) "
            "VALUES({}, '{}', '{}',1)".format(message['sender_id'],
                                              message['sender_screen_name'],
                                              sender_account))
        db.set_db_data(account_create_call)
        account_text = "You have successfully registered for an account.  Your account number is:"
        social.send_account_message(account_text, message, sender_account)

        logging.info("{}: Register successful!".format(datetime.now()))

    elif data[0][1] == 0:
        # The user has an account, but needed to register, so send a message to the user with their account
        sender_account = data[0][0]
        account_registration_update = (
            "UPDATE users SET register = 1 WHERE user_id = {} AND "
            "register = 0".format(message['sender_id']))
        db.set_db_data(account_registration_update)

        account_registration_text = "You have successfully registered for an account.  Your account number is:"
        social.send_account_message(account_registration_text, message,
                                    sender_account)

        logging.info(
            "{}: User has an account, but needed to register.  Message sent".
            format(datetime.now()))

    else:
        # The user had an account and already registered, so let them know their account.
        sender_account = data[0][0]
        account_already_registered = "You already have registered your account.  Your account number is:"
        social.send_account_message(account_already_registered, message,
                                    sender_account)

        logging.info(
            "{}: User has a registered account.  Message sent.".format(
                datetime.now()))


def account_process(message):
    """
    If the user sends !account command, reply with their account.  If there is no account, create one, register it
    and reply to the user.
    """

    logging.info("{}: In account process.".format(datetime.now()))
    sender_account_call = (
        "SELECT account, register FROM users WHERE user_id = {}".format(
            message['sender_id']))
    account_data = db.get_db_data(sender_account_call)
    if not account_data:
        sender_account = rpc.account_create(
            wallet="{}".format(WALLET), work=True)
        account_create_call = (
            "INSERT INTO users (user_id, user_name, account, register) "
            "VALUES({}, '{}', '{}',1)".format(message['sender_id'],
                                              message['sender_screen_name'],
                                              sender_account))
        db.set_db_data(account_create_call)

        account_text = "You didn't have an account set up, so I set one up for you.  Your account number is:"
        social.send_account_message(account_text, message, sender_account)

        logging.info("{}: Created an account for the user!".format(
            datetime.now()))

    else:
        sender_account = account_data[0][0]
        sender_register = account_data[0][1]

        if sender_register == 0:
            set_register_call = (
                "UPDATE users SET register = 1 WHERE user_id = {} AND register = 0"
                .format(message['sender_id']))
            db.set_db_data(set_register_call)

        account_text = "Your account number is:"
        social.send_account_message(account_text, message, sender_account)

        logging.info("{}: Sent the user their account number.".format(
            datetime.now()))


def withdraw_process(message):
    """
    When the user sends !withdraw, send their entire balance to the provided account.  If there is no provided account
    reply with an error.
    """
    logging.info('{}: in withdraw process.'.format(datetime.now()))
    # check if there is a 2nd argument
    if 3 >= len(message['dm_array']) >= 2:
        # if there is, retrieve the sender's account and wallet
        withdraw_account_call = (
            "SELECT account FROM users WHERE user_id = {}".format(
                message['sender_id']))
        withdraw_data = db.get_db_data(withdraw_account_call)

        if not withdraw_data:
            withdraw_no_account_text = "You do not have an account.  Respond with !register to set one up."
            social.send_dm(message['sender_id'], withdraw_no_account_text)
            logging.info("{}: User tried to withdraw with no account".format(
                datetime.now()))

        else:
            sender_account = withdraw_data[0][0]
            currency.receive_pending(sender_account)
            balance_return = rpc.account_balance(
                account='{}'.format(sender_account))

            if len(message['dm_array']) == 2:
                receiver_account = message['dm_array'][1].lower()
            else:
                receiver_account = message['dm_array'][2].lower()

            if rpc.validate_account_number(receiver_account) == 0:
                invalid_account_text = (
                    "The account number you provided is invalid.  Please double check and "
                    "resend your request.")
                social.send_dm(message['sender_id'], invalid_account_text)
                logging.info(
                    "{}: The xrb account number is invalid: {}".format(
                        datetime.now(), receiver_account))

            elif balance_return['balance'] == 0:
                no_balance_text = (
                    "You have 0 balance in your account.  Please deposit to your address {} to "
                    "send more tips!".format(sender_account))
                social.send_dm(message['sender_id'], no_balance_text)
                logging.info(
                    "{}: The user tried to withdraw with 0 balance".format(
                        datetime.now()))

            else:
                if len(message['dm_array']) == 3:
                    try:
                        withdraw_amount = Decimal(message['dm_array'][1])
                    except Exception as e:
                        logging.info("{}: withdraw no number ERROR: {}".format(
                            datetime.now(), e))
                        invalid_amount_text = (
                            "You did not send a number to withdraw.  Please resend with the format"
                            "!withdraw <account> or !withdraw <amount> <account>"
                        )
                        social.send_dm(message['sender_id'],
                                       invalid_amount_text)
                        return
                    withdraw_amount_raw = int(
                        withdraw_amount * raw_denominator)
                    if Decimal(withdraw_amount_raw) > Decimal(
                            balance_return['balance']):
                        not_enough_balance_text = (
                            "You do not have that much Nos in your account.  To withdraw your "
                            "full amount, send !withdraw <account>")
                        social.send_dm(message['sender_id'],
                                       not_enough_balance_text)
                        return
                else:
                    withdraw_amount_raw = balance_return['balance']
                    withdraw_amount = balance_return[
                        'balance'] / raw_denominator
                # send the total balance to the provided account
                work = currency.get_pow(sender_account)
                if work == '':
                    logging.info("{}: processed without work".format(
                        datetime.now()))
                    send_hash = rpc.send(
                        wallet="{}".format(WALLET),
                        source="{}".format(sender_account),
                        destination="{}".format(receiver_account),
                        amount=withdraw_amount_raw)
                else:
                    logging.info("{}: processed with work: {}".format(
                        datetime.now(), work))
                    send_hash = rpc.send(
                        wallet="{}".format(WALLET),
                        source="{}".format(sender_account),
                        destination="{}".format(receiver_account),
                        amount=withdraw_amount_raw,
                        work=work)
                logging.info("{}: send_hash = {}".format(
                    datetime.now(), send_hash))
                # respond that the withdraw has been processed
                withdraw_text = ("You have successfully withdrawn {} Nos!".
                                 format(withdraw_amount))
                social.send_dm(message['sender_id'], withdraw_text)
                logging.info("{}: Withdraw processed.  Hash: {}".format(
                    datetime.now(), send_hash))
    else:
        incorrect_withdraw_text = (
            "I didn't understand your withdraw request.  Please resend with !withdraw "
            "<optional:amount> <account>.  Example, !withdraw 1 nos_123 would "
            "withdraw 1 Nos to account nos_123.  Also, !withdraw "
            "nos_123 would withdraw your entire balance to account "
            "nos_123.")
        social.send_dm(message['sender_id'], incorrect_withdraw_text)
        logging.info("{}: User sent a withdraw with invalid syntax.".format(
            datetime.now()))


def tip_process(message, users_to_tip):
    """
    Main orchestration process to handle tips
    """
    logging.info("{}: in tip_process".format(datetime.now()))

    message, users_to_tip = social.set_tip_list(message, users_to_tip)

    message = social.validate_sender(message)
    if message['sender_account'] is None or message['tip_amount'] <= 0:
        return

    message = social.validate_total_tip_amount(message)
    if message['tip_amount'] <= 0:
        return

    for t_index in range(0, len(users_to_tip)):
        currency.send_tip(message, users_to_tip, t_index)

    # Inform the user that all tips were sent.
    if len(users_to_tip) >= 2:
        multi_tip_success = (
            "You have successfully sent your {} Nos tips.".format(
                message['tip_amount_text']))
        social.send_reply(message, multi_tip_success)

    elif len(users_to_tip) == 1:
        tip_success = ("You have successfully sent your {} Nos tip.".format(
            message['tip_amount_text']))
        social.send_reply(message, tip_success)
