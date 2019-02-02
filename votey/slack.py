from flask import Blueprint
from flask import request
from flask import jsonify
import shlex
import emoji
import os

from .models import Poll, Option, Vote


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

  for counter, option in enumerate(command):
    actions.append({
      'name': 'vote',
      'text': NUM_TO_SLACKMOJI[(counter+1)],
      'value': counter+1,
      'type': 'button'
    })
    fields.append({
      'title': '',
      'value': NUM_TO_SLACKMOJI[(counter+1)] + ' ' + option + '\n\n\n',
      'short': False,
    })

  response = {
    "response_type": "in_channel",
    "attachments": [
      {
        'title': poll_question,
        'mrkdwn_in': ['fields'],
        'color': '#6ecadc',
        'fields': fields,
      },
      {
        'callback_id': 'something',
        'attachment_type': 'default',
        'color': '#6ecadc',
        'actions': actions
      }
    ],
  }

  return jsonify(response)

def handle_button_interaction(req):
  pass