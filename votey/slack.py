from flask import Blueprint
from flask import request
from flask import jsonify
import shlex
import emoji
import os
import uuid
import json
import requests

from .models import Poll, Option, Vote
from votey import db


bp = Blueprint('slack', __name__)

NUM_TO_SLACKMOJI = {
  1: ':one:',
  2: ':two:',
  3: ':three:',
  4: ':four:',
  5: ':five:',
  6: ':six:',
  7: ':seven:',
}

@bp.route("/slack", methods=['POST'])
def slack():
  if request.form.get('payload'):
    return handle_button_interaction(request.form)
  return handle_poll_creation(request.form)

def handle_poll_creation(req):
  command = shlex.split(req.get('text'))
  poll_question = command.pop(0)
  actions = []
  fields = []

  poll = Poll(uuid.uuid4(), poll_question)
  db.session.add(poll)
  db.session.commit()

  for counter, option_text in enumerate(command):
    option = Option(poll.id, option_text)
    db.session.add(option)
    db.session.commit()

    actions.append({
      'name': 'vote',
      'text': NUM_TO_SLACKMOJI[(counter+1)],
      'value': option.id,
      'type': 'button'
    })
    fields.append({
      'title': '',
      'value': NUM_TO_SLACKMOJI[(counter+1)] + ' ' + option_text + '\n\n\n',
      'short': False,
    })

  attachments = [
    {
      'text': poll_question,
      'mrkdwn_in': ['fields'],
      'color': '#6ecadc',
      'fields': fields,
    },
    {
      'text': ' ',
      'callback_id': poll.poll_identifier(),
      'attachment_type': 'default',
      'color': '#6ecadc',
      'actions': actions
    }
  ]

  post_message = requests.post('https://slack.com/api/chat.postMessage', json = {
    'channel': req.get('channel_id'),
    'attachments': attachments,
  }, headers={'Authorization': 'Bearer '})
  print(post_message.text)
  return ''

def handle_button_interaction(req):
  response = json.loads(req.get('payload'))
  poll = Poll.query.filter_by(identifier=response.get('callback_id')).first()
  option = Option.query.filter_by(id=response.get('actions')[0]['value']).first()
  user = response.get('user').get('id')
  channel = response.get('channel').get('id')
  original_message = response.get('original_message')

  if poll is not None and option is not None:
    vote = Vote.query.filter_by(
      poll_id=poll.id,
      option_id=option.id,
      user=user
    ).first()

    if vote:
      db.session.delete(vote)
    else:
      vote = Vote(poll.id, option.id, user)
      db.session.add(vote)
    db.session.commit()

    position = 0
    for button in original_message.get('attachments')[1].get('actions'):
      if int(button.get('value')) == option.id:
        position = int(button.get('id'))

    vote_list = []
    votes = Vote.query.filter_by(option_id=option.id).all()
    for voter in votes:
      vote_list.append('<@' + voter.user + '>')

    original_message.get('attachments')[0].get('fields')[position-1]['value'] = NUM_TO_SLACKMOJI[(position)] + ' ' + option.option_text + '\n' + ','.join(vote_list) + '\n\n'
    update_req = requests.post('https://slack.com/api/chat.update', json = {
      'channel': channel,
      'ts': response.get('message_ts'),
      'text': '',
      'attachments': original_message.get('attachments'),
    },  headers={'Authorization': 'Bearer '})
    print(update_req.text)
  return ''



