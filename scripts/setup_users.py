#!/usr/bin/env python
"""Einmalig ausführen: generiert app/data/users.yaml mit bcrypt-Hashes."""
import yaml
from pathlib import Path
import streamlit_authenticator as stauth

DEMO_USERS = {
    "admin": {
        "name": "Administrator",
        "email": "admin@aid-demo.de",
        "password": "Admin2024!",
        "role": "admin",
    },
    "planner": {
        "name": "Planer",
        "email": "planner@aid-demo.de",
        "password": "Plan2024!",
        "role": "planner",
    },
    "viewer": {
        "name": "Betrachter",
        "email": "viewer@aid-demo.de",
        "password": "View2024!",
        "role": "viewer",
    },
}

passwords = [u["password"] for u in DEMO_USERS.values()]
hashed = stauth.Hasher.hash_list(passwords)

credentials = {"usernames": {}}
for (username, user_data), hashed_pw in zip(DEMO_USERS.items(), hashed):
    credentials["usernames"][username] = {
        "name": user_data["name"],
        "email": user_data["email"],
        "password": hashed_pw,
        "role": user_data["role"],
    }

config = {
    "credentials": credentials,
    "cookie": {
        "expiry_days": 1,
        "name": "aid_demo_cookie",
        # Kein Signierschlüssel hier - kommt aus AID_COOKIE_KEY (.env),
        # siehe streamlit_app.py. Diese Datei liegt öffentlich im Repo.
    },
}

out = Path(__file__).parent.parent / "app" / "data" / "users.yaml"
with open(out, "w", encoding="utf-8") as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
print(f"users.yaml geschrieben: {out}")
