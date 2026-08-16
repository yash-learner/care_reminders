# Installation

Install from the Git repo into CARE (editable for local work):

```sh
pip install -e ./care_reminders
```

Or from GitHub:

```sh
pip install "git+https://github.com/yash-learner/care_reminders.git"
```

Then register the plug in CARE `plug_config.py` (see the root README). Confirm:

```sh
curl http://localhost:9000/api/care_reminders/health
```
