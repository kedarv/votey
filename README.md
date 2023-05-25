# Votey

a simple slack polling slash command - because paying for polls is kind of stupid

![Votey Screenshot](https://user-images.githubusercontent.com/1365665/87252413-a9d07100-c427-11ea-9cc0-751902c99062.png)

## Deploying for Production

1. Click the Deploy button above, and then create a [new Slack app](https://api.slack.com/apps) and scroll down to the **App Credentials** Panel.
1. Once the application has deployed on Heroku, head to the **Settings** tab, and scroll down to the `Config Vars` section. We'll need to fill out some variables that are generated upon creating a Slack App:
    - `CLIENT_ID` - _Client ID_ of your Slack App
    - `CLIENT_SECRET` - _Client Secret_ of your Slack App
    - `SIGNING_SECRET` - Signing Secret of your Slack App
    - `FLASK_ENV` - should be set to `production`
    - `DATABASE_URL` - this should automatically be set to your postgres database uri
1. Click into the **Interactive Components** panel (`Interactivity and Shortcuts` on the sidebar)
    1. Toggle this feature on in the upper right hand corner
    1. Fill in the `Request URL` to `https://your-app.herokuapp.com/slack` (the `/slack` part is what's important).
1. Go back, and Click into the **Slash Commands** panel (also found on the sidebar)
    1. The command name can just be `votey`, or whatever you'd like to use to trigger the bot. Again the Request URL should be `https://your-app.herokuapp.com/slack` (remember, the `/slack` part is what's important).
1. Go back, and Click into the **Permissions** panel (`OAuth & Permissions` on the sidebar).
    1. Add a `Redirect URL`: `https://your-app.herokuapp.com/oauth`.
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
pipenv install -d
pipenv run install-hooks
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

Go ahead and fill the above with your actual Slack API information (refer to the **Deploying for Production** section above), and your postgres database URI. If you don't have a postgres database running, you can either set one up locally or use the `Deploy with Heroku` button above to have a database provisioned for free. To boot the app, run `pipenv run start`.

Connecting your app to Slack follows the same procedure as the **Deploying for Production** section above, but instead of using Heroku's domain, you'll need to use a tunneling forwarding program like [ngrok.io](http://ngrok.io/).

While developing, you can use `pipenv run <format|lint|pre-commit>` to format code, run linters, or run the whole pre-commit suite over all files (which will both format and lint).

Before committing, don't forget to run `pipenv run install-hooks`.

Happy Developing!