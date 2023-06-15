# Votey

a simple slack polling slash command - because paying for polls is kind of stupid

<img src="https://user-images.githubusercontent.com/1365665/87252413-a9d07100-c427-11ea-9cc0-751902c99062.png" width="400px"/>

## User Guide
Votey is a surprisingly complex application because it has a variety of options that can allow you to customize how your poll looks and behaves. A Votey poll is composed of three components, a poll title, options, and voters. The first quoted string after the `/votey` command is used as the poll title, and following text is used to form "options" (ie. items that can be voted upon) and poll configuration options.

Simple poll example:

`/votey "some title" "some option A" "some option B"`

Votey allows you to define "emoji vote icons" for each option. To enable this for a vote option, prepend the emoji you'd like to use:

`/votey "some title" :thumbsup: "yes" :thumbsdown: "no"`

To hide the names of voters, append `--anonymous` at the end of your poll creation text. To use an emoji other than the default `:thumbsup:` icon, use `--anonymous=:emojiName:`.

To hide the name of the poll creator _and_ names of voters, append `--secret` at the end of your poll creation text.

To limit the number of votes per poll, append `--limit=N` at the end of your poll creation text. Note that `N` must be equal to lesser than the number of vote options provided.

## Deploying for Production

1. Click the Deploy button above, and then create a [new Slack app](https://api.slack.com/apps) and scroll down to the **App Credentials** Panel.
1. Once the application has deployed on Fly.io, head to the **Settings** tab, and scroll down to the `Config Vars` section. We'll need to fill out some variables that are generated upon creating a Slack App:
    - `CLIENT_ID` - _Client ID_ of your Slack App
    - `CLIENT_SECRET` - _Client Secret_ of your Slack App
    - `SIGNING_SECRET` - Signing Secret of your Slack App
    - `FLASK_ENV` - should be set to `production`
    - `DATABASE_URL` - this should automatically be set to your postgres database uri
1. Click into the **Interactive Components** panel (`Interactivity and Shortcuts` on the sidebar)
    1. Toggle this feature on in the upper right hand corner
    1. Fill in the `Request URL` to `https://your-app.fly.dev/slack` (the `/slack` part is what's important).
1. Go back, and Click into the **Slash Commands** panel (also found on the sidebar)
    1. The command name can just be `votey`, or whatever you'd like to use to trigger the bot. Again the Request URL should be `https://your-app.fly.dev/slack` (remember, the `/slack` part is what's important).
1. Go back, and Click into the **Permissions** panel (`OAuth & Permissions` on the sidebar).
    1. Add a `Redirect URL`: `https://your-app.fly.dev/oauth`.
    1. Add Permissions under the **Scopes** Panel, and enter:
        - `chat:write`
        - `commands`
1. Finally, we're ready to connect Slack with our bot. Navigate to `Manage Distribution` on the sidebar, and click `Add to Slack`. This should navigate to the OAuth URL we provided above, and store the workspace specific token in our database.

Once OAuth has successfully completed, you're ready to start using Votey!

## Development
### Installation
Votey runs on Python 3.10, so you'll need to make sure your environment has Python 3.10 and [Poetry](https://python-poetry.org/) installed.

Run the following in the source directory:

```bash
poetry install
cp .env.example .env
```

Modify your `.env` file to look something like this:

```
SQLALCHEMY_DATABASE_URI='postgres://some_postgres_connection_string'
CLIENT_ID='slack_client_id'
CLIENT_SECRET='slack_client_secret'
SIGNING_SECRET='slack_signing_secret'
FLASK_ENV='development'
```

Go ahead and fill the above with your actual Slack API information (refer to the **Deploying for Production** section above), and your postgres database URI. If you don't have a postgres database running, you'll need to set one up locally. To boot the app, run `make start`.

Connecting your app to Slack follows the same procedure as the **Deploying for Production** section above, but instead of using a Fly.io domain, you'll need to use a tunneling forwarding program like [ngrok.io](http://ngrok.io/).

While developing, you can use `make <lint|pre-commit>` to run linters or run the whole pre-commit suite over all files (which will both format and lint).

Before committing, don't forget to run `make install-hooks`.

Happy Developing!
