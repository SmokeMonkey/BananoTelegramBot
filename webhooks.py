from http import HTTPStatus

from flask import Flask, render_template, request

from modules.orchestration import *
from modules.social import *

# Set Log File
logging.basicConfig(
    handlers=[
        logging.FileHandler('/root/webhooks/webhooks.log', 'a', 'utf-8')
    ],
    level=logging.INFO)

# Read config and parse constants
config = configparser.ConfigParser()
config.read('/root/webhooks/webhookconfig.ini')

# Telegram API
TELEGRAM_KEY = config.get('webhooks', 'telegram_key')

# IDs
BOT_ID_TELEGRAM = config.get('webhooks', 'bot_id_telegram')

# Set up Flask routing
app = Flask(__name__, template_folder='/var/www/html')

# Connect to Telegram
telegram_bot = telegram.Bot(token=TELEGRAM_KEY)

# Flask routing


@app.route('/tutorial')
@app.route('/tutorial.html')
def tutorial():
    return render_template('tutorial.html')


@app.route('/about')
@app.route('/about.html')
def about():
    btc_energy = 887000
    nano_energy = 0.112
    total_energy, checked_blocks = get_energy(nano_energy)

    btc_vs_nano = round((total_energy / btc_energy), 3)

    total_energy_formatted = '{:,}'.format(total_energy)
    btc_energy_formatted = '{:,}'.format(btc_energy)
    checked_blocks_formatted = '{:,}'.format(checked_blocks)

    return render_template(
        'about.html',
        btc_energy=btc_energy_formatted,
        nano_energy=nano_energy,
        btc_vs_nano=btc_vs_nano,
        total_energy=total_energy_formatted,
        checked_blocks=checked_blocks_formatted)


@app.route('/contact')
@app.route('/contact.html')
def contact():
    return render_template('contact.html')


@app.route('/contact-form-handler')
@app.route('/contact-form-handler.php')
def contacthandler():
    return render_template('contact-form-handler.php')


@app.route('/contact-form-thank-you')
@app.route('/contact-form-thank-you.html')
def thanks():
    return render_template('contact-form-thank-you.html')


@app.route('/tippers')
@app.route('/tippers.html')
def tippers():
    largest_tip = ("SELECT user_name, amount, account, a.system, timestamp "
                   "FROM tip_bot.tip_list AS a, tip_bot.users AS b "
                   "WHERE user_id = sender_id "
                   "AND user_name IS NOT NULL "
                   "AND processed = 2 "
                   "AND user_name != 'mitche50' "
                   "AND amount = (select max(amount) "
                   "FROM tip_bot.tip_list) "
                   "ORDER BY timestamp DESC "
                   "LIMIT 1;")

    tippers_call = (
        "SELECT user_name AS 'screen_name', sum(amount) AS 'total_tips', account, b.system "
        "FROM tip_bot.tip_list AS a, tip_bot.users AS b "
        "WHERE user_id = sender_id "
        "AND user_name IS NOT NULL "
        "AND receiver_id IN (SELECT user_id FROM tip_bot.users)"
        "GROUP BY sender_id "
        "ORDER BY sum(amount) DESC "
        "LIMIT 15")

    tipper_table = get_db_data(tippers_call)
    top_tipper = get_db_data(largest_tip)
    top_tipper_date = top_tipper[0][4].date()
    return render_template(
        'tippers.html',
        tipper_table=tipper_table,
        top_tipper=top_tipper,
        top_tipper_date=top_tipper_date)


@app.route('/tiplist')
def tip_list():
    tip_list_call = (
        "SELECT t1.user_name AS 'Sender ID', t2.user_name AS 'Receiver ID', t1.amount, "
        "t1.account AS 'Sender Account', t2.account AS 'Receiver Account', t1.system, t1.timestamp "
        "FROM "
        "(SELECT user_name, amount, account, a.system, timestamp "
        "FROM tip_bot.tip_list AS a, tip_bot.users AS b "
        "WHERE user_id = sender_id "
        "AND user_name IS NOT NULL "
        "AND processed = 2 "
        "AND user_name != 'mitche50' "
        "ORDER BY timestamp desc "
        "LIMIT 50) AS t1 "
        "JOIN "
        "(SELECT user_name, account, timestamp "
        "FROM tip_bot.tip_list, tip_bot.users "
        "WHERE user_id = receiver_id "
        "AND user_name IS NOT NULL "
        "AND processed = 2 "
        "ORDER BY timestamp DESC "
        "LIMIT 50) AS t2 "
        "ON t1.timestamp = t2.timestamp")
    tip_list_table = get_db_data(tip_list_call)
    print(tip_list_table)
    return render_template('tiplist.html', tip_list_table=tip_list_table)


@app.route('/')
@app.route('/index')
@app.route('/index.html')
def index():
    r = requests.get('https://api.coinmarketcap.com/v2/ticker/1567/')
    rx = r.json()
    price = round(rx['data']['quotes']['USD']['price'], 2)

    total_tipped_nano = (
        "SELECT system, sum(amount) AS total "
        "FROM tip_bot.tip_list "
        "WHERE receiver_id IN (SELECT user_id FROM tip_bot.users) "
        "GROUP BY system "
        "ORDER BY total DESC")

    total_tipped_number = (
        "SELECT system, count(system) AS notips "
        "FROM tip_bot.tip_list "
        "WHERE receiver_id IN (SELECT user_id FROM tip_bot.users)"
        "GROUP BY system "
        "ORDER BY notips DESC")

    total_tipped_nano_table = get_db_data(total_tipped_nano)
    total_tipped_number_table = get_db_data(total_tipped_number)
    total_value_usd = round(total_tipped_number_table[0][1] * price, 2)

    logging.info("total_value_usd: {}".format(total_value_usd))
    logging.info(
        "total_tipped_nano_table = {}".format(total_tipped_nano_table))
    logging.info(
        "total_tipped_number_table = {}".format(total_tipped_number_table))
    return render_template(
        'index.html',
        total_tipped_nano_table=total_tipped_nano_table,
        total_tipped_number_table=total_tipped_number_table,
        total_value_usd=total_value_usd,
        price=price)


@app.route('/webhooks/telegram/set_webhook')
def telegram_webhook():
    response = telegram_bot.setWebhook(
        'https://nanotipbot.com/webhooks/telegram')
    if response:
        return "Webhook setup successfully"
    else:
        return "Error {}".format(response)


@app.route('/webhooks/telegram', methods=["POST"])
def telegram_event():
    message = {
        # id:                     ID of the received tweet - Error logged through None value
        # text:                   A list containing the text of the received tweet, split by ' '
        # sender_account:         Nano account of sender - Error logged through None value
        # sender_register:        Registration status with Tip Bot of sender account
        # sender_balance_raw:     Amount of Nano in sender's account, stored in raw
        # sender_balance:         Amount of Nano in sender's account, stored in Nano

        # action_index:           Location of key action value *(currently !tip only)
        # action:                 Action found in the received tweet - Error logged through None value

        # starting_point:         Location of action sent via tweet (currently !tip only)

        # tip_amount:             Value of tip to be sent to receiver(s) - Error logged through -1
        # tip_amount_text:        Value of the tip stored in a string to prevent formatting issues
        # total_tip_amount:       Equal to the tip amount * number of users to tip
        # tip_id:                 ID of the tip, used to prevent double sending of tips.  Comprised of
        #                         message['id'] + index of user in users_to_tip
        # send_hash:              Hash of the send RPC transaction
        # system:                 System that the command was sent from
    }

    users_to_tip = [
        # List including dictionaries for each user to send a tip.  Each index will include
        # the below parameters
        #    receiver_account:       Nano account of receiver
        #    receiver_register:      Registration status with Tip Bot of receiver account
    ]

    message['system'] = 'telegram'
    request_json = request.get_json()
    logging.info("request_json: {}".format(request_json))
    if 'message' in request_json.keys():
        if request_json['message']['chat']['type'] == 'private':
            logging.info("Direct message received in Telegram.  Processing.")
            message['sender_id'] = request_json['message']['from']['id']

            # message['sender_screen_name'] = request_json['message']['from']['username']
            message['dm_id'] = request_json['update_id']
            message['text'] = request_json['message']['text']
            message['dm_array'] = message['text'].split(" ")
            message['dm_action'] = message['dm_array'][0].lower()

            logging.info("{}: action identified: {}".format(
                datetime.now(), message['dm_action']))

            parse_action(message)

        elif (request_json['message']['chat']['type'] == 'supergroup'
              or request_json['message']['chat']['type'] == 'group'):
            if 'text' in request_json['message']:
                message['sender_id'] = request_json['message']['from']['id']
                message['sender_screen_name'] = request_json['message'][
                    'from']['username']
                message['id'] = request_json['message']['message_id']
                message['chat_id'] = request_json['message']['chat']['id']
                message['chat_name'] = request_json['message']['chat']['title']

                check_telegram_member(message['chat_id'], message['chat_name'],
                                      message['sender_id'],
                                      message['sender_screen_name'])

                message['text'] = request_json['message']['text']
                message['text'] = message['text'].replace('\n', ' ')
                message['text'] = message['text'].lower()
                message['text'] = message['text'].split(' ')

                message = check_message_action(message)
                if message['action'] is None:
                    logging.info(
                        "{}: Mention of nano tip bot without a !tip command.".
                        format(datetime.now()))
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
                member_id = request_json['message']['new_chat_member']['id']
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
                member_id = request_json['message']['left_chat_member']['id']
                member_name = request_json['message']['left_chat_member'][
                    'username']
                logging.info(
                    "member {}-{} left chat {}-{}, removing from DB.".format(
                        member_id, member_name, chat_id, chat_name))

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
                    "member {} created chat {}, inserting creator into DB.".
                    format(member_name, chat_name))

                new_chat_call = (
                    "INSERT INTO telegram_chat_members (chat_id, chat_name, member_id, member_name) "
                    "VALUES ({}, '{}', {}, '{}')".format(
                        chat_id, chat_name, member_id, member_name))
                set_db_data(new_chat_call)

        else:
            logging.info("request: {}".format(request_json))

    return 'ok'


if __name__ == "__main__":
    app.run()
