from flask import Blueprint
from flask import request
from flask import jsonify
from flask import current_app
import shlex
import emoji
import os
import uuid
import json
import requests
import time
import hmac
import hashlib

from .models import Poll, Option, Vote, Workspace
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
  if valid_request(request):
    if request.form.get('payload'):
      return handle_button_interaction(request.form)
    return handle_poll_creation(request.form)

@bp.route("/oauth", methods=['GET'])
def oauth():
  code = request.args.get('code')
  client_id = current_app.config['CLIENT_ID']
  client_secret = current_app.config['CLIENT_SECRET']
  oauth = requests.get('https://slack.com/api/oauth.access', params={
    'code': code,
    'client_id': client_id,
    'client_secret': client_secret,
  })
  if oauth.json().get('ok') == True:
    team_id = oauth.json().get('team_id')
    token = oauth.json().get('access_token')
    name = oauth.json().get('team_name')
    workspace = Workspace.query.filter_by(team_id=team_id).first()
    if workspace is not None:
      workspace.token = token
    else:
      workspace = Workspace(team_id, name, token)
      db.session.add(workspace)
    db.session.commit()
    return "thanks! votey has been installed to <b>{}</b>. you can close this tab.".format(name)
  return "something went wrong :("

def handle_poll_creation(req):
  workspace = Workspace.query.filter_by(team_id=req.get('team_id')).first()
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
      "mrkdwn": "true",
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
  }, headers={'Authorization': 'Bearer {}'.format(workspace.token)})

  return ''

def handle_button_interaction(req):
  response = json.loads(req.get('payload'))
  poll = Poll.query.filter_by(identifier=response.get('callback_id')).first()
  option = Option.query.filter_by(id=response.get('actions')[0]['value']).first()
  user = response.get('user').get('id')
  channel = response.get('channel').get('id')
  original_message = response.get('original_message')
  workspace = Workspace.query.filter_by(team_id=response.get('team').get('id')).first()

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

    if len(vote_list) > 0:
      field_text = NUM_TO_SLACKMOJI[(position)] + ' ' + option.option_text + '\t `'+ str(len(vote_list)) +'` \n' + ','.join(vote_list) + '\n\n'
    else:
      field_text = NUM_TO_SLACKMOJI[(position)] + ' ' + option.option_text + '\n' + ','.join(vote_list) + '\n\n'
    original_message.get('attachments')[0].get('fields')[position-1]['value'] = field_text
    update_req = requests.post('https://slack.com/api/chat.update', json = {
      'channel': channel,
      'ts': response.get('message_ts'),
      'text': '',
      'attachments': original_message.get('attachments'),
    },  headers={'Authorization': 'Bearer {}'.format(workspace.token)})
  return ''

def valid_request(request):
  timestamp = request.headers['X-Slack-Request-Timestamp']
  slack_signature = request.headers['X-Slack-Signature']
  # Avoid replay attacks
  if abs(time.time() - int(timestamp)) > (60*5):
    return False
  sig_basestring = str.encode('v0:' + str(timestamp) + ':') + request.get_data()
  request_hash = 'v0=' + hmac.new(
      bytes(current_app.config['SIGNING_SECRET'], encoding='utf-8'),
      sig_basestring,
      hashlib.sha256
  ).hexdigest()
  return hmac.compare_digest(request_hash, slack_signature)

