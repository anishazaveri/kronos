from flask import Flask, request
import requests
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
import os
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from datetime import date, datetime
from recurrent.event_parser import RecurringEvent
from dateutil.rrule import rrulestr
import re
import random
import json
load_dotenv()

proxy_client = TwilioHttpClient(proxy={'http': os.getenv(
    "http_proxy"), 'https': os.getenv("https_proxy")})
twilio_client = Client(http_client=proxy_client)


app = Flask(__name__)


DONE_REPLIES = ["Great job!", "Excellent!", "Well done!", "You are on a roll!",
                "Thanks for letting me know", "Thumbs up!", "Keep going!"]
REMINDER_SET_REPLIES = ["Got it!", "Gotcha!",
                        "Recorded!", "Roger!", "Ok!", "Confirmed!"]


def parse_datetime(dt):
    date_str = dt.strftime('%Y-%m-%d')
    time_str = dt.strftime('%H:%M')
    return date_str, time_str


def parse_snooze(body):
    with open('last_req.txt') as json_file:
        last_req = json.load(json_file)
    # print("Last req", LAST_REQ)
    event = RecurringEvent(now_date=datetime.now())
    datetime_extracted = event.parse(body)
    rec_person = "Anisha"
    date_str, time_str = parse_datetime(datetime_extracted)
    body_c = last_req['title']
    rrule = None
    rrule_str = None
    return rec_person, date_str, time_str, body_c, rrule, rrule_str


def parse_body(body):
    """
    Parse body and return relevant extracted arguments
    """
    # Is it snooze message?
    if "remind me again" in body.lower():
        return parse_snooze(body)
    # get receiver
    rec = re.split('remind', body, flags=re.IGNORECASE)[-1].split(' ')[1]
    if rec == 'me':
        rec_person = "Anisha"
    else:
        rec_person = rec
    # get everything after remind me
    body_r = re.split(f'remind {rec}', body, flags=re.IGNORECASE)[-1]

    # get the reminder content by splitting the first 'to' or 'about'
    body_t, filler, body_c_mfiller = re.split(r'(\bto\b|\babout\b)', body_r, 1)
    body_c = f'{filler}{body_c_mfiller}'
    # print(body_t, body_c)

    # extract date/rrule
    event = RecurringEvent(now_date=datetime.now())
    datetime_extracted = event.parse(body_t)
    if datetime_extracted is None:
        raise TypeError
    elif type(datetime_extracted) == str:
        # then rrule
        rule = rrulestr(datetime_extracted)
        next_rem = rule.after(datetime.now())
        date_str, time_str = parse_datetime(next_rem)
        rrule = datetime_extracted
        rrule_str = event.format(rrule)
    else:
        date_str, time_str = parse_datetime(datetime_extracted)
        rrule = None
        rrule_str = None
    return rec_person, date_str, time_str, body_c, rrule, rrule_str


def set_reminder(body):
    """
    Sets reminder and returns response string
    """
    try:
        rec_person, date_str, time_str, body_c, rrule, rrule_str = parse_body(
            body)
    except TypeError:
        return "Sorry! No datetime information was found to set a reminder"
    if rec_person == 'Anisha':
        rec_reformat = "you"
    else:
        rec_reformat = rec_person
    headers = {
        'Authorization': f'Bearer {os.getenv("REMINDERS_TOKEN")}',
    }
    data = {"title": f"{body_c}", "date_tz": date_str, "time_tz": time_str,
            "timezone": "America/New_York", "notes": rec_person}
    if rrule:
        data["rrule"] = rrule
        reply_mess = f"{random.choice(REMINDER_SET_REPLIES)} I will remind {rec_reformat} {rrule_str} {body_c}"
    else:
        reply_mess = f"{random.choice(REMINDER_SET_REPLIES)} I will remind {rec_reformat} on {date_str} at {time_str} {body_c}"
    response = requests.post(
        'https://reminders-api.com/api/applications/23/reminders/', headers=headers, data=data)
    return reply_mess


@app.route("/sms", methods=['GET', 'POST'])
def incoming_sms():
    """Send a dynamic reply to an incoming text message"""
    # Get the message the user sent our Twilio number
    body = request.values.get('Body', None)
    if body[0:4].lower() == "done":
        reply_mess = random.choice(DONE_REPLIES)
    if body[0:5].lower() == "thank":
        reply_mess = "You are welcome!"
    else:
        reply_mess = set_reminder(body)
    # Start our TwiML response
    reply = MessagingResponse()
    reply.message(reply_mess)
    return str(reply)


def write_last_req(req):
    with open('last_req.txt', 'w') as outfile:
        json.dump(req, outfile)
    return None


@app.route("/reminders", methods=['POST'])
def receive_reminder():
    req = request.get_json()
    # print(req)
    # content
    for single_rem in req['reminders_notified']:
        send_reminder(single_rem)
    return 'OK'


def send_reminder(single_rem):
    body_c = single_rem['title']
    # person to remind
    rec_person = single_rem['notes']
    if rec_person == "Anisha":
        to_phone_number = os.getenv("ANISHA_PHONE")
        body = f"Hi! This is a reminder {body_c}"
        write_last_req(single_rem)
    if rec_person == "Victor":
        to_phone_number = os.getenv("VICTOR_PHONE")
        body = f"Hi! This is a reminder from Anisha {body_c}"
    twilio_from = os.getenv("TWILIO_SMS_FROM")
    twilio_client.messages.create(
        body=body,
        from_=f"{twilio_from}",
        to=f"{to_phone_number}")
    return None


if __name__ == '__main__':
    app.run()
