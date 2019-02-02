from flask import Flask
from flask import request
from flask import jsonify
import shlex
import emoji

app = Flask(__name__)

NUM_TO_SLACKMOJI = {
  1: ':one:',
  2: ':two:',
  3: ':three:',
  4: ':four:',
  5: ':five:',
  6: ':six:',
  7: ':seven:',
}

@app.route("/slack", methods=['POST'])
def slack():
  if request.form.get('payload'):
    return handle_button_interaction(request.form)
  return handle_poll_creation(request.form)

def handle_poll_creation(request):
  command = shlex.split(request.get('text'))
  poll_question = command.pop(0)
  actions = []
  action_texts = []

  for counter, option in enumerate(command):
    action_texts.append(NUM_TO_SLACKMOJI[(counter+1)] + ' ' + option)
    actions.append({
      'name': option,
      'text': NUM_TO_SLACKMOJI[(counter+1)],
      'value': option,
      'type': 'button'
    })

  response = {
    "attachments": [
      {
        'text': '*' + poll_question + '*\n' + '\n'.join(action_texts),
        'mrkdwn_in': ['text'],
      },
      {
        'callback_id': 'something',
        'attachment_type': 'default',
        'color': '#3AA0E3',
        'actions': actions
      }
    ],
  }

  return jsonify(response)