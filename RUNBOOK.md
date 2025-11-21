# RUNBOOK

## Secrets
- `.env` はローカル開発のみに使用。運用では direnv / 1Password CLI から環境変数を注入する。
- `PORCUPINE_ACCESS_KEY` は各端末専用。紛失時は Picovoice Console で失効し再発行する。

## Raspberry Pi 起動
1. `rsync -av src/ pi:/opt/chappy_ai/src`
2. `rsync -av config/ pi:/opt/chappy_ai/config`
3. `APP_ENV=rpi.prod` を設定した `.env` を配置
4. `python -m venv /opt/chappy_ai/.venv && source /opt/chappy_ai/.venv/bin/activate`
5. `pip install -r requirements.txt`
6. `python -m src.main --config config/rpi.prod.yaml`

## systemd サービス雛形
```
[Unit]
Description=Chappy AI Voice Assistant
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/chappy_ai
Environment=APP_ENV=rpi.prod
ExecStart=/opt/chappy_ai/.venv/bin/python -m src.main --config config/rpi.prod.yaml
Restart=on-failure

[Install]
WantedBy=default.target
```
