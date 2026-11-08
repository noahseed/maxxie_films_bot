"""Surveillance locale ; seules les pannes déclenchent un message privé."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from telegram_api import Telegram, TelegramError


def problems(run=subprocess.run, directory=Path('/var/backups/maxxie-films-bot'), now=None):
    now=time.time() if now is None else now
    issues=[]
    for name in ('maxxie-films-bot','postgresql'):
        result=run(['systemctl','is-active','--quiet',name],capture_output=True)
        if result.returncode:
            issues.append(name+' est arrêté ou en échec')
    result=run(['systemctl','show','maxxie-films-backup.service','--property=Result','--value'],capture_output=True,text=True)
    if result.returncode or result.stdout.strip() not in ('success',''):
        issues.append('la dernière sauvegarde a échoué')
    archives=list(directory.glob('maxxie-films-*.tar.gz'))
    if not archives or now-max(path.stat().st_mtime for path in archives)>27*3600:
        issues.append('aucune sauvegarde récente depuis 27 heures')
    return issues


def main():
    directory=Path('/var/backups/maxxie-films-bot')
    with (directory/'.monitor.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        issues=problems(directory=directory)
        state=directory/'.monitor-state.json'
        last=json.loads(state.read_text()) if state.exists() else {}
        key='; '.join(issues)
        if issues and (last.get('key')!=key or time.time()-last.get('time',0)>3600):
            api=Telegram(os.environ['BOT_TOKEN'])
            try:
                api.call('sendMessage',chat_id=int(os.environ['NOTIFY_CHAT_ID']),
                    text='⚠️ Maxxie Films — surveillance\n\n'+'\n'.join('• '+item for item in issues))
                state.write_text(json.dumps({'key':key,'time':time.time()}))
            except TelegramError as error:
                print(f'Alerte non confirmée (code {error.code}).')
            finally:
                api.close()
        elif not issues and last.get('key'):
            state.write_text(json.dumps({'key':'','time':time.time()}))


if __name__=='__main__':
    main()
