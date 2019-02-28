import os
import logging
import requests
import json
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from transport.data_provider import DropBoxDataProvider
from bots.mockbase import Database
from stella_api.service_data import store_bot_data, comany_and_address
from database.queries import (session_scope, list_fuel_company_names,
                              acquire_gas_station)

dbx_token = os.environ['DROPBOX_TOKEN']
telegram_token = os.environ['TELEGRAM_TOKEN']
port = int(os.environ['PORT'])
url_path = os.environ['URL_PATH']

locations = dict()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
dbx_provider = DropBoxDataProvider(dbx_token)

db_object = Database()
ACTION, CHOICE, CHOOSE_STATION, SENT_LOCATION = range(4)


def start(bot, update):
    reply_keyboard = [['/setdata', '/getdata']]

    update.message.reply_text(
            "Hello! My name is Stella, and I will provide you with the actual information on prices of Ukrainian" \
            "gas stations.\n"
            "Simply type or choose button, what do yo want\n"
            "/setdata - send us actual photo with gas prices.\n"
            "/getdata - get information about gas prices\n"
            "If something goes wrong, simply type '/start'. If you need help, type 'help'.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))

    
def help(bot, update):
    update.message.reply_text("Still in development./start")


#TODO: upgrade pagination
def setdata(bot, update):
    with session_scope() as session:
        companies = list_fuel_company_names(session)
        height = int(len(companies) ** 0.5)
        reply_keyboard = list(zip(*[iter(companies)] * height))
    
    update.message.reply_text("Please chose Fuel company from the list, \n"
                                  "or type /add_company if you can't see it",
                               reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                               one_time_keyboard=True))
    return CHOICE


def add_company(bot, update):
    update.message.reply_text("Please enter company name:")
    return ACTION


def cancel(bot, update):
    return ConversationHandler.END


def add_to_db(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text=db_object.add_company(update.message.text))
    return sent_location(bot, update)


def sent_location(bot, update):
    location_button = KeyboardButton('Sent location', request_location=True)
    update.message.reply_text('Please, share you location so we can find nearest gas stations',
                              reply_markup=ReplyKeyboardMarkup([[location_button]],
                              one_time_keyboard=True, resize_keyboard=True))
    return SENT_LOCATION


def got_location(bot, update):
    loc = update.message.location
    update.message.reply_text('Thanks!\n' + str(loc))
    tg_id = update.message.from_user.id
    locations[tg_id] = loc
    return choose_station(bot, update, update.message.location)


def choose_station(bot, update, location):
    company, address = comany_and_address(location['latitude'],
                                          location['longitude'])
    with session_scope() as session:
        station = acquire_gas_station(session, company, address)
        reply_keyboard = [
            [f'{company} {station.address}'],
            ['other']
        ]
    update.message.reply_text("Please chose Gas Station from the list",
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard,
                                                               one_time_keyboard=True))
    return CHOOSE_STATION


def send_photo(bot, update):
    update.message.reply_text("Please sent us the photo of Stella")
    return cancel(bot, update)


def error(bot, update, error):
    logger.warning("Update {} caused error {}".format(update, error))


def send_file_dbx(bot, update):
    # TODO move this to services
    file_id = update.message.document.file_id
    chat_id = update.message.chat_id
    new_file = requests.get("https://api.telegram.org/bot{}/getFile?file_id={}".format(telegram_token, file_id))
    loaded_data = json.loads(new_file.text)
    file_path = loaded_data["result"]["file_path"]

    down_path = "https://api.telegram.org/file/bot{}/{}".format(telegram_token, file_path)
    dirname, basename = os.path.split(file_path)
    dbx_path = "/telegram_files/" + basename

    #res = requests.get(down_path)
    #binary_pic = res.content
    #dbx_upload_path = dbx_provider.file_upload(down_path, dbx_path)
    #file_path = 'files/image.png'
    #print(dbx_path)
    #local_file_path = dbx_provider.file_download(file_path, dbx_path)
    #print(local_file_path)
    #global image_link
    #image_link = dbx_path
    #bot.send_message(chat_id=update.message.chat_id, text=down_path)

    tg_id = update.message.from_user.id
    user_location = locations.get(tg_id)
    if user_location:
        reply_store = store_bot_data(tg_id,
                                     down_path,
                                     user_location['latitude'],
                                     user_location['longitude'])
        bot.send_message(chat_id=chat_id, text=reply_store)
    else:
        bot.send_message(chat_id=chat_id, text='Share your location first.')


def request_user_location(bot, update):
    chat_id = update.message.chat_id
    location_keyboard = KeyboardButton(text="My Location", request_location=True)
    custom_keyboard = [[location_keyboard]]
    reply_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True)
    bot.send_message(chat_id=chat_id, text="Please, share your location:", reply_markup=reply_markup)


def get_user_location(bot, update):
    new_location = update.message.location
    chat_id = update.message.chat_id
    bot.send_message(chat_id=chat_id, text="Thanks!", reply_markup=ReplyKeyboardRemove())
    tg_id = update.message.from_user.id
    #reply_store = store_bot_data(tg_id,
    #                             image_link,
    #                             new_location['latitude'],
    #                             new_location['longitude'])
    #bot.send_message(chat_id=update.message.chat_id, text=reply_store)
    locations[tg_id] = dict(lat=new_location['latitude'], long=new_location['longitude'])
    print(locations)


message_handlers = {Filters.document: send_file_dbx, Filters.location: get_user_location, }
command_handlers = {"start": start, "help": help, }


def main():
    updater = Updater(telegram_token)
    disp = updater.dispatcher
    disp.add_error_handler(error)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add_company', add_company),
                      CommandHandler("setdata", setdata)],

        states={
            ACTION: [MessageHandler(Filters.text, add_to_db)],
            CHOICE: [CommandHandler('add_company', add_company),
                     MessageHandler(Filters.text, sent_location)],
            SENT_LOCATION: [MessageHandler(Filters.location, got_location)],
            CHOOSE_STATION: [MessageHandler(Filters.text, send_photo)]
        },

        fallbacks=[CommandHandler('cancel', cancel)]
    )
    disp.add_handler(conv_handler)
    disp.add_handler(CommandHandler("start", start))
    disp.add_handler(CommandHandler("help", help))
    disp.add_handler(CommandHandler("getdata", help))
    disp.add_handler(CommandHandler("chose_station", help))
    disp.add_handler(MessageHandler(Filters.document, send_file_dbx))
    disp.add_handler(MessageHandler(Filters.photo, send_file_dbx))

    #deque(map(lambda kv: (disp.add_handler(CommandHandler(kv[0], kv[1]))), command_handlers.items()))
    #deque(map(lambda kv: (disp.add_handler(MessageHandler(kv[0], kv[1]))), message_handlers.items()))

    updater.start_webhook(listen="0.0.0.0",
                          port=port,
                          url_path=telegram_token)
    updater.bot.setWebhook(f'{url_path}/{telegram_token}')
    updater.idle()

if __name__ == '__main__':
    main()
