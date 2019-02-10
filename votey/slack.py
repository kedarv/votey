from flask import Blueprint
from flask import request
from flask import current_app
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple
from werkzeug.local import LocalProxy
import hashlib
import hmac
import json
import requests
import shlex
import time
import uuid

from .models import Poll, Option, Vote, Workspace
from votey import db
from .utils import batch, AnyJSON, JSON

bp = Blueprint('slack', __name__)

NUM_TO_SLACKMOJI = {
    1: ':one:',
    2: ':two:',
    3: ':three:',
    4: ':four:',
    5: ':five:',
    6: ':six:',
    7: ':seven:',
    8: ':eight:',
    9: ':nine:',
    10: ':keycap_ten:',
}

ANON_KEYWORDS = {
    '--anonymous',
    '-anonymous',
    '-anon',
    '--anon',
}

@bp.route('/slack', methods=['POST'])  # type: ignore
def slack() -> str:
    return handle_button_interaction(request.form) \
        if valid_request(request) and request.form.get('payload') \
        else handle_poll_creation(request.form) \
        if valid_request(request) \
        else ''

@bp.route('/oauth', methods=['GET'])  # type: ignore
def oauth() -> str:
    code = request.args.get('code')
    client_id = current_app.config['CLIENT_ID']
    client_secret = current_app.config['CLIENT_SECRET']
    oauth = requests.get('https://slack.com/api/oauth.access', params={
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
    })
    if oauth.json().get('ok'):
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
        return f'thanks! votey has been installed to <b>{name}</b>. you can close this tab.'
    return 'something went wrong :('

def handle_poll_creation(req: JSON) -> str:
    workspace = Workspace.query.filter_by(team_id=req.get('team_id')).first()
    command, anonymous = get_command_from_req(req, workspace)
    if command is None:
        return ''

    channel = req.get('channel_id', '')

    poll_question = command.pop(0)
    actions = []
    fields = []

    poll = Poll(uuid.uuid4(), poll_question, channel, anonymous)
    db.session.add(poll)
    db.session.commit()

    for counter, option_text in enumerate(command):
        option = Option(poll.id, option_text)
        db.session.add(option)
        db.session.commit()

        actions.append({
            'name': str(counter),
            'text': NUM_TO_SLACKMOJI[counter + 1],
            'value': option.id,
            'type': 'button'
        })
        fields.append({
            'title': '',
            'value': f'{NUM_TO_SLACKMOJI[counter + 1]} {option_text}\n\n\n',
            'short': False,
            'mrkdwn': 'true',
        })

    attachments = [
        {
            'text': poll_question,
            'mrkdwn_in': ['fields'],
            'color': '#6ecadc',
            'fields': fields,
            'footer': f'Anonymous poll created by <@{req.get("user_id")}>'
            if anonymous else f'Poll created by <@{req.get("user_id")}>',
            'ts': time.time(),
        },
    ]
    for batched in batch(actions, 5):
        attachments.append({
                'text': ' ',
                'callback_id': poll.poll_identifier(),
                'attachment_type': 'default',
                'color': '#6ecadc',
                'actions': batched
        })

    delete_attachment = {
        'text': ' ',
        'callback_id': poll.poll_identifier(),
        'actions': [{
            'name': 'delete',
            'text': 'Delete',
            'type': 'button',
            'style': 'danger',
        }]
    }
    res = send_message(workspace, channel, attachments=attachments).json()
    poll.ts = res['ts']
    db.session.commit()

    send_message(
        workspace,
        req.get('user_id', ''),
        text=f'Delete your last poll, "{poll_question}"?',
        attachments=[delete_attachment]
    )
    return ''


def handle_button_interaction(req: JSON) -> str:
    res = json.loads(req.get('payload', ''))
    button = res.get('actions')[0]['name']
    return handle_poll_deletion(res) if button == 'delete' else handle_vote(res)


def handle_vote(response: AnyJSON) -> str:
    poll = Poll.query.filter_by(
        identifier=response.get('callback_id')
    ).first()
    option = Option.query.filter_by(
        id=response.get('actions', [])[0]['value']
    ).first()
    workspace = Workspace.query.filter_by(
        team_id=response.get('team', {}).get('id')
    ).first()
    user = response.get('user', {}).get('id')
    channel = response.get('channel', {}).get('id')
    attachment_id = int(response.get('attachment_id', '-1'))
    original_message = response.get('original_message', {})
    attachments = original_message.get('attachments')

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

        position = int(response.get('actions', [])[0]['name'])

        votes = Vote.query.filter_by(option_id=option.id).all()
        num = f'`{len(votes)}`'
        field_text = f'{NUM_TO_SLACKMOJI[position+1]} {option.option_text}\t' \
                                 f'{num if votes else ""}\n' \
                                 f'{thumbs(votes) if poll.anonymous else names(votes)}\n\n'
        attachments[0].get('fields')[position]['value'] = field_text
        requests.post('https://slack.com/api/chat.update', json={
            'channel': channel,
            'ts': response.get('message_ts'),
            'text': '',
            'attachments': attachments,
        },  headers={'Authorization': f'Bearer {workspace.token}'})
    return ''


def handle_poll_deletion(response: AnyJSON) -> str:
    workspace = Workspace.query.filter_by(
        team_id=response.get('team', {}).get('id')
    ).first()
    poll = Poll.query.filter_by(
        identifier=response.get('callback_id')
    ).first()
    votes = Vote.query.filter_by(
        poll_id=poll.id
    ).delete()
    options = Option.query.filter_by(
        poll_id=poll.id
    ).delete()

    db.session.delete(poll)
    db.session.commit()
    res = requests.post('https://slack.com/api/chat.delete', json={
        'channel': poll.channel,
        'ts': poll.ts,
    }, headers={'Authorization': f'Bearer {workspace.token}'})
    return f'Your poll "{poll.question}" has been deleted.'


def thumbs(votes: List[Vote]) -> str:
    return ':thumbsup:' * len(votes)


def names(votes: List[Vote]) -> str:
    return ','.join([f'<@{vote.user}>' for vote in votes])


def valid_request(request: LocalProxy) -> bool:
    timestamp = request.headers['X-Slack-Request-Timestamp']
    slack_signature = request.headers['X-Slack-Signature']
    # Avoid replay attacks
    if abs(time.time() - int(timestamp)) > (60*5):
        return False
    sig_basestring = str.encode(f'v0:{timestamp}:') + request.get_data()
    request_hash = 'v0=' + hmac.new(
            bytes(current_app.config['SIGNING_SECRET'], encoding='utf-8'),
            sig_basestring,
            hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(request_hash, slack_signature)

def get_command_from_req(
    request: JSON,
    workspace: Workspace
) -> Tuple[Optional[List[str]], bool]:
    try:
        split = shlex.split(request.get('text', '') \
            .replace('“','"') \
            .replace('”','"'))
    except ValueError as e:
        send_ephemeral_message(
            workspace,
            request.get('channel_id', ''),
            request.get('user_id', ''),
            f'We had trouble parsing that - {e}',
        )
        return None, False

    if ANON_KEYWORDS.isdisjoint(split):
        anonymous = False
    else:
        anonymous = True
        split = [word for word in split if word not in ANON_KEYWORDS]

    if len(split) < 3:
        send_ephemeral_message(
            workspace,
            request.get('channel_id', ''),
            request.get('user_id', ''),
            'Oops - a poll needs to have at least two options. ' \
            'Try again with `/votey "question" "option 1" "option 2"`',
        )
        return None, False
    if len(split) > 11:
        send_ephemeral_message(
            workspace,
            request.get('channel_id', ''),
            request.get('user_id', ''),
            'Sorry - Votey only supports 10 options at the moment.',
        )
        return None, False

    return split, anonymous


def send_ephemeral_message(
    workspace: Workspace,
    channel: str,
    user: str,
    text: str,
) -> requests.Response:
    return requests.post(
        'https://slack.com/api/chat.postEphemeral',
        json={'channel': channel, 'user': user, 'text': text},
        headers={'Authorization': f'Bearer {workspace.token}'},
    )

def send_message(
    workspace: Workspace,
    dest: str,
    text: Optional[str] = None,
    attachments: Optional[List[Any]] = None,
) -> requests.Response:
    body: Any = {'channel': dest}
    if text is not None:
        body['text'] = text
    if attachments is not None:
        body['attachments'] = attachments
    return requests.post(
        'https://slack.com/api/chat.postMessage',
        json=body,
        headers={'Authorization': f'Bearer {workspace.token}'},
    )
