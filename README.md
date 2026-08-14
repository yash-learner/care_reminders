# Care Reminders

CARE Django plugin: dose calendar and Android exact-alarm APIs for patient OTP sessions.

Scaffolded with [ohcnetwork/care-plugin-cookiecutter](https://github.com/ohcnetwork/care-plugin-cookiecutter). Increment 1 plan: [`docs/increment-1.md`](docs/increment-1.md). v1 build sequence (Capacitor → alarms): [`docs/increment-1-v1-plan.md`](docs/increment-1-v1-plan.md).

Plugin URLs mount at `/api/care_reminders/` (health: `/api/care_reminders/health`).

## Local development (with CARE)

1. Clone next to `care`:

```bash
cd /path/to/care
git clone https://github.com/yash-learner/care_reminders.git
pip install -e ./care_reminders
```

2. Register in `plug_config.py` (local only — do not PR this into CARE core until ready):

```python
from plugs.manager import PlugManager
from plugs.plug import Plug

care_reminders_plug = Plug(
    name="care_reminders",
    package_name="git+https://github.com/yash-learner/care_reminders.git",
    version="@main",
    configs={},
)
plugs = [care_reminders_plug]
manager = PlugManager(plugs)
```

For a local clone mounted at `/app/care_reminders`:

```python
care_reminders_plug = Plug(
    name="care_reminders",
    package_name="/app/care_reminders",
    version="",
    configs={},
)
```

3. Rebuild CARE and confirm `GET /api/care_reminders/health` returns `OK`.

Parser tests (no Django):

```bash
PYTHONPATH=src python -m unittest tests.test_dosage_parser tests.test_care_hello
```

After `pip install -e` into CARE and registering the plug:

```bash
python manage.py migrate care_reminders
python manage.py test care_reminders --keepdb
```

## Production

Same `Plug` block in CARE `plug_config.py`, `package_name` pointing at this Git repo.

[Plug installation docs](https://care-be-docs.ohc.network/pluggable-apps/configuration.html)

This plugin was created with [Cookiecutter](https://github.com/cookiecutter/cookiecutter) using [ohcnetwork/care-plugin-cookiecutter](https://github.com/ohcnetwork/care-plugin-cookiecutter).
