# Votey

a simple slack polling slash command - because paying for polls is kind of stupid


## Installation
Votey runs on Python 3.7, so you'll need to make sure your environment has Python 3.7 and [Pipenv](https://pipenv.readthedocs.io/en/latest/) installed.

Run `pipenv shell` and `pipenv install` in the cloned directory.
Next, create a configuration file:

```
mkdir instance
touch instance/dev.cfg
```

Your `dev.cfg` file should look something like this:

```
SQLALCHEMY_DATABASE_URI='postgres://some_postgres_connection_string'
CLIENT_ID='slack_client_id'
CLIENT_SECRET='slack_client_secret'
SIGNING_SECRET='slack_signing_secret'
```

Go ahead and fill the above with your actual Slack API information, and your postgres database uri string. As a note, you can get a free postgres database provisioned on [Heroku](http://herokuapp.com) (you'll need to create an app and provision the Heroku Postgres addon - the connection string will be attached to your app's environment config variables).

Finally, run `VOTEY_CONFIG=dev.cfg make run`

Everything should launch up now!

## Developing
Now that we've setup votey to run and talk to a database, we need to connect Slack with our development environment. I recommend using a forwarding utility like [https://serveo.net](Serveo), which will let you connect an internal port with the outside work, with a static URL.

Create a [new Slack app](https://api.slack.com/apps) with the following features:
- Interative Components
- Slash Commands
- Permissions (`chat:write:bot`, `Add slash commands and add actions to messages (and view related content)`)

We'll then need to configure a couple of URLs so slack can talk to our development instance. On the sidebar, navigate to `Interactive Components`, and fill in the `Request URL` to `https://votey-dev.serveo.net/slack` (the `/slack` part is what's important, the domain can be of your choosing).

Next, head to `Slash Commands`, and create a new command. The command name can just be `votey`, or whatever you'd like to use to trigger the bot. Again the Request URL should be `https://votey-dev.serveo.net/slack`

Next, navigate to `OAuth & Permissions`, and add a `Redirect URL`: `https://votey-dev.serveo.net/oauth`.

Finally, we're ready to connect Slack with our bot. Navigate to `Manage Distribution` on the sidebar, and click `Add to Slack`. This should navigate to the OAuth URL we provided above, and store the workspace specific token in our database.

Once OAuth has successfully completed, we're good to start using a dev instance Votey in the playground.

Happy developing!
