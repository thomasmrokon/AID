import bcrypt

hashes = {
    'admin':   b'$2b$12$hzj653yyaFbCI64Ue29PHuzzRP7AfZGsNQKqEuxzzHYPlwzIRQgra',
    'planner': b'$2b$12$p9SqRDlQ2F9eSFRDaXGobezA.K21TDW2ud1G3Conr1SRTaaVOjmJK',
    'viewer':  b'$2b$12$7w9yfaidHr759X9IqXN2he0..ct7b4CSWp60CdJs50FvXsolcDFS.',
}
candidates = ['admin', 'planner', 'viewer', 'demo', 'aid2024', 'password', '1234', 'test',
              'aid', 'dreso', 'Admin', 'Planner', 'Viewer', 'Demo', 'AID', 'aid123', 'demo123']

for user, h in hashes.items():
    for pw in candidates:
        try:
            if bcrypt.checkpw(pw.encode(), h):
                print(f'{user}: "{pw}"')
                break
        except Exception:
            pass
    else:
        print(f'{user}: not in candidates')
